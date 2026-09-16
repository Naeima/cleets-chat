from __future__ import annotations

import os
import re
from collections import defaultdict

try:
    from methods import METHODS, FAMILY_SHORT
except ImportError:  # methods.py is optional
    METHODS, FAMILY_SHORT = {}, {}

ONTOLOGY = "https://w3id.org/def/cleets"

# Model used for humanisation; override with CLEETS_LLM_MODEL in .env if needed.
LLM_MODEL = os.getenv("CLEETS_LLM_MODEL", "claude-haiku-4-5-20251001")

# Initialize Anthropic client (uses ANTHROPIC_API_KEY env var). The `anthropic`
# package is imported lazily so the dashboard still runs (templated answers only)
# when it is not installed.
_client = None

def get_client():
    global _client
    if _client is None:
        api_key = os.getenv("ANTHROPIC_API_KEY")
        if not api_key:
            raise ValueError("ANTHROPIC_API_KEY environment variable not set")
        try:
            import anthropic
        except ImportError as exc:
            raise ValueError("The 'anthropic' package is not installed: run  pip install -r requirements.txt") from exc
        _client = anthropic.Anthropic(api_key=api_key)
    return _client


def md_links(links):
    bits = [f"[{x['label']}]({x['url']})" for x in links]
    bits.append(f"[CLEETS knowledge graph]({ONTOLOGY})")
    return " · ".join(dict.fromkeys(bits))


def extract_year(q: str, default=2045):
    years = [int(x) for x in re.findall(r"\b(20\d{2})\b", q)]
    return years[-1] if years else default


def extract_scenario(q: str, default="central"):
    # Whole-word match only: "highest"/"lowest" are rankings, not scenarios.
    m = re.search(r"\b(low|central|high)\b", q.casefold())
    return m.group(1) if m else default


def humanize_answer(markdown_body: str, metadata: dict = None, humanize: bool = True) -> str:
    """
    Rephrase templated answer for readability using Claude Haiku.

    Args:
        markdown_body: The answer text (without Sources line)
        metadata: dict with keys like 'subject', 'value', 'period', 'scenario'
        humanize: if False, returns body unchanged

    Returns:
        Humanized markdown text, or original if humanize=False or API fails
    """
    if not humanize:
        return markdown_body

    metadata = metadata or {}

    system_prompt = """You are a technical writer specializing in data presentation.

Your task: rephrase the provided answer for clarity and readability.

STRICT CONSTRAINTS (non-negotiable):
1. You may reorganize, condense, or expand phrasing only.
2. Do NOT add new facts, qualifications, or claims not in the input.
3. Do NOT speculate, infer, or add interpretations beyond the stated data.
4. Preserve all quantitative values, periods, and scenario names exactly as given.
5. Keep tone professional, direct, and suitable for research documentation.

If the input is already well-phrased, minimal changes are acceptable."""

    user_prompt = f"""Rephrase this answer for clarity:

{markdown_body}"""

    if metadata:
        user_prompt += "\n\n--- Source data context ---\n"
        for k, v in metadata.items():
            user_prompt += f"{k}: {v}\n"

    try:
        client = get_client()
        response = client.messages.create(
            model=LLM_MODEL,
            max_tokens=600,
            system=system_prompt,
            messages=[{"role": "user", "content": user_prompt}]
        )
        return response.content[0].text
    except Exception as e:
        # Fail gracefully: return original if API error
        print(f"Warning: humanization failed ({e}), returning original answer")
        return markdown_body


def preserve_sources(full_answer: str, humanized_body: str) -> str:
    """
    Reattach the Sources line to the humanized body, ensuring citations are unchanged.
    """
    if "\n**Sources:**" not in full_answer:
        return humanized_body

    _, sources_line = full_answer.rsplit("\n**Sources:**", 1)
    return humanized_body + "\n**Sources:**" + sources_line


# --------------------------------------------------------------------------- formatting helpers
def _fmt(v, pct=False, digits=2):
    if v is None or v == "":
        return "n/a"
    if isinstance(v, str):
        return v
    if pct:
        return f"{v:.{digits}%}"
    if float(v).is_integer() and abs(v) >= 1000:
        return f"{int(v):,}"
    if float(v).is_integer():
        return f"{int(v)}"
    return f"{v:,.{digits}f}" if abs(v) >= 1 else f"{v:.4g}"


def md_table(rows, columns=None, max_rows=None) -> str:
    """Render a list of dict rows as a Markdown table."""
    if not rows:
        return "_no rows_"
    columns = columns or list(rows[0].keys())
    lines = ["| " + " | ".join(columns) + " |", "|" + "|".join("---" for _ in columns) + "|"]
    shown = rows if max_rows is None else rows[:max_rows]
    for r in shown:
        cells = []
        for c in columns:
            v = r.get(c)
            cells.append(_fmt(v) if not isinstance(v, str) else v)
        lines.append("| " + " | ".join(cells) + " |")
    if max_rows is not None and len(rows) > max_rows:
        lines.append(f"\n_{len(rows) - max_rows} more rows in the downloadable table._")
    return "\n".join(lines)


def family_sources(kg, family: str):
    fam = kg.family(family) if hasattr(kg, "family") else None
    return fam.get("used_links", []) if fam else []


def family_label(kg, family: str) -> str:
    fam = kg.family(family) if hasattr(kg, "family") else None
    return FAMILY_SHORT.get(family) or (fam["label"] if fam else family)


# --------------------------------------------------------------------------- model metrics helpers
def _metric_table(rows, with_target: bool = False, rank: bool = False):
    """Uniform Markdown rows for ModelMetric records (pooled R2 / n only when the run recorded them)."""
    out = []
    for i, m in enumerate(rows, 1):
        r = {}
        if rank:
            r["Rank"] = i
        if with_target:
            r["Target"] = m["target"]
        r.update({"Model": m["model"], "Scenario": m.get("scenario") or "-", "MAE": m["mae"], "RMSE": m["rmse"], "R2 (mean per LAD)": m["r2"]})
        if m.get("pooled_r2") is not None:
            r["Pooled R2"] = m["pooled_r2"]
        if m.get("n") is not None:
            r["n"] = int(m["n"])
        out.append(r)
    return out


def _protocol_label(metrics) -> str:
    notes = " ".join(m.get("note", "") for m in metrics)
    if "rolling-origin" in notes:
        return "rolling-origin one-step-ahead quarterly backtest, held-out quarters 2022 Q1 to 2025 Q4, 352 LAD-quarters per configuration"
    return "walk-forward 2023-2025, annual LAD panel"


def _target_key(question: str):
    q = question.casefold()
    if any(w in q for w in ("charger", "charging", "charge point", "chargepoint", "evci")):
        return "chargers"
    if any(w in q for w in ("keepership", "keeper", "bev count", "ev count", "vehicles", "adoption")):
        return "keepership"
    return None


def _best_line(kg) -> str:
    best = kg.best_models() if hasattr(kg, "best_models") else {}
    if not best:
        return ""
    return "In the loaded run the lowest one-step-ahead MAE is " + "; ".join(
        f"**{b['model']}** for {t} (MAE {_fmt(b['mae'])}, RMSE {_fmt(b['rmse'])}, mean per-LAD R2 {_fmt(b['r2'], digits=3)})"
        for t, b in best.items()) + "."


# --------------------------------------------------------------------------- worked examples (ⓘ panels)
# Each example is written for a lay reader and filled only with values read from the graphs
# (or arithmetic on them that the notebook itself performs), so it stays true after a re-run.
EXAMPLE_LAD = "Cardiff"


def _pick_lad(kg, preferred=EXAMPLE_LAD):
    names = kg.lad_names() if hasattr(kg, "lad_names") else []
    return preferred if preferred in names else (names[0] if names else None)


def _example_diffusion(kg) -> str:
    lad = _pick_lad(kg)
    if not lad:
        return ""
    keep = kg.latest_observation(lad, "keepership")
    stock = kg.latest_observation(lad, "vehicle_stock")
    rows = {y: kg.prediction_rows(y, "central", lad, family="diffusion") for y in (2030, 2035, 2045)}
    if not keep or not all(rows.values()):
        return "The loaded graphs do not contain enough values for a worked example."
    parts = [f"Think of {lad}. At {keep['period']} it had **{_fmt(keep['value'])}** privately kept battery-electric vehicles"]
    if stock and stock["value"]:
        parts[-1] += (f" out of **{_fmt(stock['value'])}** private vehicles ({stock['period']}), a share of "
                      f"**{keep['value'] / stock['value']:.1%}**")
    parts[-1] += (". The curve treats adoption like the spread of any new technology, smartphones for instance: slow at first, "
                  "fastest in the middle years, then levelling off as the market fills up.")
    ms = {m["threshold_share"]: m["period"] for m in kg.milestones(lad, "central") if m.get("family", "diffusion") == "diffusion"}
    mid = ms.get(0.5)
    steps = "; ".join(f"**{_fmt(r[-1]['keepership'])}** ({r[-1]['adoption_share']:.1%}) at {r[-1]['period']}" for r in rows.values())
    parts.append(f"Under the central scenario {lad}'s curve"
                 + (f" passes the halfway mark in **{mid}** and" if mid else "")
                 + f" gives {steps}.")
    lo = kg.prediction_rows(2045, "low", lad, family="diffusion"); hi = kg.prediction_rows(2045, "high", lad, family="diffusion")
    if lo and hi:
        parts.append(f"The low and high scenarios slide the same curve later or earlier, giving **{_fmt(lo[-1]['keepership'])}** and "
                     f"**{_fmt(hi[-1]['keepership'])}** vehicles at {lo[-1]['period']}.")
    if stock and stock["value"]:
        parts.append(f"Every count is the predicted share multiplied by the {_fmt(stock['value'])} vehicles {lad} had at {stock['period']}, "
                     "so a growing or shrinking future fleet is not part of the picture.")
    return " ".join(parts)


def _example_hierarchical(kg) -> str:
    rows = kg.hierarchical_params() if hasattr(kg, "hierarchical_params") else []
    if not rows:
        return "No hierarchical parameters are loaded, so there is no worked example."
    slow, fast = rows[0], rows[-1]
    lad = _pick_lad(kg)
    mine = next((r for r in rows if r["lad_name"] == lad), None)
    parts = [f"The midpoint is the quarter in which a district's curve reaches half of its ceiling. **{slow['lad_name']}** is the slowest district: "
             f"its midpoint is **{slow['midpoint_period']}**, {abs(slow['lag_vs_median_years']):.1f} years "
             f"{'behind' if slow['lag_vs_median_years'] > 0 else 'ahead of'} the Welsh median, while **{fast['lad_name']}** is the fastest at "
             f"**{fast['midpoint_period']}** ({abs(fast['lag_vs_median_years']):.1f} years {'ahead' if fast['lag_vs_median_years'] < 0 else 'behind'})."]
    parts.append("Each district's estimate is a blend, like predicting a student's exam mark from their own mock results and from the class pattern: "
                 "the more precisely a district's own history pins down its curve, the more the model trusts it.")
    if slow.get("shrinkage_weight") is not None:
        w = slow["shrinkage_weight"]
        parts.append(f"{slow['lad_name']}'s shrinkage weight of {w:.3f} means **{w:.1%}** of its midpoint comes from its own data and "
                     f"**{1 - w:.1%}** from what its population and density would predict.")
    if mine:
        parts.append(f"{lad} sits at rank {int(mine['slowest_rank'])} of {len(rows)} (slowest first): midpoint **{mine['midpoint_period']}**, "
                     f"rate {mine['rate_per_quarter']:.3f} per quarter, interval width {mine['ci_width_years']:.1f} years.")
    return " ".join(parts)


def _example_turnover(kg) -> str:
    lad = _pick_lad(kg)
    rows = kg.turnover_rows(lad) if (lad and hasattr(kg, "turnover_rows")) else []
    if not rows:
        return "No turnover results are loaded, so there is no worked example."
    r = rows[0]
    stock = kg.latest_observation(lad, "vehicle_stock")
    ce = {c["median_scrappage_years"]: c for c in kg.turnover_ceilings()} if hasattr(kg, "turnover_ceilings") else {}
    c14 = ce.get(14.0) or ce.get(14)
    parts = [f"Picture {lad}'s" + (f" **{_fmt(stock['value'])}**" if stock else "") + " private vehicles as a queue in which the oldest are scrapped and replaced"
             + (f", about {c14['implied_annual_replacement_pct']:.1f}% of the fleet a year when a vehicle lasts a median 14 years" if c14 else "")
             + ". From 2033 every replacement is a BEV, so the BEV share can rise only as fast as the old vehicles leave."]
    parts.append(f"For {lad} that gives a BEV share of **{r['bev_share_2045']:.1%}** at 2045 Q4"
                 + (f", 95% first reached in **{r['reaches_0.95']}**" if r.get("reaches_0.95") else "")
                 + (f" and 99% in **{r['reaches_0.99']}**" if r.get("reaches_0.99") else "")
                 + (f", with about **{_fmt(round(r['residual_non_bev']))}** non-BEV vehicles still on the road at 2053 Q4" if r.get("residual_non_bev") is not None else "")
                 + ".")
    if ce:
        parts.append("Wales-wide, the 2045 share is " + ", ".join(f"**{c['bev_share_2045']:.1%}** if vehicles last {c['median_scrappage_years']:g} years"
                                                                   for c in sorted(ce.values(), key=lambda x: x["median_scrappage_years"])) + ".")
    return " ".join(parts)


def _example_charging(kg) -> str:
    rows = kg.charging_assessments() if hasattr(kg, "charging_assessments") else []
    if not rows:
        return "No charging-constraint assessments are loaded, so there is no worked example."
    flagged = [r for r in rows if "binding" in r["constraint_class"] and r.get("charger_shortfall_2045")]
    r = flagged[0] if flagged else rows[0]
    lad = r["lad_name"]
    chg = kg.latest_observation(lad, "chargers")
    stock = kg.latest_observation(lad, "vehicle_stock")
    turn = (kg.turnover_rows(lad) or [None])[0] if hasattr(kg, "turnover_rows") else None
    parts = [f"Take **{lad}**" + (f", which has **{_fmt(chg['value'])}** public charging devices ({chg['period']})" if chg else "") + "."]
    if turn and stock:
        bevs = turn["bev_share_2045"] * stock["value"]
        parts.append(f"The turnover path gives it about **{_fmt(round(bevs, -2))}** BEVs by 2045 ({turn['bev_share_2045']:.1%} of {_fmt(stock['value'])} vehicles).")
        if r.get("evs_per_charge_point_2045"):
            devices = bevs / r["evs_per_charge_point_2045"]
            parts.append(f"If its devices grow 5% a year for 20 years it would have about **{_fmt(round(devices))}** of them, so each device would serve "
                         f"**{r['evs_per_charge_point_2045']:.0f}** BEVs against the benchmark of 20.")
    else:
        parts.append(f"The assessment stores **{r['evs_per_charge_point_2045']:.0f}** BEVs per public device at 2045 against the benchmark of 20.")
    if r.get("charger_shortfall_2045"):
        parts.append(f"Meeting the benchmark would take about **{_fmt(round(r['charger_shortfall_2045']))}** more devices than that growth path provides"
                     + (f"; because {lad} also diffuses slowly it is classed '{r['constraint_class']}'." if "binding" in r["constraint_class"] else "."))
    else:
        parts.append(f"It is classed '{r['constraint_class']}'.")
    n_flag = sum(1 for x in rows if "binding" in x["constraint_class"])
    parts.append(f"{n_flag} of {len(rows)} districts are flagged this way; the rest are 'provision will bind later', not 'provision is sufficient'.")
    return " ".join(parts)


def _drift_fold(kg, lad, measure, label, unit):
    """One rolling-origin fold of the persistence + drift baseline, computed exactly as Stage 14 does:
    prediction = last training value + (last - value five quarters back) / 4."""
    obs = [o for o in kg.observations(lad, measure) if o["value"] is not None and o["quarter"]]
    obs = [o for o in obs if (o["year"], o["quarter"]) <= (2025, 4)]
    if len(obs) < 6:
        return None
    idx = {(o["year"], o["quarter"]): o for o in obs}
    test = obs[-1]
    y, q = test["year"], test["quarter"]
    chain = []
    for _ in range(5):
        q -= 1
        if q == 0:
            y, q = y - 1, 4
        if (y, q) not in idx:
            return None
        chain.append(idx[(y, q)])
    last, back5 = chain[0], chain[4]
    d = (last["value"] - back5["value"]) / 4
    pred = last["value"] + d
    return (f"For {lad}'s {label} at **{test['period']}** the training data stop at {last['period']} ({_fmt(last['value'])} {unit}). "
            f"The drift baseline adds the average quarterly change of the previous year, ({_fmt(last['value'])} − {_fmt(back5['value'])}) / 4 = "
            f"{d:+.1f}, and predicts **{_fmt(round(pred))}**; the actual value was **{_fmt(test['value'])}**, a miss of about {abs(pred - test['value']):.0f} {unit}. "
            f"The scenario-constrained network sees the same history plus a ceiling K = 10 × {_fmt(last['value'])} = {_fmt(10 * last['value'])} "
            f"under the central scenario (6× low, 15× high).")


def _example_neural(kg) -> str:
    lad = _pick_lad(kg)
    if not lad:
        return ""
    parts = ["Each model is tested the way a weather forecast is: it is shown history up to one quarter, asked for the next, and scored "
             "against what really happened, for every district and every quarter from 2022 Q1 to 2025 Q4."]
    for measure, label, unit in (("chargers", "public charging devices", "devices"), ("keepership", "BEV keepership", "vehicles")):
        f = _drift_fold(kg, lad, measure, label, unit)
        if f:
            parts.append(f)
    best = kg.best_models() if hasattr(kg, "best_models") else {}
    if best:
        parts.append("The MAE in the table is the average size of such misses over the 352 district-quarters: "
                     + "; ".join(f"**{_fmt(b['mae'])}** {('devices' if 'charger' in t.lower() else 'vehicles')} for {b['model']} on {t}"
                                 for t, b in best.items())
                     + ". R2 near 1 means the model follows each district's ups and downs closely; a negative R2 means it does worse than "
                       "simply guessing the district's average.")
    return " ".join(parts)


def _example_covariates(kg) -> str:
    res = kg.covariate_residuals() if hasattr(kg, "covariate_residuals") else []
    if not res:
        return "No covariate residuals are loaded, so there is no worked example."
    lo, hi = res[0], res[-1]
    lad = _pick_lad(kg)
    mine = next((r for r in res if r["lad_name"] == lad), None)
    parts = [f"The question is whether a district's size and density alone explain its uptake. **{hi['lad_name']}** has **{hi['observed']:.1f}** BEVs per 1,000 residents; "
             f"from its population, density and land area the Ridge model expects **{hi['predicted']:.1f}**, so it adopts **{hi['residual']:+.1f}** per 1,000 more "
             f"than those three facts would suggest. **{lo['lad_name']}** has {lo['observed']:.1f} against an expected {lo['predicted']:.1f} ({lo['residual']:+.1f})."]
    if mine:
        parts.append(f"{lad}: {mine['observed']:.1f} observed, {mine['predicted']:.1f} expected ({mine['residual']:+.1f}).")
    parts.append("Notice that the expected values are almost identical for every district: the model finds so little signal in size and density that it "
                 "falls back on the Welsh average, which is the paper's point.")
    eff = [e for e in (kg.covariate_effects() if hasattr(kg, "covariate_effects") else []) if e["term"] != "intercept"]
    if eff:
        parts.append("Timing is different. In the hierarchical model " + "; ".join(
            f"a district one standard deviation {'denser' if e['term'] == 'density' else 'larger in ' + e['term']} reaches its midpoint "
            f"**{abs(e['beta_midpoint_q']):.1f} quarters {'earlier' if e['beta_midpoint_q'] < 0 else 'later'}**" for e in eff) + ".")
    return " ".join(parts)


EXAMPLES = {"diffusion": _example_diffusion, "hierarchical": _example_hierarchical, "turnover": _example_turnover,
            "charging": _example_charging, "neural": _example_neural, "covariates": _example_covariates}


# --------------------------------------------------------------------------- methods (ⓘ panels)
def methods_text(kg, family: str) -> str:
    """Markdown explanation of how a prediction family was generated, with KG values filled in."""
    spec = METHODS.get(family)
    if spec is None:
        fam = kg.family(family) if hasattr(kg, "family") else None
        if fam is None:
            return "No method description is available for this prediction type."
        return f"### {fam['label']}\n\n{fam.get('comment') or ''}"
    fam = kg.family(family) if hasattr(kg, "family") else None
    fill = defaultdict(str)

    # provenance line from the prov:Activity
    if fam:
        used = " · ".join(f"[{l['label']}]({l['url']})" for l in fam.get("used_links", [])) or "n/a"
        act = fam.get("activity_label") or fam["label"]
        fill["activity"] = (f"Generated by the activity *{act}*"
                            + (f" ({fam['ended'][:10]})" if fam.get("ended") else "")
                            + f"; source datasets: {used}. Paper: {fam.get('paper') or 'n/a'}; notebook: {fam.get('stage') or 'n/a'}."
                            + (f"\n\n> {fam['comment']}" if fam.get("comment") else ""))
    else:
        fill["activity"] = "This prediction type is not present in the loaded prediction KG."

    if family == "diffusion":
        act = kg.prediction_activity() if hasattr(kg, "prediction_activity") else {}
        lines = []
        for s in sorted(act.get("scenarios", []), key=lambda x: x.get("terminal_target_share") or 0):
            tts = s.get("terminal_target_share"); sh = s.get("midpoint_shift_quarters")
            if tts is not None:
                lines.append(f"**{s['scenario']}**: {tts:.1%} of the private stock at 2045 Q4"
                             + (f" (midpoint shift {sh:+.2f} quarters)" if sh is not None else ""))
        fill["scenario_lines"] = ("Scenario constraints in the KG: " + "; ".join(lines) + ".") if lines else ""

    if family in ("hierarchical", "covariates"):
        eff = kg.covariate_effects() if hasattr(kg, "covariate_effects") else []
        eff = [e for e in eff if e["term"] != "intercept"]
        if eff:
            fill["effects"] = ("In the loaded run: " + "; ".join(
                f"**{e['term']}** {e['beta_midpoint_q']:+.2f} quarters per sd [{e['lo']:.2f}, {e['hi']:.2f}]"
                + (" (interval crosses zero)" if e.get("crosses_zero") else "") for e in eff) + ".")
        else:
            fill["effects"] = "(Covariate effects are not loaded; run build_prediction_families.py.)"

    if family == "turnover":
        ce = kg.turnover_ceilings() if hasattr(kg, "turnover_ceilings") else []
        if ce:
            fill["ceilings"] = "Wales-wide ceilings at 2045 Q4 in the loaded run: " + "; ".join(
                f"median scrappage {c['median_scrappage_years']:g} years → **{c['bev_share_2045']:.1%}** BEV share"
                f" ({_fmt(c['residual_non_bev'])} residual non-BEV vehicles)" for c in ce) + "."

    if family == "diffusion":
        s13 = kg.logistic_backtest() if hasattr(kg, "logistic_backtest") else {}
        if s13:
            rows = [r for rs in s13.values() for r in rs]
            fill["metrics_stage13"] = ("\n\nStage 13, bounded logistic re-run off the released KG (rolling-origin one-step-ahead, "
                                       f"{_fmt(rows[0].get('n'), digits=0)} held-out LAD-quarters per row, loaded run):\n\n"
                                       + md_table(_metric_table(rows)))
        else:
            fill["metrics_stage13"] = ""

    if family == "neural":
        m7 = [m for m in kg.model_metrics("neural") if "Table 7" in m.get("note", "")] if hasattr(kg, "model_metrics") else []
        m6 = [m for m in kg.model_metrics("neural") if "Stage 6e" in m.get("note", "")] if hasattr(kg, "model_metrics") else []
        if m7:
            fill["metrics_table7"] = (f"\n\nTable 7, best configuration per approach ({_protocol_label(m7)}; loaded run):\n\n"
                                      + md_table(_metric_table(m7, with_target=True)))
            fill["best_line"] = _best_line(kg)
        if m6:
            fill["metrics_6e"] = "\n\nStage 6e walk-forward on first differences (pp, loaded run):\n\n" + md_table(
                [{"Model": m["model"], "MAE (pp)": m["mae"], "RMSE (pp)": m["rmse"], "R2 diff": m["r2"]} for m in m6])
        fam_n = (fam or {}).get("predictions", 0)
        fill["forecast_note"] = ("Per-LAD quarterly neural forecasts to 2030 Q4 are loaded." if fam_n else
                                 "No per-LAD network forecast is in the loaded KG (the quarterly notebook produces evaluation "
                                 "metrics only); the 2045 scenarios come from the bounded logistic.")

    if family == "covariates":
        m8 = kg.model_metrics("covariates") if hasattr(kg, "model_metrics") else []
        if m8:
            fill["metrics_table8"] = "\n\nTable 8 (leave-one-out, EVs per 1,000 residents, loaded run):\n\n" + md_table(
                [{"Model": m["model"], "MAE": m["mae"], "RMSE": m["rmse"], "R2": m["r2"]} for m in sorted(m8, key=lambda x: x["rmse"] or 0)])
        res = kg.covariate_residuals() if hasattr(kg, "covariate_residuals") else []
        if res:
            lo, hi = res[0], res[-1]
            fill["residuals"] = (f"Largest negative residual: **{lo['lad_name']}** ({lo['residual']:+.2f}); "
                                 f"largest positive: **{hi['lad_name']}** ({hi['residual']:+.2f}).")

    if family in EXAMPLES:
        try:
            fill["example"] = EXAMPLES[family](kg) or ""
        except Exception as exc:  # an example must never break the panel
            fill["example"] = f"(worked example unavailable: {type(exc).__name__})"

    body = spec["body"]
    for k in re.findall(r"\{(\w+)\}", body):
        body = body.replace("{" + k + "}", fill.get(k, ""))
    return f"### {spec['title']}\n{body}".strip()


# --------------------------------------------------------------------------- family detection
FAMILY_KEYWORDS = [
    ("turnover", ("turnover", "scrappage", "phase-out", "phase out", "sales ban", "ban", "2053", "arrival", "residual",
                  "ice ", "non-bev", "age-structured", "structural age", "vintage", "ceiling", "fleet")),
    ("hierarchical", ("hierarchical", "midpoint", "slowest", "fastest", "diffuse", "diffusion rate", "empirical bayes",
                      "pooling", "shrink", "rate per quarter", "lag")),
    ("charging", ("charging constraint", "provision", "binding", "chargers per", "bevs per", "charge point", "charging provision")),
    ("neural", ("neural", " nn", "gnn", "perceptron", "graph neural", "walk-forward", "walk forward", "table 6", "table 7", "mlp")),
    ("covariates", ("covariate", "ridge", "random forest", "extra trees", "leave-one-out", "table 8", "relate", "relationship",
                    "correlat", "what makes", "population density", "deprivation")),
]


def detect_family(question: str, default: str = "diffusion") -> str:
    q = " " + question.casefold() + " "
    for key, words in FAMILY_KEYWORDS:
        if any(w in q for w in words):
            return key
    return default


def _method_footer(kg, family):
    return f"\n\n*Prediction type: {family_label(kg, family)}. Press ⓘ for how it was generated.*"


# --------------------------------------------------------------------------- dataset extraction
TABLE_TRIGGERS = ("table", "csv", "download", "extract", "export", "spreadsheet", "tabulate", "give me the data")
# "dataset"/"data set" only count as a table request together with an extraction verb,
# so provenance questions ("which dataset supports this answer?") are not intercepted.
TABLE_WEAK = ("dataset", "data set", "list the", "pull")
TABLE_VERBS = ("give", "build", "create", "make", "get", "generate", "prepare", "want", "need", "show me a", "produce", "compile")
COLUMN_KEYWORDS = [
    ("keepership", ("keepership", "keeper", "bev count", "ev count", "electric vehicle")),
    ("chargers", ("charger", "charging count", "charging device", "chargepoint", "charge point")),
    ("ratio", ("keepers per charger", "ratio")),
    ("chargers_per_100k", ("per 100k", "per 100,000")),
    ("evs_per_1000", ("per 1,000", "per 1000", "per thousand")),
    ("vehicle_stock", ("vehicle stock", "licensed vehicles", "private stock")),
    ("population", ("population",)),
    ("density", ("density",)),
    ("deprivation", ("deprivation", "wimd", "income")),
    ("hier_midpoint", ("midpoint", "hierarchical")),
    ("hier_rate", ("diffusion rate", "rate per quarter")),
    ("turnover_share_2045", ("turnover", "ceiling", "phase-out", "ban")),
    ("turnover_reaches_99", ("arrival", "reaches 99", "99%")),
    ("turnover_residual", ("residual non-bev", "residual ice", "non-bev")),
    ("charging_class", ("charging constraint", "constraint class", "binding")),
    ("covariate_residual", ("covariate residual", "ridge residual")),
]
DEFAULT_TABLE_COLUMNS = ["keepership", "chargers", "deprivation", "population", "density"]


def wants_table(question: str) -> bool:
    q = question.casefold()
    if any(p in q for p in ("supports this", "source dataset", "which dataset", "datasets were used", "provenance", "where did")):
        return False
    if any(t in q for t in TABLE_TRIGGERS):
        return True
    return any(t in q for t in TABLE_WEAK) and any(v in q for v in TABLE_VERBS)


def table_columns_from_text(question: str, mode: str = "actual"):
    q = " " + question.casefold() + " "
    cols = []
    for key, words in COLUMN_KEYWORDS:
        if any(w in q for w in words) and key not in cols:
            # "population density" must not also select population
            if key == "population" and "density" in q and "population density" in q and " population " not in q.replace("population density", ""):
                continue
            cols.append(key)
    if any(w in q for w in ("predict", "forecast", "2045", "scenario")) or mode == "prediction":
        sc = extract_scenario(question)
        cols.append(f"pred_keepership_{sc}")
        if "share" in q or "penetration" in q:
            cols.append("pred_share_central")
    if not cols:
        cols = list(DEFAULT_TABLE_COLUMNS) + (["pred_keepership_central"] if mode == "prediction" else [])
    return list(dict.fromkeys(cols))


def table_answer(kg, question: str, mode: str = "actual") -> dict:
    """Build a per-LAD table from the KG according to the question."""
    cols = table_columns_from_text(question, mode)
    available = {k for k, _ in kg.dataset_columns()}
    cols = [c for c in cols if c in available] or [c for c in DEFAULT_TABLE_COLUMNS if c in available]
    lads = [name for name, _ in kg.find_lads_in_text(question)] or None
    years = [int(y) for y in re.findall(r"\b(20[0-2]\d)\b", question)]
    year = years[-1] if years else None
    rows = kg.dataset_table(cols, lads=lads, year=year)
    links = kg.dataset_sources(cols)
    scope = f"{len(rows)} LAD{'s' if len(rows) != 1 else ''}" + (f" ({', '.join(lads)})" if lads else " (all Welsh LADs)")
    labels = [kg.DATASET_COLUMNS[c][0] for c in cols]
    md = (f"### Custom dataset: {scope}\n\n"
          f"Columns: {', '.join(labels)}. Observed columns use the latest available period"
          f"{f' in {year}' if year else ''}; the period of each value is included in the download.\n\n"
          + md_table(rows, [c for c in rows[0].keys() if not c.endswith(" period")] if rows else None, max_rows=25)
          + f"\n\n**Sources:** {md_links(links)}"
          + "\n\n*Use the download button to save the full table as CSV, or plot any column on the map.*")
    return {"markdown": md, "table": rows, "columns": cols, "kind": "table", "family": None, "sources": links}


# --------------------------------------------------------------------------- inventory
def inventory_answer(kg, mode):
    if mode == "prediction":
        inv = kg.prediction_inventory()
        fams = kg.prediction_families() if hasattr(kg, "prediction_families") else []
        fam_lines = "\n".join(
            f"- **{family_label(kg, f['key'])}**: "
            + (f"{f['predictions']:,} LAD-quarter forecasts, scenarios {', '.join(f['scenarios'])}" if f["predictions"] else "")
            + (f"{'; ' if f['predictions'] else ''}{f['resources']} per-LAD resources" if f["resources"] else "")
            + (f"{'; ' if (f['predictions'] or f['resources']) else ''}evaluation metrics only" if "metrics" in f["kinds"] and not f["predictions"] and not f["resources"] else "")
            + (f" ({f['paper']})" if f.get("paper") else "")
            for f in fams)
        return (f"### Prediction data inventory\n\n"
                f"- **{inv['prediction_count']:,}** quarterly scenario forecasts across **{len(inv['lads'])}** Welsh LADs "
                f"({inv['periods'][0] if inv['periods'] else '?'} to {inv['periods'][-1] if inv['periods'] else '?'}; "
                f"scenarios {', '.join(inv['scenarios']) or 'not stated'}).\n"
                f"- Measures: {', '.join(inv['measures'])}.\n\n"
                f"**Prediction types loaded (matching the paper):**\n{fam_lines}\n\n"
                f"**Knowledge graph:** [CLEETS]({ONTOLOGY})")
    inv = kg.actual_inventory()
    ds = [f"[{label}]({url})" if url else label for label, _, url in inv["datasets"][:12]]
    return (f"### Observed data inventory\n\n"
            f"The enriched graph contains **{inv['triples']:,} triples**, **{inv['subjects']:,} subjects** and **{inv['predicates']:,} predicates**.\n\n"
            f"**Datasets:** {' · '.join(ds) if ds else 'No dataset metadata found.'}\n\n"
            f"**Measures per LAD:** {', '.join(inv.get('measures', []))}.\n\n"
            f"**Knowledge graph:** [CLEETS]({ONTOLOGY})")


# --------------------------------------------------------------------------- prediction answers
def diffusion_answer(kg, question, humanize: bool = False):
    q = question.casefold()
    year, scenario = extract_year(question), extract_scenario(question)
    lads = kg.find_lads_in_text(question)
    fam = "diffusion"
    src = family_sources(kg, fam)

    if "all three" in q or (lads and "scenario" in q and "compare" in q) or (lads and "sensitiv" in q):
        name = lads[0][0] if lads else "Cardiff"
        lines = [f"### {name}: scenario comparison for {year}"]
        for sc in ("low", "central", "high"):
            rows = kg.prediction_rows(year, sc, name, family=fam)
            if rows:
                r = rows[-1]
                lines.append(f"- **{sc.title()}** ({r['period']}): predicted keepership **{r['keepership']:,.0f}**, adoption share **{r['adoption_share']:.2%}**." if r['adoption_share'] is not None else f"- **{sc.title()}**: **{r['keepership']:,.0f}** predicted keepership.")
        rows_c = kg.prediction_rows(year, "central", name, family=fam)
        if rows_c and "sensitiv" in q:
            lo = kg.prediction_rows(year, "low", name, family=fam); hi = kg.prediction_rows(year, "high", name, family=fam)
            if lo and hi:
                spread = hi[-1]["keepership"] - lo[-1]["keepership"]
                lines.append(f"\nSpread between the low and high scenarios at {rows_c[-1]['period']}: **{spread:,.0f}** vehicles "
                             f"({spread / rows_c[-1]['keepership']:.1%} of the central value). The scenarios differ only in the shared "
                             f"midpoint shift that sets the Wales-wide terminal share, so the spread measures the terminal-constraint sensitivity.")
        return "\n".join(lines) + f"\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam)

    if any(x in q for x in ("highest", "top", "rank")):
        rows = kg.prediction_year_summary(year, scenario, family=fam)
        if not rows:
            return f"No prediction observations were found for {year} under the {scenario} scenario."
        body = "\n".join(f"{i+1}. **{r['lad_name']}** — {r['keepership']:,.0f} ({r['period']})" for i, r in enumerate(rows[:10]))
        return (f"### Highest predicted EV keepership — {year}, {scenario} scenario\n\n{body}\n\n**Sources:** {md_links(src)}"
                + _method_footer(kg, fam))

    if any(x in q for x in ("lowest", "bottom")):
        rows = list(reversed(kg.prediction_year_summary(year, scenario, family=fam)))
        body = "\n".join(f"{i+1}. **{r['lad_name']}** — {r['keepership']:,.0f} ({r['period']})" for i, r in enumerate(rows[:10]))
        return (f"### Lowest predicted EV keepership — {year}, {scenario} scenario\n\n{body}\n\n**Sources:** {md_links(src)}"
                + _method_footer(kg, fam))

    if "milestone" in q or "when" in q or "reach" in q or "cross" in q:
        name = lads[0][0] if lads else None
        ms = [m for m in kg.milestones(name, scenario) if m["family"] == fam]
        if ms:
            title = f"### {name or 'Wales'}: adoption-share milestones, {scenario} scenario"
            body = "\n".join(f"- **{m['threshold_share']:.0%}** share first reached in **{m['period']}**" + ("" if name else f" ({m['lad_name']})") for m in ms[:12])
            return f"{title}\n\n{body}\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam)

    if lads:
        name = lads[0][0]
        rows = kg.prediction_rows(year, scenario, name, family=fam)
        if rows:
            r = rows[-1]
            links = kg.source_links_for_subject(r["subject"], prediction=True) or src
            share = f"; predicted adoption share **{r['adoption_share']:.2%}**" if r["adoption_share"] is not None else ""
            body = (f"Under the **{scenario}** scenario, the latest {year} quarterly prediction ({r['period']}) gives predicted private BEV keepership of **{r['keepership']:,.0f}**{share}.")
            if len(lads) > 1:
                other = kg.prediction_rows(year, scenario, lads[1][0], family=fam)
                if other:
                    o = other[-1]
                    body += (f" For **{lads[1][0]}** the same quarter gives **{o['keepership']:,.0f}** ({o['adoption_share']:.2%}). "
                             f"Both LADs follow the same scenario constraint; the counts differ because each share is multiplied by the LAD's own "
                             f"private vehicle stock and each curve has its own fitted rate and midpoint.")
            if humanize:
                body = humanize_answer(body, metadata={"subject": name, "value": f"{r['keepership']:,.0f}", "period": r['period'], "scenario": scenario})
            return (f"### {name} prediction\n\n{body}\n\n**Sources:** {md_links(links)}\n\n"
                    f"*This is a model prediction, not an observed value.*" + _method_footer(kg, fam))

    if any(x in q for x in ("generated", "source dataset", "provenance", "evidence path", "assumption", "observed, calculated",
                            "which dataset", "supports this", "where did", "datasets were used")):
        act = kg.prediction_activity()
        used = " · ".join(f"[{l['label']}]({l['url']})" for l in act.get("used", [])) if act else ""
        cite = (kg.family("diffusion") or {}).get("citation", "") if hasattr(kg, "family") else ""
        return ("### Prediction provenance\n\n"
                + (f"The diffusion forecasts were generated by the activity **{act['label']}** ({act['ended'][:10]}). {act['comment']}\n\n"
                   f"Source datasets: {used}.\n\n" if act else "")
                + (f"Citation: {cite}\n\n" if cite else "")
                + "Every forecast resource in the KG links to this activity with `prov:wasGeneratedBy` and to its source datasets with "
                  "`dcterms:source`; ask about a specific LAD, year and scenario to retrieve one. Values are model predictions, not observations.\n\n"
                + f"**Knowledge graph:** [CLEETS]({ONTOLOGY})" + _method_footer(kg, fam))

    rows = kg.prediction_year_summary(year, scenario, family=fam)
    if rows:
        avg = sum(r["keepership"] for r in rows if r["keepership"] is not None) / len(rows)
        wales = kg.area_prediction_rows(year, scenario) if hasattr(kg, "area_prediction_rows") else []
        body = (f"I found {len(rows)} LAD-level year-end records. Mean predicted private BEV keepership is **{avg:,.0f}** per LAD; "
                f"the highest is **{rows[0]['lad_name']} ({rows[0]['keepership']:,.0f})** and the lowest **{rows[-1]['lad_name']} ({rows[-1]['keepership']:,.0f})**.")
        if wales:
            w = wales[-1]
            body += f" The Wales-wide total at {w['period']} is **{w['keepership']:,.0f}** private BEVs ({w['adoption_share']:.1%} of the private stock)."
        if humanize:
            body = humanize_answer(body, metadata={"count": len(rows), "mean_keepership": f"{avg:,.0f}", "year": year, "scenario": scenario})
        return (f"### Wales prediction summary — {year}, {scenario} scenario\n\n{body}\n\n**Sources:** {md_links(src)}"
                + _method_footer(kg, fam))

    return "I could not map that free-text question to prediction evidence currently present in the KG. Try naming a LAD, year, scenario, ranking or provenance request."


def hierarchical_answer(kg, question, humanize: bool = False):
    fam = "hierarchical"
    rows = kg.hierarchical_params()
    if not rows:
        return ("### Hierarchical diffusion\n\nThe hierarchical-diffusion parameters are not in the loaded KG. Run "
                "`python build_prediction_families.py --notebook <companion notebook>` and restart." + _method_footer(kg, fam))
    q = question.casefold()
    lads = kg.find_lads_in_text(question)
    src = family_sources(kg, fam)
    if lads:
        parts = []
        for name, _ in lads[:3]:
            r = next((x for x in rows if x["lad_name"] == name), None)
            if r:
                parts.append(f"**{name}** diffuses with midpoint **{r['midpoint_period']}** (rank {int(r['slowest_rank'])} of {len(rows)}, slowest first), "
                             f"{r['lag_vs_median_years']:+.2f} years against the Welsh median, rate **{r['rate_per_quarter']:.3f}** per quarter, "
                             f"95% interval width {r['ci_width_years']:.2f} years, shrinkage weight {r['shrinkage_weight']:.3f}.")
        body = " ".join(parts)
        if humanize:
            body = humanize_answer(body, metadata={"model": "hierarchical diffusion"})
        return f"### {', '.join(n for n, _ in lads[:3])}: hierarchical diffusion parameters\n\n{body}\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam)
    if any(w in q for w in ("fastest", "earliest", "quick")):
        ordered = list(reversed(rows))
        title = "Fastest-diffusing LADs (earliest midpoint)"
    else:
        ordered = rows
        title = "Slowest-diffusing LADs (latest midpoint)"
    body = md_table([{"Rank": int(r["slowest_rank"]), "LAD": r["lad_name"], "Midpoint": r["midpoint_period"],
                      "Lag vs median (years)": r["lag_vs_median_years"], "Rate / quarter": r["rate_per_quarter"],
                      "95% width (years)": r["ci_width_years"]} for r in ordered], max_rows=22)
    eff = [e for e in kg.covariate_effects() if e["term"] != "intercept"]
    eff_line = ("\n\nCovariate effects on the midpoint (quarters per 1 sd; positive = slower): " + "; ".join(
        f"**{e['term']}** {e['beta_midpoint_q']:+.2f} [{e['lo']:.2f}, {e['hi']:.2f}]" for e in eff) + ".") if eff else ""
    return f"### {title}\n\n{body}{eff_line}\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam)


def turnover_answer(kg, question, humanize: bool = False):
    fam = "turnover"
    rows = kg.turnover_rows()
    if not rows:
        return ("### Age-structured turnover\n\nThe turnover trajectories are not in the loaded KG. Run "
                "`python build_prediction_families.py --notebook <companion notebook>` and restart." + _method_footer(kg, fam))
    q = question.casefold()
    lads = kg.find_lads_in_text(question)
    src = family_sources(kg, fam)
    ceilings = kg.turnover_ceilings()
    if lads:
        parts = []
        for name, _ in lads[:3]:
            r = next((x for x in rows if x["lad_name"] == name), None)
            if r:
                parts.append(f"**{name}**: under the 2032 phase-out with a 14-year median scrappage age, BEV share of the private parc reaches "
                             f"**{r['bev_share_2045']:.1%}** at 2045 Q4 and **{r['bev_share_end']:.2%}** at 2053 Q4, leaving about **{r['residual_non_bev']:,.0f}** "
                             f"non-BEV vehicles at 2053 Q4; 95% is first reached in **{r.get('reaches_0.95', 'n/a')}**, 99% in **{r.get('reaches_0.99', 'n/a')}** "
                             f"and 99.5% in **{r.get('reaches_0.995', 'n/a')}** (arrival rank {int(r['arrival_rank'])} of {len(rows)}).")
        body = " ".join(parts)
        if humanize:
            body = humanize_answer(body, metadata={"model": "age-structured turnover"})
        return (f"### {', '.join(n for n, _ in lads[:3])}: age-structured turnover trajectory\n\n{body}\n\n"
                f"*A ceiling, not a forecast: every new private vehicle from the ban onward is assumed to be a BEV.*\n\n**Sources:** {md_links(src)}"
                + _method_footer(kg, fam))
    if "ceiling" in q or "scrappage" in q or "wales" in q or "sensitiv" in q:
        body = md_table([{"Median scrappage age (years)": c["median_scrappage_years"], "Implied annual replacement (%)": c["implied_annual_replacement_pct"],
                          "Wales BEV share 2045 Q4": f"{c['bev_share_2045']:.2%}", "Residual non-BEV vehicles": c["residual_non_bev"]} for c in ceilings]) if ceilings else "_no ceilings loaded_"
        return (f"### Wales fleet-turnover ceiling at 2045 Q4 under a 2032 Q4 phase-out\n\n{body}\n\n"
                f"The scrappage curve, not the ban date, controls the 2045 outcome: moving the ban by two years shifts the residual by a few tenths "
                f"of a point; moving the median scrappage age by two years shifts it by several points.\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam))
    ordered = sorted(rows, key=lambda r: -(r["residual_non_bev"] or 0)) if "residual" in q else rows
    body = md_table([{"Arrival rank": int(r["arrival_rank"]), "LAD": r["lad_name"], "BEV share 2045 Q4": f"{r['bev_share_2045']:.2%}",
                      "BEV share 2053 Q4": f"{r['bev_share_end']:.2%}", "Residual non-BEV": r["residual_non_bev"],
                      "Reaches 95%": r.get("reaches_0.95", ""), "Reaches 99%": r.get("reaches_0.99", "")} for r in ordered], max_rows=22)
    note = ("After the ban every LAD receives the same inflow, so arrival quarters converge; the residual non-BEV stock separates the LADs far more "
            "sharply than the BEV share does.")
    return f"### Electrification arrival by LAD (2032 phase-out, median scrappage 14 years)\n\n{body}\n\n{note}\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam)


def charging_answer(kg, question, humanize: bool = False):
    fam = "charging"
    rows = kg.charging_assessments()
    if not rows:
        return ("### Charging-provision constraint\n\nThe Stage 8 classification is not in the loaded KG. Run "
                "`python build_prediction_families.py --notebook <companion notebook>` and restart." + _method_footer(kg, fam))
    lads = kg.find_lads_in_text(question)
    src = family_sources(kg, fam)
    if lads:
        parts = []
        for name, _ in lads[:3]:
            r = next((x for x in rows if x["lad_name"] == name), None)
            if r:
                parts.append(f"**{name}** is classed **'{r['constraint_class']}'**: {r['evs_per_charge_point_2045']:.0f} BEVs per public charging device at 2045 "
                             f"(provision adequacy {r['provision_adequacy']:.2f} against the 20-per-device benchmark), diffusion lag {r['lag_years_at_80pc']:+.2f} years"
                             + (f", shortfall of {_fmt(r['charger_shortfall_2045'])} devices" if r.get("charger_shortfall_2045") is not None else "") + ".")
        return f"### {', '.join(n for n, _ in lads[:3])}: charging-provision constraint\n\n{' '.join(parts)}\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam)
    binding = [r for r in rows if "binding" in r["constraint_class"]]
    body = md_table([{"LAD": r["lad_name"], "Class": r["constraint_class"], "BEVs per device 2045": r["evs_per_charge_point_2045"],
                      "Provision adequacy": r["provision_adequacy"], "Lag at 80% (years)": r["lag_years_at_80pc"],
                      "Device shortfall 2045": r.get("charger_shortfall_2045")} for r in rows], max_rows=22)
    return (f"### Where may charging provision be the principal constraint?\n\n**{len(binding)} of {len(rows)}** LADs are classed 'charging plausibly binding' "
            f"(slow diffusion and provision short of the 20-BEVs-per-device benchmark under 5%/yr charger growth): "
            f"{', '.join(r['lad_name'] for r in binding)}.\n\n{body}\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam))


def neural_answer(kg, question, humanize: bool = False):
    fam = "neural"
    src = family_sources(kg, fam)
    q = question.casefold()
    lads = kg.find_lads_in_text(question)
    year = extract_year(question, default=2030)
    if lads:
        rows = kg.prediction_rows(year, "nn-stage6e", lads[0][0], family=fam)
        if rows:
            r = rows[-1]
            return (f"### {lads[0][0]}: neural adoption-ratio forecast\n\nThe Stage 6e network gives a predicted private adoption ratio of "
                    f"**{r['adoption_share']:.2%}** at {r['period']}.\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam))
    m7 = [m for m in kg.model_metrics(fam) if "Table 7" in m.get("note", "")]
    m6 = [m for m in kg.model_metrics(fam) if "Stage 6e" in m.get("note", "")]
    if not (m7 or m6):
        return ("### Neural forecasts\n\nNo neural-network results are in the loaded KG. Run `python build_prediction_families.py` with the companion "
                "notebook (metrics) or its CSV exports (per-LAD forecasts to 2030 Q4)." + _method_footer(kg, fam))
    parts = ["### Scenario-constrained neural and graph neural forecasts"]
    if m7:
        parts.append(f"Table 7, best configuration per approach ({_protocol_label(m7)}):\n\n" + md_table(_metric_table(m7, with_target=True)))
        best = _best_line(kg)
        if best:
            parts.append(best + " Ask *which model is most accurate for chargers (or keepership)?* for the ranking and its reading.")
    if m6:
        parts.append("Stage 6e quarterly adoption-ratio network, walk-forward on first differences (percentage points):\n\n" + md_table(
            [{"Model": m["model"], "MAE (pp)": m["mae"], "RMSE (pp)": m["rmse"], "R2 diff": m["r2"]} for m in m6]))
    fam_d = kg.family(fam) or {}
    parts.append("Per-LAD quarterly neural forecasts to 2030 Q4 are loaded; ask about a LAD to retrieve one." if fam_d.get("predictions")
                 else "No per-LAD network forecast is in the loaded KG: the quarterly notebook evaluates the networks (Stages 13-14) but "
                      "does not roll them forward, so the 2045 scenarios come from the bounded logistic. The metrics above are the "
                      "paper's evaluation results.")
    return "\n\n".join(parts) + f"\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam)


# --------------------------------------------------------------------------- model accuracy
ACCURACY_KEYWORDS = ("most accurate", "accurate", "accuracy", "best model", "which model", "what model", "best predictor",
                     "best approach", "best method", "performs best", "perform best", "most reliable", "backtest", "back-test",
                     "back test", "mae", "rmse", "model comparison", "compare the models", "compare models", "drift",
                     "persistence", "error metric", "lowest error", "smallest error", "how well do the models", "beat",
                     "outperform")


def wants_accuracy(question: str) -> bool:
    q = question.casefold()
    for w in ACCURACY_KEYWORDS:
        # short metric names need a boundary on both sides (Maesteg contains 'mae'); the rest may take suffixes
        tail = r"(?![\w-])" if w in ("mae", "rmse", "drift") else ""
        if re.search(r"(?<![\w-])" + re.escape(w) + tail, q):
            return True
    return False


def accuracy_answer(kg, question, humanize: bool = False):
    """Rank the forecasting approaches by their backtest error (Table 7 + Stage 13) for one or both targets."""
    fam = "neural"
    target = _target_key(question)
    ranking = kg.model_ranking(target) if hasattr(kg, "model_ranking") else {}
    if not ranking:
        return ("### Model accuracy\n\nNo comparable backtest metrics are in the loaded KG. Run `python build_prediction_families.py` "
                "with the executed companion notebook (Stages 13-14 print Table 7)." + _method_footer(kg, fam))
    src = list(family_sources(kg, "neural"))
    for l in family_sources(kg, "diffusion"):
        if l not in src:
            src.append(l)
    first = next(iter(ranking.values()))
    parts = [f"### Which model predicts {' and '.join(ranking)} most accurately?",
             f"All approaches are scored under one protocol ({_protocol_label(first)}; paper Table 7, notebook Stage 14; "
             "the bounded logistic row is the Stage 13 re-run off the released KG). Ranked by MAE:"]
    for t, rows in ranking.items():
        parts.append(f"**{t}**\n\n" + md_table(_metric_table(rows, rank=True)))
        b = rows[0]
        runner = rows[1] if len(rows) > 1 else None
        logi = next((r for r in rows if r["model"].lower().startswith("bounded logistic")), None)
        line = f"Lowest MAE for {t}: **{b['model']}** ({_fmt(b['mae'])})"
        if runner:
            line += f", then {runner['model']} ({_fmt(runner['mae'])}"
            if runner["rmse"] is not None and b["rmse"] is not None and runner["rmse"] < b["rmse"]:
                line += f"; lowest RMSE, {_fmt(runner['rmse'])}"
            line += ")"
        if logi is not None and logi is not b and logi is not runner:
            line += f"; the bounded logistic, the instrument behind the 2045 scenarios, scores {_fmt(logi['mae'])}"
        parts.append(line + ".")
    s13 = kg.logistic_backtest(target) if hasattr(kg, "logistic_backtest") else {}
    if s13:
        rows = [r for rs in s13.values() for r in rs]
        parts.append("Bounded logistic by capacity multiplier (Stage 13; alpha = 6 low, 10 central, 15 high, K = alpha x last "
                     "training observation):\n\n" + md_table(_metric_table(rows, with_target=len(s13) > 1)))
    parts.append("**How to read the ranking.** Persistence + drift (last value plus the mean quarterly change over the preceding "
                 "four quarters) is the strongest one-quarter-ahead predictor, and the scenario-constrained network is the best "
                 "neural model; both track the next quarter closely. Neither can carry a scenario, saturate, or hold up over "
                 "multi-quarter horizons, which is why the paper keeps the bounded logistic as the forecasting instrument for the "
                 "2045 scenarios. The scenario multiplier alpha scales a per-LAD constant that input standardisation removes, so the "
                 "scenario-constrained NN returns identical metrics under every scenario ('any'). Mean R2 averages per-LAD R2 over "
                 "each district's held-out quarters; pooled R2 is computed over all held-out LAD-quarters.")
    if target == "chargers" or target is None:
        parts.append("Note: the loaded KG holds no charger forecast to 2045. Charging enters the 2045 outlook through the "
                     "charging-constraint assessment (Stage 8), which grows each LAD's latest EVCI9001 count at 0, 5 or 12% a year.")
    return "\n\n".join(parts) + f"\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam)


# --------------------------------------------------------------------------- citation audit
def wants_citation_audit(question: str) -> bool:
    q = question.casefold()
    return (any(w in q for w in ("cite", "citation", "provenance", "sourced", "referenced")) and
            any(w in q for w in ("all ", "every", "properly", "complete", "audit", "coverage", "fully", "missing")))


def _licence_label(url: str) -> str:
    u = (url or "").lower()
    if "open-government-licence" in u:
        return "OGL v3.0"
    if "creativecommons.org/licenses/by/4.0" in u:
        return "CC BY 4.0"
    return url or "n/a"


def citation_answer(kg, question):
    a = kg.citation_audit() if hasattr(kg, "citation_audit") else {}
    if not a or a.get("available") is False:
        return "### Citation audit\n\nThe citation audit is not available for the loaded graphs."
    meta = getattr(kg, "_dataset_meta", {})
    ds_lines = []
    for d in a["datasets"]:
        m = meta.get(d["uri"], {})
        cite = m.get("citation") or d["title"]
        link = f" [landing page]({d['landing_page']})" if d.get("landing_page") else ""
        flag = "" if d["complete"] else f" **(missing: {', '.join(d['missing'])})**"
        ds_lines.append(f"- **{d['identifier']}** ({_licence_label(m.get('license', ''))}): {cite}{link}{flag}")
    res_obs = "; ".join(f"{r['class']} {r['total']:,}" + (f" ({r['uncited']} uncited)" if r["uncited"] else "")
                        for r in a["resources"] if r["graph"] == "observed")
    res_pred = "; ".join(f"{r['class']} {r['total']:,}" + (f" ({r['uncited']} uncited)" if r["uncited"] else "")
                         for r in a["resources"] if r["graph"] == "prediction")
    act_lines = "\n".join(f"- {x['label']} ({x['family']}): {x['used']} dataset(s) used"
                          + (", bibliographic citation present" if x["has_citation"] else ", **no bibliographic citation**")
                          + (", paper section recorded" if x["has_paper_section"] else "") for x in a["activities"])
    verdict = ("**Yes.** " if a["complete"] else "**Not completely.** ")
    return (f"### Are all resources cited?\n\n{verdict}Every answer ends with a *Sources* line built from the dataset records "
            f"its statements link to (dcterms:source / prov:wasDerivedFrom, or the prov:Activity's prov:used). Audit of the loaded graphs:\n\n"
            f"- **Dataset records:** {a['datasets_complete']} of {a['datasets_total']} complete (identifier, title, publisher, licence, "
            f"bibliographic citation, landing page).\n"
            f"- **Resources:** {a['resources_uncited']:,} of {a['resources_total']:,} typed resources lack a path to a dataset record. "
            f"Observed graph: {res_obs}. Prediction graph: {res_pred}.\n"
            f"- **Prediction activities:** {len(a['activities']) - a['activities_uncited']} of {len(a['activities'])} cite their input "
            f"datasets and the companion notebook / paper section.\n\n**Dataset citations**\n\n" + "\n".join(ds_lines)
            + f"\n\n**Activities**\n\n{act_lines}\n\n**Ontology:** [CLEETS]({ONTOLOGY})")


def covariates_answer(kg, question, humanize: bool = False):
    fam = "covariates"
    src = family_sources(kg, fam)
    res = kg.covariate_residuals()
    m8 = kg.model_metrics(fam)
    eff = [e for e in kg.covariate_effects() if e["term"] != "intercept"]
    if not (res or m8 or eff):
        return ("### Covariate analysis\n\nNo covariate results are in the loaded KG. Run `python build_prediction_families.py --notebook <companion notebook>`."
                + _method_footer(kg, fam))
    q = question.casefold()
    lads = kg.find_lads_in_text(question)
    parts = ["### Covariate analysis: what population, density and area explain"]
    if eff:
        parts.append("Effect of each covariate on the diffusion **midpoint** in the hierarchical model (quarters per 1 sd; positive = slower): "
                     + "; ".join(f"**{e['term']}** {e['beta_midpoint_q']:+.2f} [{e['lo']:.2f}, {e['hi']:.2f}]" for e in eff) + ".")
    if m8:
        parts.append("Cross-sectional prediction of EVs per 1,000 residents from population, density and area (leave-one-out, Table 8):\n\n"
                     + md_table([{"Model": m["model"], "MAE": m["mae"], "RMSE": m["rmse"], "R2": m["r2"]} for m in sorted(m8, key=lambda x: x["rmse"] or 0)])
                     + "\n\nNo model beats the mean baseline by more than the seed-to-seed spread, so the covariates carry little linear signal about the current share.")
    if res:
        if lads:
            for name, _ in lads[:3]:
                r = next((x for x in res if x["lad_name"] == name), None)
                if r:
                    parts.append(f"**{name}**: observed {r['observed']:.2f} EVs per 1,000 residents against a Ridge covariate prediction of {r['predicted']:.2f} "
                                 f"(residual {r['residual']:+.2f}).")
        else:
            parts.append("LADs adopting furthest below and above what the covariates predict (Ridge residual, EVs per 1,000):\n\n"
                         + md_table([{"LAD": r["lad_name"], "Observed": r["observed"], "Predicted": r["predicted"], "Residual": r["residual"]}
                                     for r in res[:3] + res[-3:]]))
    return "\n\n".join(parts) + f"\n\n**Sources:** {md_links(src)}" + _method_footer(kg, fam)


FAMILY_ANSWERERS = {
    "diffusion": diffusion_answer,
    "hierarchical": hierarchical_answer,
    "turnover": turnover_answer,
    "charging": charging_answer,
    "neural": neural_answer,
    "covariates": covariates_answer,
}


def prediction_answer(kg, question, humanize: bool = False, family: str = None):
    """Route a prediction-mode question to the prediction family it concerns."""
    fam = family or detect_family(question)
    if fam not in FAMILY_ANSWERERS or (hasattr(kg, "family") and kg.family(fam) is None and fam != "diffusion"):
        fam = "diffusion" if fam not in FAMILY_ANSWERERS else fam
    return FAMILY_ANSWERERS[fam](kg, question, humanize=humanize), fam


def actual_answer(kg, question, humanize: bool = False):
    q = question.casefold()
    if "ontology" in q or "what is cleets" in q or (q.startswith("what is") and "knowledge graph" in q):
        return (f"### CLEETS knowledge graph\n\nCLEETS is the knowledge graph that describes the 22 Welsh LADs, their observations (EV keepership, public charging, "
                f"population, density, income deprivation) and the predictions built on them, with the source dataset behind every value. "
                f"Ask *What classes and properties are defined in CLEETS?* for its vocabulary.\n\n**Knowledge graph:** [Open CLEETS]({ONTOLOGY})")

    rows = list(kg.actual_search(question, limit=30))
    if not rows:
        return "I could not find supporting RDF statements for that free-text question. I will not infer an unsupported answer. Try naming the LAD, measure, year, dataset or knowledge-graph concept."

    # Group top evidence by subject and keep the display concise.
    grouped = defaultdict(list)
    for r in rows:
        grouped[(r["subject"], r["subject_label"])].append(r)
    best = list(grouped.items())[:5]
    out = ["### Retrieved KG evidence"]
    all_links = []
    for (subject, label), statements in best:
        out.append(f"\n**{label}**")
        for r in statements[:5]:
            obj = r["object"]
            if obj.startswith("http"):
                obj = f"[{obj}]({obj})"
            out.append(f"- `{r['predicate_label']}` → {obj}")
        all_links.extend(kg.source_links_for_subject(subject, prediction=False))

    body = "\n".join(out)

    if humanize:
        # Humanize only the evidence list, preserve the caveats
        evidence_section = "\n".join(out[:-1])  # Exclude Sources line
        humanized = humanize_answer(evidence_section, metadata={
            "question": question,
            "result_count": len(best)
        })
        body = humanized

    body += f"\n\n**Sources:** {md_links(all_links)}"
    body += "\n\n*The answer above is restricted to retrieved RDF evidence; broader causal claims are not inferred unless represented or explicitly calculated from the KG.*"
    return body


def answer_question_rich(kg, question: str, mode: str = "actual", humanize: bool = False, family: str = None) -> dict:
    """
    Answer a question and return structured output for the dashboard:
        {markdown, kind ('table'|'prediction'|'actual'|'inventory'), family, table, columns, sources}
    """
    q = question.casefold().strip()
    if any(p in q for p in ("show me the data", "data inventory", "what data are available", "list the actual datasets", "how many prediction",
                            "what data do you have", "which prediction types")):
        return {"markdown": inventory_answer(kg, mode), "kind": "inventory", "family": None, "table": None, "columns": None}

    if wants_citation_audit(q):
        return {"markdown": citation_answer(kg, question), "kind": "inventory", "family": None, "table": None, "columns": None}

    if wants_table(q) and not any(w in q for w in ("table 6", "table 7", "table 8", "table 9", "table 10")):
        return table_answer(kg, question, mode)

    if wants_accuracy(q) and family in (None, "neural") and hasattr(kg, "model_ranking") and kg.model_ranking():
        return {"markdown": accuracy_answer(kg, question, humanize=humanize), "kind": "prediction", "family": "neural",
                "table": None, "columns": None}

    if mode == "prediction":
        md, fam = prediction_answer(kg, question, humanize=humanize, family=family)
        return {"markdown": md, "kind": "prediction", "family": fam, "table": None, "columns": None}
    return {"markdown": actual_answer(kg, question, humanize=humanize), "kind": "actual", "family": None, "table": None, "columns": None}


def answer_question(kg, question: str, mode: str = "actual", humanize: bool = False, family: str = None) -> str:
    """
    Answer a free-text question over the CLEETS knowledge graphs (Markdown only).

    Args:
        kg: CLEETSKG instance
        question: free-text question string
        mode: "actual" (observed data) or "prediction" (scenario forecasts)
        humanize: if True, use Claude to rephrase templated prose (tables and citations are never rephrased)
        family: force a prediction family (diffusion, hierarchical, turnover, charging, neural, covariates)
    """
    return answer_question_rich(kg, question, mode=mode, humanize=humanize, family=family)["markdown"]
