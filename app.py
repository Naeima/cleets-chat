#!/usr/bin/env python3
"""
CLEETS-CHAT: Cited and Hallucination-Free AI with Traceability

Single-entry dashboard:
  * Header with the CLEETS logo (assets/cleets_logo.png) and live KG statistics
  * OpenStreetMap view of the 22 Welsh LADs coloured by an observed, predicted or
    custom-dataset metric (click a district to pre-fill a question and to add it
    to the dataset selection)
  * Free-text question answering over the observed graph (CLEETS-KG-Enriched)
    and the prediction graph, with cited sources
  * Prediction types matching the paper (bounded logistic diffusion scenarios,
    hierarchical diffusion, age-structured turnover, charging constraint,
    scenario-constrained neural / GNN, covariate analysis), each with an
    "ⓘ how was this predicted?" panel
  * Dataset builder: choose columns and LADs, build a per-LAD table from the
    graphs, download it as CSV, plot any column on the map
  * Optional humanisation of templated prose with Claude (ANTHROPIC_API_KEY)
  * Stakeholder scoring of every answer (1-10 + notes) in cleets_feedback.db

Run:
    python app.py                # http://localhost:8050
    PORT=8055 python app.py      # another port
"""

from __future__ import annotations

import os
from urllib.parse import quote
import sqlite3
import time
from datetime import datetime
from pathlib import Path

import pandas as pd
from dotenv import load_dotenv
from dash import ALL, Dash, Input, Output, State, callback, ctx, dcc, html, no_update, dash_table
import plotly.graph_objects as go

from kg_service import CLEETSKG
from about import about_content
try:
    from qa import answer_question_rich, methods_text, family_label
except ImportError:  # qa.py is only a shim; fall back to the engine itself
    from qa_with_humanization import answer_question_rich, methods_text, family_label

load_dotenv()

TITLE = "CLEETS-CHAT: Cited and Hallucination-Free AI with Traceability"
HERE = Path(__file__).parent
TTL = os.getenv("CLEETS_TTL") or os.getenv("KG_OBSERVED") or "cleets_cskg_enriched.ttl"
from kg_service import find_data_file  # noqa: E402
_has_families = any((HERE / d / "cleets_prediction_families.ttl").exists() for d in (".", "data")) or Path("cleets_prediction_families.ttl").exists()
_pred_default = "cleets_prediction_kg.ttl" + (",cleets_prediction_families.ttl" if _has_families else "")
PRED_TTL = os.getenv("PREDICTION_TTL") or os.getenv("KG_PREDICTION") or _pred_default
FEEDBACK_DB = os.getenv("CLEETS_FEEDBACK_DB", "cleets_feedback.db")
LOGO_FILE = HERE / "assets" / "cleets_logo.png"
HAS_API_KEY = bool(os.getenv("ANTHROPIC_API_KEY"))

load_started = time.perf_counter()
kg = CLEETSKG(TTL, PRED_TTL)
load_seconds = time.perf_counter() - load_started
PRED_INV = kg.prediction_inventory()
FORECAST_YEAR = PRED_INV["years"][1] or 2045
FAMILIES = kg.prediction_families()
FAMILY_KEYS = [f["key"] for f in FAMILIES]


# --------------------------------------------------------------------------- feedback store
def init_feedback_db():
    conn = sqlite3.connect(FEEDBACK_DB)
    conn.execute("""
        CREATE TABLE IF NOT EXISTS feedback (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            timestamp TEXT, question TEXT, answer TEXT, score INTEGER,
            mode TEXT, humanized BOOLEAN, lad_clicked TEXT, metric TEXT, notes TEXT
        )""")
    conn.commit()
    conn.close()


def save_feedback(question, answer, score, mode, humanized, lad_clicked=None, metric=None, notes=None) -> bool:
    try:
        conn = sqlite3.connect(FEEDBACK_DB)
        conn.execute(
            "INSERT INTO feedback (timestamp, question, answer, score, mode, humanized, lad_clicked, metric, notes) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (datetime.now().isoformat(timespec="seconds"), question, (answer or "")[:2000], int(score), mode,
             bool(humanized), lad_clicked, metric, notes))
        conn.commit()
        conn.close()
        return True
    except Exception as exc:
        print(f"Error saving feedback: {exc}")
        return False


def feedback_count() -> int:
    try:
        conn = sqlite3.connect(FEEDBACK_DB)
        n = conn.execute("SELECT COUNT(*) FROM feedback").fetchone()[0]
        conn.close()
        return int(n)
    except Exception:
        return 0


init_feedback_db()

# --------------------------------------------------------------------------- content
QUESTION_GROUPS = {
    "actual": {
        "Observed data": [
            "What data are available in CLEETS-KG?",
            "What do you know about Cardiff?",
            "Show Cardiff EV keepership data.",
            "How has Cardiff EV keepership changed over time?",
            "Which LAD has the highest EV keepership?",
            "Which LAD has the most public EV chargers?",
            "Compare Cardiff and Swansea.",
        ],
        "Custom datasets (download or map)": [
            "Give me a table of keepership, charging count, deprivation, population and population density for the 22 LADs.",
            "Extract chargers per 100k residents and income deprivation for all LADs as CSV.",
            "Table of population and EV keepership for Cardiff, Swansea and Newport in 2024.",
        ],
        "Reasoning & comparison": [
            "Which LADs have high EV uptake but relatively low charger provision?",
            "Which LADs have similar populations but different EV uptake?",
            "How does population density relate to EV uptake?",
            "How does income deprivation relate to EV adoption?",
            "Which areas differ most from the Welsh pattern?",
        ],
        "Provenance & knowledge graph": [
            "Where did this number come from?",
            "Which dataset supports this answer?",
            "Are all resources properly cited?",
            "What is the CLEETS knowledge graph?",
            "What classes and properties are defined in CLEETS?",
            "How is Cardiff connected to EV keepership in the KG?",
        ],
    },
    "prediction": {
        "Diffusion scenarios (paper S3.5, Figures 4-5)": [
            f"What is Cardiff's predicted EV keepership in {FORECAST_YEAR} under the central scenario?",
            f"Compare Cardiff across all three scenarios in {FORECAST_YEAR}.",
            f"Which LAD has the highest predicted EV keepership in {FORECAST_YEAR}?",
            f"Summarise Wales in {FORECAST_YEAR} under the high scenario.",
            "When does Cardiff reach 50% and 90% BEV share under the central scenario?",
            "How sensitive is Cardiff to the scenario assumption?",
        ],
        "Hierarchical diffusion (Table 9)": [
            "Which LADs diffuse most slowly?",
            "Which LADs diffuse fastest?",
            "What are Gwynedd's hierarchical diffusion midpoint and rate?",
            "What makes an LAD diffuse late?",
        ],
        "Age-structured turnover, 2032 phase-out (Table 10, Figure 7)": [
            "When does each LAD reach 99% BEV share under the 2032 phase-out?",
            "What is the Wales fleet-turnover ceiling at 2045 under different scrappage ages?",
            "How many non-BEV vehicles remain in Cardiff at 2053 under the turnover scenario?",
            "Which LADs have the largest residual non-BEV stock?",
        ],
        "Charging constraint (research question 2)": [
            "Where may charging provision be the principal constraint?",
            "Is charging provision plausibly binding in Powys?",
        ],
        "Model accuracy: neural, graph neural, drift and logistic backtests (Tables 5-7)": [
            "Which model is most accurate for EV chargers?",
            "Which model is most accurate for EV keepership?",
            "How well does the scenario-constrained neural network perform?",
            "Does the graph neural network beat the bounded logistic?",
        ],
        "Covariate analysis (Table 8)": [
            "How does population density relate to EV uptake?",
            "How does income deprivation relate to EV adoption?",
            "Which LADs adopt above what their covariates predict?",
        ],
        "Custom datasets (download or map)": [
            f"Extract a table of predicted {FORECAST_YEAR} keepership, turnover arrival quarter and charging-constraint class for all LADs.",
            "Give me a dataset of keepership, chargers, deprivation, population and density for Cardiff, Swansea and Newport.",
        ],
        "Evidence & provenance": [
            "What generated this prediction?",
            "Which source datasets were used for this prediction?",
            "Is this observed, calculated or predicted?",
            "What assumptions are behind this prediction?",
            "Which prediction types are loaded?",
            "Are all predictions properly cited?",
        ],
    },
}

MODE_DESCRIPTION = {
    "actual": "Actual Data mode retrieves observed RDF statements, metadata and provenance from CLEETS-KG-Enriched.",
    "prediction": "Prediction mode queries the CLEETS Prediction KG: the paper's prediction types are listed below; "
                  "'Auto' picks the type from the wording of the question.",
}

# Map metrics: key -> (label, kind, argument, unit, colorscale)
MAP_METRICS = {
    "pred_keepership_central": (f"Predicted BEV keepership {FORECAST_YEAR} (diffusion, central)", "pred", "central", "vehicles", "YlOrRd"),
    "pred_keepership_high": (f"Predicted BEV keepership {FORECAST_YEAR} (diffusion, high)", "pred", "high", "vehicles", "OrRd"),
    "pred_keepership_low": (f"Predicted BEV keepership {FORECAST_YEAR} (diffusion, low)", "pred", "low", "vehicles", "Blues"),
    "pred_share_central": (f"Predicted BEV share of private vehicles {FORECAST_YEAR} (diffusion, central)", "share", "central", "%", "Purples"),
    "hier_lag": ("Hierarchical diffusion: lag against Welsh median midpoint (years)", "hier", "lag_vs_median_years", "years", "RdBu"),
    "turnover_residual": ("Turnover scenario: residual non-BEV vehicles at 2053 Q4", "turnover", "residual_non_bev", "vehicles", "Reds"),
    "charging_evs": ("Charging constraint: BEVs per public device at 2045", "charging", "evs_per_charge_point_2045", "BEVs/device", "Oranges"),
    "covariate_residual": ("Covariate residual: EVs per 1,000 residents above/below prediction", "covariates", "residual", "per 1,000", "RdBu"),
    "obs_keepership": ("Observed private BEV keepership (latest quarter)", "obs", "keepership", "vehicles", "YlGnBu"),
    "obs_chargers": ("Observed public charging devices (latest quarter)", "obs", "chargers", "devices", "Greens"),
    "obs_ratio": ("Observed keepers per charger (latest quarter)", "obs", "ratio", "keepers/charger", "Oranges"),
    "obs_chargers_per_100k": ("Observed chargers per 100k residents (latest quarter)", "obs", "chargers_per_100k", "per 100k", "Teal"),
    "obs_deprivation": ("Income deprivation, mean WIMD 2025 decile (1 = most deprived)", "obs", "deprivation", "decile", "RdYlGn"),
    "custom": ("Custom dataset column (use 'Plot on map' in the dataset panel)", "custom", None, "", "Viridis"),
}

# Approximate LAD centroids (lat, lon) for the marker map.
LAD_CENTROIDS = {
    "Isle of Anglesey": (53.27, -4.33), "Gwynedd": (52.93, -3.93), "Conwy": (53.16, -3.75),
    "Denbighshire": (53.08, -3.35), "Flintshire": (53.20, -3.12), "Wrexham": (53.00, -2.95),
    "Ceredigion": (52.25, -4.00), "Pembrokeshire": (51.83, -4.95), "Carmarthenshire": (51.90, -4.10),
    "Swansea": (51.65, -3.98), "Neath Port Talbot": (51.68, -3.72), "Bridgend": (51.52, -3.58),
    "Vale of Glamorgan": (51.43, -3.40), "Cardiff": (51.49, -3.18), "Rhondda Cynon Taf": (51.66, -3.42),
    "Caerphilly": (51.66, -3.20), "Blaenau Gwent": (51.78, -3.18), "Torfaen": (51.70, -3.05),
    "Monmouthshire": (51.78, -2.85), "Newport": (51.58, -2.98), "Powys": (52.30, -3.40),
    "Merthyr Tydfil": (51.75, -3.38),
}

COLORS = {
    "navy": "#12355B", "navy2": "#0B2542", "blue": "#2F6B9A", "sky": "#6FB1E0", "pale": "#EEF5FA",
    "pale2": "#F7FAFC", "text": "#17324D", "muted": "#5B7083", "border": "#D8E5EE", "white": "#FFFFFF",
    "green": "#2E7D32", "amber": "#B26A00",
}

# Banner in the style of the CLEETS Global Center website (cleets-global-center.org): the site blue,
# the logo at the left, the navigation at the right and the light-blue sweep on the right-hand side.
BRAND = {"blue": "#1B75BB", "blue2": "#3283C2", "sweep": "#70A9D5", "dark": "#0F4C8A"}
CLEETS_SITE = "https://cleets-global-center.org/"
_SWEEP_SVG = ("<svg xmlns='http://www.w3.org/2000/svg' width='900' height='120' viewBox='0 0 900 120' "
              "preserveAspectRatio='xMaxYMid slice'>"
              f"<path d='M0,0 H900 V120 H430 C300,120 140,62 0,0 Z' fill='{BRAND['blue2']}'/>"
              f"<path d='M792,0 H900 V120 H872 Z' fill='{BRAND['sweep']}'/></svg>")
SWEEP_URL = "url(\"data:image/svg+xml;utf8," + quote(_SWEEP_SVG) + "\")"
NAV_LINKS = [("About", "#sec-about"), ("Map", "#sec-map"), ("Ask", "#sec-ask"), ("Predictions", "#sec-mode"),
             ("Datasets", "#sec-datasets"), ("Feedback", "#sec-feedback"), ("CLEETS website", CLEETS_SITE)]


app = Dash(__name__, title=TITLE)
server = app.server

app.index_string = """<!DOCTYPE html>
<html>
<head>
{%metas%}<title>{%title%}</title>{%favicon%}{%css%}
<style>
  body { margin: 0; background: #F3F7FA; }
  .cc-btn { transition: background .15s, transform .05s; }
  .cc-btn:hover { filter: brightness(1.06); }
  .cc-btn:active { transform: translateY(1px); }
  .cc-help-q:hover { background: #EEF5FA !important; border-color: #2F6B9A !important; }
  .cc-chip { display: inline-flex; align-items: center; gap: 8px; padding: 7px 14px; border-radius: 999px;
             background: #FFFFFF; border: 1px solid #C9DCEC; font-size: 14px; color: #17324D; }
  .cc-chip b { font-size: 16px; color: #0F4C8A; }
  .cc-banner { position: relative; overflow: hidden; display: flex; align-items: center; justify-content: space-between;
               gap: 24px; min-height: 110px; padding: 12px 34px; border-top: 6px solid #0F4C8A; border-radius: 18px 18px 0 0; }
  .cc-sweep { position: absolute; top: 0; right: 0; bottom: 0; width: 62%; pointer-events: none;
              background-repeat: no-repeat; background-position: right center; background-size: auto 100%; }
  .cc-brand { position: relative; display: flex; align-items: center; gap: 16px; text-decoration: none; color: #fff; }
  .cc-brand img { height: 88px; display: block; }
  .cc-logo-card { background: #fff; padding: 8px 14px; border-radius: 12px; box-shadow: 0 4px 14px rgba(0,0,0,.18); }
  .cc-wm { font-size: 40px; font-weight: 900; letter-spacing: .5px; line-height: 1; }
  .cc-wm-sub { font-size: 13px; font-weight: 700; margin-top: 4px; line-height: 1.25; }
  .cc-nav { position: relative; display: flex; align-items: center; gap: 26px; flex-wrap: wrap; justify-content: flex-end; }
  .cc-nav a { color: #fff; text-decoration: none; font-weight: 700; font-size: 17px; white-space: nowrap; padding: 6px 0;
              border-bottom: 2px solid transparent; }
  .cc-nav a:hover { border-bottom-color: #fff; }
  .cc-titleband { background: linear-gradient(180deg, #EEF5FA 0%, #F7FAFC 100%); border: 1px solid #D8E5EE; border-top: 0;
                  border-radius: 0 0 18px 18px; padding: 22px 34px 20px; color: #17324D; }
  @media (max-width: 860px) { .cc-banner { padding: 12px 18px; } .cc-wm { font-size: 30px; } .cc-nav { gap: 14px; }
                              .cc-nav a { font-size: 15px; } .cc-sweep { width: 45%; } .cc-titleband { padding: 18px; } }
  .cc-grid-2 { display: grid; grid-template-columns: minmax(360px, 2fr) minmax(260px, 1fr); gap: 16px; }
  .cc-grid-3 { display: grid; grid-template-columns: 2fr 1fr 1fr; gap: 16px; }
  .cc-methods table, .cc-answer table { border-collapse: collapse; margin: 8px 0; font-size: 15px; }
  .cc-methods th, .cc-methods td, .cc-answer th, .cc-answer td { border: 1px solid #D8E5EE; padding: 5px 9px; text-align: left; }
  .cc-methods th, .cc-answer th { background: #EEF5FA; }
  .cc-datasets { border-collapse: collapse; width: 100%; font-size: 14px; }
  .cc-datasets th, .cc-datasets td { border: 1px solid #D8E5EE; padding: 6px 9px; text-align: left; vertical-align: top; }
  .cc-datasets th { background: #EEF5FA; }
  .cc-methods blockquote { border-left: 4px solid #6FB1E0; margin: 8px 0; padding: 4px 12px; color: #5B7083; }
  @media (max-width: 860px) { .cc-grid-2, .cc-grid-3 { grid-template-columns: 1fr; } .cc-title { font-size: 26px !important; } }
</style>
</head>
<body>{%app_entry%}<footer>{%config%}{%scripts%}{%renderer%}</footer></body>
</html>"""


# --------------------------------------------------------------------------- helpers
def help_panel(mode: str):
    blocks, index = [], 0
    for heading, questions in QUESTION_GROUPS[mode].items():
        blocks.append(html.H4(heading, style={"margin": "12px 0 8px", "color": COLORS["navy"]}))
        for q in questions:
            blocks.append(html.Button(
                q, id={"type": "help-question", "index": index}, n_clicks=0, className="cc-help-q",
                style={"display": "block", "width": "100%", "textAlign": "left", "padding": "10px 12px",
                       "marginBottom": "7px", "border": f"1px solid {COLORS['border']}", "borderRadius": "10px",
                       "background": COLORS["white"], "cursor": "pointer", "fontSize": "16px", "color": COLORS["text"]}))
            index += 1
    return blocks


def flattened_questions(mode: str):
    return [q for qs in QUESTION_GROUPS[mode].values() for q in qs]


def available_map_metrics():
    opts = []
    for k, (label, kind, arg, unit, scale) in MAP_METRICS.items():
        if kind == "hier" and not kg.hierarchical_params():
            continue
        if kind == "turnover" and not kg.turnover_rows():
            continue
        if kind == "charging" and not kg.charging_assessments():
            continue
        if kind == "covariates" and not kg.covariate_residuals():
            continue
        opts.append({"label": label, "value": k})
    return opts


def metric_values(metric_key: str, custom: dict = None):
    """[(lad, value, period)] for the chosen map metric, read from the KG (or the custom dataset)."""
    label, kind, arg, unit, scale = MAP_METRICS[metric_key]
    out = []
    if kind == "custom":
        for lad, val in (custom or {}).get("values", {}).items():
            if val is not None:
                out.append((lad, float(val), custom.get("period", "")))
        return out
    lookup = {}
    if kind == "hier":
        lookup = {r["lad_name"]: (r[arg], r["midpoint_period"]) for r in kg.hierarchical_params()}
    elif kind == "turnover":
        lookup = {r["lad_name"]: (r[arg], "2053-Q4") for r in kg.turnover_rows()}
    elif kind == "charging":
        lookup = {r["lad_name"]: (r[arg], "2045") for r in kg.charging_assessments()}
    elif kind == "covariates":
        lookup = {r["lad_name"]: (r[arg], "2025-Q2") for r in kg.covariate_residuals()}
    for _, (name, _uri) in kg.lad_map().items():
        if kind in ("pred", "share"):
            rows = kg.prediction_rows(FORECAST_YEAR, arg, name, family="diffusion")
            if rows:
                r = rows[-1]
                val = r["keepership"] if kind == "pred" else (r["adoption_share"] or 0) * 100
                out.append((name, val, r["period"]))
        elif kind == "obs":
            r = kg.latest_observation(name, arg)
            if r and r["value"] is not None:
                out.append((name, r["value"], r["period"]))
        elif name in lookup and lookup[name][0] is not None:
            out.append((name, float(lookup[name][0]), lookup[name][1]))
    return out


def build_map(metric_key: str, custom: dict = None) -> go.Figure:
    metric_key = metric_key if metric_key in MAP_METRICS else "pred_keepership_central"
    label, kind, arg, unit, scale = MAP_METRICS[metric_key]
    if kind == "custom" and custom:
        label = custom.get("label", label); unit = custom.get("unit", "")
    values = metric_values(metric_key, custom)
    names = [v[0] for v in values]
    vals = [v[1] for v in values]
    lat = [LAD_CENTROIDS.get(n, (52.3, -3.6))[0] for n in names]
    lon = [LAD_CENTROIDS.get(n, (52.3, -3.6))[1] for n in names]
    hover = [f"<b>{n}</b><br>{label}<br><b>{v:,.2f}</b> {unit} ({p})<br><i>Click to ask about {n} and add it to the dataset selection</i>"
             for n, v, p in values]
    vmax = max(abs(v) for v in vals) if vals else 1
    sizes = [14 + 26 * (abs(v or 0) / vmax if vmax else 0) for v in vals]
    diverging = scale in ("RdBu",)
    trace_kwargs = dict(
        lat=lat, lon=lon, text=names, mode="markers+text", textposition="top center",
        textfont=dict(size=11, color=COLORS["text"]),
        marker=dict(size=sizes, color=vals, colorscale=scale, showscale=True, opacity=0.85,
                    cmid=0 if diverging else None,
                    colorbar=dict(title=dict(text=unit, side="top"), thickness=14, len=0.55,
                                  x=0.985, xanchor="right", y=0.5,
                                  bgcolor="rgba(255,255,255,.88)", bordercolor=COLORS["border"], borderwidth=1,
                                  outlinewidth=0, tickfont=dict(size=11))),
        hovertext=hover, hoverinfo="text", customdata=names,
    )
    view = dict(style="open-street-map", center=dict(lat=52.42, lon=-3.85), zoom=6.75)
    # Plotly >= 5.24 uses MapLibre traces (Scattermap); older versions use Scattermapbox.
    if hasattr(go, "Scattermap"):
        fig = go.Figure(go.Scattermap(**trace_kwargs))
        fig.update_layout(map=view)
    else:  # pragma: no cover
        fig = go.Figure(go.Scattermapbox(**trace_kwargs))
        fig.update_layout(mapbox=view)
    if not values:
        fig.add_annotation(text="No values to plot for this metric yet", showarrow=False, x=0.5, y=0.5, xref="paper", yref="paper")
    fig.update_layout(
        title=dict(text=f"<b>{label}</b>", x=0.01, xanchor="left", font=dict(size=16, color=COLORS["navy"])),
        height=580, margin=dict(l=0, r=0, t=44, b=0), hovermode="closest",
        paper_bgcolor=COLORS["white"], font=dict(family="Arial, Helvetica, sans-serif"),
    )
    return fig


def logo_block():
    """Logo at the left of the banner. With assets/cleets_logo.png the image is shown in a white card
    (LOGO_CARD=0 puts it directly on the blue); without it, the CLEETS wordmark is drawn in HTML."""
    if LOGO_FILE.exists():
        use_card = os.getenv("LOGO_CARD", "1") != "0"  # white card by default so the logo shows on the blue banner
        img = html.Img(src=app.get_asset_url("cleets_logo.png"), alt="CLEETS logo")
        parts = [html.Div(img, className="cc-logo-card") if use_card else img]
        if os.getenv("SHOW_WORDMARK") == "1":
            parts.append(wordmark())
    else:
        parts = [wordmark()]
    return html.A(parts, href=CLEETS_SITE, target="_blank", className="cc-brand", title="CLEETS Global Center")


def wordmark():
    return html.Div([
        html.Div("CLEETS", className="cc-wm"),
        html.Div("Clean Energy and Equitable Transportation Solutions", className="cc-wm-sub"),
        html.Div("NSF-UKRI Global Center", className="cc-wm-sub"),
    ])


def chip(label, value):
    return html.Span([html.Span(label, style={"opacity": .85}), html.B(value)], className="cc-chip")


def header():
    n_obs = sum(len(kg.observations(n)) for n in kg.lad_names())
    banner = html.Div([
        html.Div(className="cc-sweep", style={"backgroundImage": SWEEP_URL}),
        logo_block(),
        html.Nav([html.A(label, href=href, target="_blank" if href.startswith("http") else None,
                         rel="noopener" if href.startswith("http") else None) for label, href in NAV_LINKS],
                 className="cc-nav"),
    ], className="cc-banner", style={"background": BRAND["blue"], "color": COLORS["white"]})
    title_band = html.Div([
        html.H1(TITLE, className="cc-title",
                style={"margin": "0 0 8px", "fontSize": "30px", "lineHeight": 1.15, "fontWeight": 800, "color": COLORS["navy"]}),
        html.P("Ask free-text questions over observed CLEETS knowledge and prediction resources. Answers remain "
               "evidence-constrained and citable, every prediction explains how it was generated, and every answer can be scored.",
               style={"fontSize": "17px", "maxWidth": "980px", "margin": 0, "lineHeight": 1.45, "color": COLORS["text"]}),
        html.Div([
            chip("Welsh LADs ", f"{len(kg.lad_names())}"),
            chip("Observed triples ", f"{len(kg.observed_kg):,}"),
            chip("Observations ", f"{n_obs:,}"),
            chip("Quarterly forecasts ", f"{PRED_INV['prediction_count']:,}"),
            chip("Prediction types ", f"{len(FAMILIES)}"),
            chip("Scenarios ", " / ".join(PRED_INV["scenarios"]) or "n/a"),
            chip("Horizon ", f"{PRED_INV['years'][0]}–{PRED_INV['years'][1]}"),
            chip("Loaded in ", f"{load_seconds:.1f} s"),
            chip("Humanisation ", "Claude on" if HAS_API_KEY else "off (no API key)"),
            html.Span(id="feedback-chip", children=chip("Scores collected ", f"{feedback_count()}")),
        ], style={"display": "flex", "flexWrap": "wrap", "gap": "8px", "marginTop": "16px"}),
    ], className="cc-titleband")
    return html.Div([banner, title_band], style={"borderRadius": "18px", "boxShadow": "0 10px 30px rgba(18,53,91,.18)"})


def card(children, id_=None, **extra):
    style = {"background": COLORS["white"], "padding": "24px", "borderRadius": "18px",
             "border": f"1px solid {COLORS['border']}", "boxShadow": "0 2px 10px rgba(18,53,91,.05)",
             "scrollMarginTop": "12px"}
    style.update(extra)
    return html.Div(children, style=style, **({"id": id_} if id_ else {}))


def button(label, id_, primary=True, color=None):
    return html.Button(label, id=id_, n_clicks=0, className="cc-btn",
                       style={"fontSize": "17px", "fontWeight": 700, "padding": "11px 20px", "borderRadius": "11px", "cursor": "pointer",
                              "background": (color or COLORS["blue"]) if primary else COLORS["white"],
                              "color": COLORS["white"] if primary else COLORS["navy"],
                              "border": "none" if primary else f"2px solid {COLORS['blue']}"})


def family_options():
    opts = [{"label": " Auto (from the question)", "value": "auto"}]
    for f in FAMILIES:
        opts.append({"label": f" {family_label(kg, f['key'])}", "value": f["key"]})
    return opts


def dataset_table_component(rows):
    if not rows:
        return html.Div("No table yet.", style={"color": COLORS["muted"]})
    df = pd.DataFrame(rows)
    show_cols = [c for c in df.columns if not c.endswith(" period")]
    return dash_table.DataTable(
        data=df[show_cols].to_dict("records"),
        columns=[{"name": c, "id": c} for c in show_cols],
        sort_action="native", filter_action="native", page_size=25,
        style_table={"overflowX": "auto"},
        style_cell={"fontFamily": "Arial, Helvetica, sans-serif", "fontSize": "14px", "padding": "6px 10px", "textAlign": "left",
                    "minWidth": "90px", "maxWidth": "260px", "whiteSpace": "normal"},
        style_header={"backgroundColor": COLORS["pale"], "fontWeight": 700, "border": f"1px solid {COLORS['border']}"},
        style_data={"border": f"1px solid {COLORS['border']}"},
    )


def numeric_columns(rows):
    if not rows:
        return []
    df = pd.DataFrame(rows)
    return [c for c in df.columns if c not in ("LAD", "LAD code") and not c.endswith(" period")
            and pd.to_numeric(df[c], errors="coerce").notna().sum() >= 3]


def about_card():
    """About CLEETS-CHAT: what it does, the datasets it integrates (read from the graph), the ontology-based
    design and how it scales. Text in about.py."""
    c = about_content(kg)
    cols = ["Dataset", "Publisher", "Licence", "Role", "Measures supplied", "Coverage"]
    head = html.Tr([html.Th(x) for x in cols])
    body = []
    for r in c["datasets"]:
        first = html.A(r["Dataset"], href=r["Landing page"], target="_blank", rel="noopener") if r["Landing page"] else r["Dataset"]
        body.append(html.Tr([html.Td(first, title=r["Title"])] + [html.Td(str(r[k])) for k in cols[1:]]))
    children = [
        html.Div("About CLEETS-CHAT", style={"fontSize": "21px", "fontWeight": 700}),
        html.P(c["lead"], style={"fontSize": "16px", "lineHeight": 1.55, "margin": "8px 0 0"}),
    ]
    for title, text in c["sections"]:
        children.append(html.Div(title, style={"fontSize": "17px", "fontWeight": 700, "margin": "16px 0 4px", "color": COLORS["navy"]}))
        children.append(html.P(text, style={"fontSize": "15px", "lineHeight": 1.55, "margin": 0}))
        if title.startswith("Datasets"):
            children.append(html.Div(html.Table([html.Thead(head), html.Tbody(body)], className="cc-datasets"),
                                     style={"overflowX": "auto", "marginTop": "10px"}))
    return card(children, id_="sec-about", marginTop="18px")


# --------------------------------------------------------------------------- layout
app.layout = html.Div([
    header(),
    about_card(),

    # Map ---------------------------------------------------------------------------
    card([
        html.Div([
            html.Div([
                html.Div("Map the data", style={"fontSize": "21px", "fontWeight": 700}),
                html.Div("OpenStreetMap view of the 22 Welsh local authority districts. Marker size and colour follow the selected "
                         "metric, or any column of a custom dataset. Click a district to pre-fill a question and add it to the dataset selection.",
                         style={"fontSize": "15px", "color": COLORS["muted"], "marginTop": "4px"}),
            ], style={"flex": "1 1 420px"}),
            html.Div([
                html.Label("Metric", htmlFor="map-metric", style={"fontWeight": 700, "fontSize": "15px"}),
                dcc.Dropdown(id="map-metric", clearable=False, value="pred_keepership_central",
                             options=available_map_metrics(), style={"fontSize": "15px", "marginTop": "4px"}),
            ], style={"flex": "1 1 380px"}),
        ], style={"display": "flex", "gap": "18px", "flexWrap": "wrap", "alignItems": "flex-end", "marginBottom": "12px"}),
        dcc.Loading(dcc.Graph(id="lad-map", figure=build_map("pred_keepership_central"),
                              config={"displaylogo": False, "scrollZoom": True},
                              style={"borderRadius": "14px", "overflow": "hidden", "border": f"1px solid {COLORS['border']}"}),
                    type="circle", color=COLORS["blue"]),
    ], id_="sec-map", marginTop="18px"),

    # Mode + prediction type + answer style ---------------------------------------------
    html.Div([
        html.Div([
            html.Div("Query mode", style={"fontSize": "18px", "fontWeight": 700, "marginBottom": "10px"}),
            dcc.RadioItems(id="mode-switch",
                           options=[{"label": " Actual Data", "value": "actual"}, {"label": " Predictions", "value": "prediction"}],
                           value="prediction", inline=True, inputStyle={"marginRight": "8px", "transform": "scale(1.25)"},
                           labelStyle={"fontSize": "19px", "fontWeight": 700, "marginRight": "24px"}),
            html.Div(id="mode-description", children=MODE_DESCRIPTION["prediction"],
                     style={"fontSize": "16px", "color": COLORS["muted"], "marginTop": "9px"}),
            html.Div([
                html.Div("Prediction type (as in the paper)", style={"fontSize": "16px", "fontWeight": 700, "margin": "14px 0 6px"}),
                dcc.RadioItems(id="family-switch", options=family_options(), value="auto",
                               inputStyle={"marginRight": "6px"}, labelStyle={"display": "inline-block", "fontSize": "15px", "marginRight": "16px"}),
            ], id="family-block"),
        ], style={"background": COLORS["pale"], "padding": "18px 20px", "borderRadius": "16px", "border": f"1px solid {COLORS['border']}"}),
        html.Div([
            html.Div("Answer style", style={"fontSize": "18px", "fontWeight": 700, "marginBottom": "8px"}),
            dcc.Checklist(id="humanize-toggle",
                          options=[{"label": " Humanise the wording with Claude (figures, tables and citations are kept verbatim)",
                                    "value": "humanize"}],
                          value=["humanize"] if HAS_API_KEY else [],
                          inputStyle={"marginRight": "8px", "transform": "scale(1.2)"},
                          labelStyle={"fontSize": "15px", "lineHeight": 1.4}),
            html.Div("Set ANTHROPIC_API_KEY in .env to enable humanisation." if not HAS_API_KEY
                     else "Humanisation is available. Templated answers are shown when it is switched off.",
                     style={"fontSize": "13px", "color": COLORS["amber"] if not HAS_API_KEY else COLORS["muted"], "marginTop": "6px"}),
        ], style={"padding": "16px 18px", "background": COLORS["white"], "border": f"1px solid {COLORS['border']}", "borderRadius": "15px"}),
    ], id="sec-mode", className="cc-grid-2", style={"margin": "18px 0", "scrollMarginTop": "12px"}),

    # Question ---------------------------------------------------------------------
    card([
        html.Div([
            html.Label("Ask a free-text question", htmlFor="question", style={"fontSize": "21px", "fontWeight": 700}),
            html.Button("ⓘ", id="help-toggle", n_clicks=0, title="What can I ask?", className="cc-btn",
                        style={"marginLeft": "10px", "width": "34px", "height": "34px", "borderRadius": "50%",
                               "border": f"1px solid {COLORS['blue']}", "background": COLORS["white"], "color": COLORS["blue"],
                               "fontSize": "20px", "fontWeight": 700, "cursor": "pointer"}),
            html.Span(" What can I ask?", style={"fontSize": "15px", "color": COLORS["muted"], "marginLeft": "5px"}),
        ], style={"display": "flex", "alignItems": "center"}),
        html.Div(id="help-panel", children=help_panel("prediction"),
                 style={"display": "none", "marginTop": "12px", "padding": "16px", "background": COLORS["pale2"],
                        "border": f"1px solid {COLORS['border']}", "borderRadius": "14px", "maxHeight": "430px", "overflowY": "auto"}),
        dcc.Textarea(id="question", value=flattened_questions("prediction")[0],
                     placeholder="Ask in your own words: compare Cardiff and Swansea, when does Powys reach 99% BEV share, "
                                 "give me a table of keepership and deprivation for all LADs...",
                     style={"width": "100%", "height": "120px", "boxSizing": "border-box", "fontSize": "19px", "lineHeight": 1.5,
                            "padding": "16px", "border": f"2px solid {COLORS['border']}", "borderRadius": "14px",
                            "marginTop": "12px", "resize": "vertical", "fontFamily": "inherit"}),
        html.Div([
            button("Ask CLEETS-CHAT", "ask"),
            button("Show data inventory", "show-inventory", primary=False),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginTop": "13px"}),
    ], id_="sec-ask"),

    # Answer -----------------------------------------------------------------------
    html.Div([
        dcc.Loading(html.Div(dcc.Markdown(id="answer", link_target="_blank", className="cc-answer",
                                          style={"fontSize": "19px", "lineHeight": 1.7}),
                             id="answer-box", style={"minHeight": "120px"}),
                    type="circle", color=COLORS["blue"]),
        html.Div([
            html.Button("ⓘ  How was this predicted?", id="methods-toggle", n_clicks=0, className="cc-btn",
                        style={"fontSize": "16px", "fontWeight": 700, "padding": "9px 16px", "borderRadius": "10px", "cursor": "pointer",
                               "background": COLORS["white"], "color": COLORS["blue"], "border": f"2px solid {COLORS['blue']}"}),
            html.Div([
                html.Span("Prediction type:", style={"fontSize": "14px", "color": COLORS["muted"], "marginRight": "8px"}),
                dcc.Dropdown(id="methods-family", clearable=False, options=[{"label": family_label(kg, f["key"]), "value": f["key"]} for f in FAMILIES],
                             value=FAMILY_KEYS[0] if FAMILY_KEYS else None, style={"width": "360px", "fontSize": "14px", "display": "inline-block", "verticalAlign": "middle"}),
            ], style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"}),
        ], id="methods-bar", style={"display": "none", "gap": "16px", "alignItems": "center", "flexWrap": "wrap", "marginTop": "14px"}),
        html.Div(dcc.Markdown(id="methods-panel", link_target="_blank", className="cc-methods",
                              style={"fontSize": "16px", "lineHeight": 1.65}),
                 id="methods-box",
                 style={"display": "none", "marginTop": "14px", "padding": "18px 22px", "background": COLORS["white"],
                        "border": f"1px solid {COLORS['sky']}", "borderLeft": f"6px solid {COLORS['sky']}", "borderRadius": "14px"}),
    ], style={"background": COLORS["pale2"], "padding": "27px", "marginTop": "18px", "borderRadius": "18px",
              "border": f"1px solid {COLORS['border']}"}),

    # Dataset builder ------------------------------------------------------------------
    card([
        html.Div("Build a custom dataset from the knowledge graphs", style={"fontSize": "21px", "fontWeight": 700}),
        html.Div("Choose columns and districts, build the table, then download it as CSV or plot any column on the map. "
                 "Tables produced by the chatbot appear here too.",
                 style={"fontSize": "15px", "color": COLORS["muted"], "marginTop": "4px", "marginBottom": "14px"}),
        html.Div([
            html.Div([
                html.Div("Columns", style={"fontWeight": 700, "fontSize": "15px", "marginBottom": "6px"}),
                dcc.Checklist(id="ds-columns", options=[{"label": f" {lbl}", "value": key} for key, lbl in kg.dataset_columns()],
                              value=["keepership", "chargers", "deprivation", "population", "density"],
                              inputStyle={"marginRight": "6px"}, labelStyle={"display": "block", "fontSize": "14px", "lineHeight": 1.7}),
            ]),
            html.Div([
                html.Div("Districts (empty = all 22; map clicks add here)", style={"fontWeight": 700, "fontSize": "15px", "marginBottom": "6px"}),
                dcc.Dropdown(id="ds-lads", multi=True, value=[], placeholder="All Welsh LADs",
                             options=[{"label": n, "value": n} for n in kg.lad_names()], style={"fontSize": "14px"}),
                html.Div("Observation year (optional)", style={"fontWeight": 700, "fontSize": "15px", "margin": "14px 0 6px"}),
                dcc.Input(id="ds-year", type="number", placeholder="latest", min=2009, max=2026, step=1,
                          style={"fontSize": "15px", "padding": "8px 10px", "border": f"2px solid {COLORS['border']}", "borderRadius": "10px", "width": "140px"}),
                html.Div("Latest available value per LAD when left empty.", style={"fontSize": "13px", "color": COLORS["muted"], "marginTop": "4px"}),
            ]),
            html.Div([
                html.Div("Actions", style={"fontWeight": 700, "fontSize": "15px", "marginBottom": "6px"}),
                html.Div([
                    button("Build table", "ds-build"),
                    button("Download CSV", "ds-download", color=COLORS["green"]),
                ], style={"display": "flex", "flexDirection": "column", "gap": "10px"}),
                html.Div("Plot a column on the map", style={"fontWeight": 700, "fontSize": "15px", "margin": "14px 0 6px"}),
                dcc.Dropdown(id="ds-plot-column", placeholder="Choose a numeric column", style={"fontSize": "14px"}),
                html.Div(button("Plot on map", "ds-plot", primary=False), style={"marginTop": "8px"}),
                dcc.Download(id="ds-download-file"),
            ]),
        ], className="cc-grid-3"),
        html.Div(id="ds-status", style={"fontSize": "15px", "color": COLORS["navy"], "fontWeight": 600, "marginTop": "14px"}),
        html.Div(id="ds-table", children=dataset_table_component([]), style={"marginTop": "12px"}),
        html.Div(id="ds-sources", style={"fontSize": "14px", "color": COLORS["muted"], "marginTop": "10px"}),
    ], id_="sec-datasets", marginTop="18px"),

    # Feedback ---------------------------------------------------------------------
    card([
        html.Div("Score this answer", style={"fontSize": "21px", "fontWeight": 700}),
        html.Div("Your score is stored with the question, mode, prediction type and answer so the templates and prompts can be improved "
                 "(1 = unusable, 10 = exactly what I needed).",
                 style={"fontSize": "15px", "color": COLORS["muted"], "marginTop": "4px", "marginBottom": "14px"}),
        dcc.Slider(id="feedback-score", min=1, max=10, step=1, value=7,
                   marks={str(i): {"label": str(i), "style": {"fontSize": "14px"}} for i in range(1, 11)},
                   tooltip={"placement": "bottom", "always_visible": False}),
        dcc.Textarea(id="feedback-notes", value="", placeholder="Optional: what was missing, unclear or wrong?",
                     style={"width": "100%", "height": "70px", "boxSizing": "border-box", "fontSize": "16px", "padding": "12px",
                            "border": f"2px solid {COLORS['border']}", "borderRadius": "12px", "marginTop": "18px",
                            "resize": "vertical", "fontFamily": "inherit"}),
        html.Div([
            button("Submit score", "feedback-submit", color=COLORS["green"]),
            html.Div(id="feedback-status", style={"fontSize": "16px", "fontWeight": 600, "color": COLORS["navy"]}),
        ], style={"display": "flex", "gap": "16px", "alignItems": "center", "flexWrap": "wrap", "marginTop": "12px"}),
    ], id_="sec-feedback", marginTop="18px"),

    html.Div(f"CLEETS-KG-Enriched ({len(kg.observed_kg):,} triples) and CLEETS Prediction KG ({len(kg.prediction_kg):,} triples, "
             f"{len(FAMILIES)} prediction types) · Knowledge graph: https://w3id.org/def/cleets · Feedback database: {FEEDBACK_DB}",
             style={"fontSize": "13px", "color": COLORS["muted"], "textAlign": "center", "marginTop": "22px"}),

    dcc.Store(id="last-answer-store"),
    dcc.Store(id="question-meta-store"),
    dcc.Store(id="dataset-store"),
    dcc.Store(id="map-custom-store"),
], style={"maxWidth": "1200px", "margin": "26px auto", "padding": "0 20px 34px",
          "fontFamily": "Arial, Helvetica, sans-serif", "color": COLORS["text"]})


# --------------------------------------------------------------------------- callbacks
@callback(Output("help-panel", "style"), Input("help-toggle", "n_clicks"), State("help-panel", "style"))
def toggle_help(n, style):
    style = dict(style or {})
    style["display"] = "block" if n and n % 2 else "none"
    return style


@callback(Output("mode-description", "children"), Output("help-panel", "children"), Output("family-block", "style"),
          Input("mode-switch", "value"))
def change_mode(mode):
    return MODE_DESCRIPTION[mode], help_panel(mode), {"display": "block" if mode == "prediction" else "none"}


@callback(Output("lad-map", "figure"), Input("map-metric", "value"), Input("map-custom-store", "data"))
def update_map(metric_key, custom):
    return build_map(metric_key or "pred_keepership_central", custom)


@callback(Output("question", "value"), Output("ds-lads", "value"),
          Input({"type": "help-question", "index": ALL}, "n_clicks"),
          Input("lad-map", "clickData"),
          State("mode-switch", "value"), State("question", "value"), State("ds-lads", "value"),
          prevent_initial_call=True)
def fill_question(_clicks, click_data, mode, current, selected):
    trig = ctx.triggered_id
    selected = list(selected or [])
    if trig == "lad-map":
        if click_data and click_data.get("points"):
            p = click_data["points"][0]
            lad = p.get("customdata") or p.get("text")
            if lad:
                if lad in selected:
                    selected.remove(lad)
                else:
                    selected.append(lad)
                if mode == "prediction":
                    return f"What is {lad}'s predicted EV keepership in {FORECAST_YEAR} under the central scenario?", selected
                return f"What do you know about {lad}?", selected
        return current, no_update
    if isinstance(trig, dict):
        if not any(_clicks or []):
            return current, no_update
        questions = flattened_questions(mode)
        idx = int(trig["index"])
        if 0 <= idx < len(questions):
            return questions[idx], no_update
    return current, no_update


@callback(Output("answer", "children"),
          Output("last-answer-store", "data"),
          Output("question-meta-store", "data"),
          Output("feedback-score", "value"),
          Output("feedback-notes", "value"),
          Output("feedback-status", "children"),
          Output("methods-bar", "style"),
          Output("methods-box", "style"),
          Output("methods-panel", "children"),
          Output("methods-family", "value"),
          Output("dataset-store", "data", allow_duplicate=True),
          Input("ask", "n_clicks"), Input("show-inventory", "n_clicks"),
          State("question", "value"), State("mode-switch", "value"), State("family-switch", "value"),
          State("humanize-toggle", "value"), State("map-metric", "value"),
          prevent_initial_call=True)
def ask_question(_ask, _inv, question, mode, family, humanize_toggle, metric_key):
    hidden = {"display": "none"}
    bar_shown = {"display": "flex", "gap": "16px", "alignItems": "center", "flexWrap": "wrap", "marginTop": "14px"}
    if ctx.triggered_id == "show-inventory":
        question = "Show me the data you have"
    if not question or not question.strip():
        return "Please enter a question.", None, None, 7, "", "", hidden, hidden, "", no_update, no_update
    question = question.strip()
    wants_humanize = "humanize" in (humanize_toggle or [])
    humanize = wants_humanize and HAS_API_KEY
    fam = None if (family in (None, "auto")) else family
    started = time.perf_counter()
    try:
        result = answer_question_rich(kg, question, mode=mode, humanize=humanize, family=fam)
    except Exception as exc:
        return f"### Query error\n\n`{type(exc).__name__}: {exc}`", None, None, 7, "", "", hidden, hidden, "", no_update, no_update
    elapsed = time.perf_counter() - started
    answer = result["markdown"]
    source = "CLEETS-KG-Enriched" if mode == "actual" else "CLEETS Prediction KG"
    note = " Humanisation skipped: ANTHROPIC_API_KEY is not set." if (wants_humanize and not HAS_API_KEY) else ""
    footer = (f"\n\n---\n\n*Mode: {source}. {'Humanised with Claude' if humanize else 'Templated answer'}. "
              f"Retrieved and composed in {elapsed:.2f} seconds.{note}*")
    meta = {"question": question, "mode": mode, "humanized": humanize, "metric": metric_key, "family": result.get("family"),
            "kind": result.get("kind")}
    ans_family = result.get("family")
    if ans_family:
        methods_md = methods_text(kg, ans_family)
        bar, box, fam_value = bar_shown, hidden, ans_family
    else:
        methods_md, bar, box, fam_value = "", hidden, hidden, no_update
    ds = no_update
    if result.get("kind") == "table" and result.get("table"):
        ds = {"rows": result["table"], "columns": result.get("columns"), "title": answer.splitlines()[0].lstrip("# "),
              "sources": result.get("sources", [])}
    return answer + footer, answer, meta, 7, "", "", bar, box, methods_md, fam_value, ds


@callback(Output("methods-box", "style", allow_duplicate=True), Output("methods-panel", "children", allow_duplicate=True),
          Input("methods-toggle", "n_clicks"), Input("methods-family", "value"),
          State("methods-box", "style"), prevent_initial_call=True)
def toggle_methods(n, family, style):
    style = dict(style or {})
    base = {"marginTop": "14px", "padding": "18px 22px", "background": COLORS["white"],
            "border": f"1px solid {COLORS['sky']}", "borderLeft": f"6px solid {COLORS['sky']}", "borderRadius": "14px"}
    if ctx.triggered_id == "methods-toggle":
        shown = style.get("display") != "block"
        base["display"] = "block" if shown else "none"
        return base, methods_text(kg, family) if family else ""
    base["display"] = style.get("display", "none")
    return base, methods_text(kg, family) if family else ""


@callback(Output("dataset-store", "data"), Output("ds-status", "children"),
          Input("ds-build", "n_clicks"),
          State("ds-columns", "value"), State("ds-lads", "value"), State("ds-year", "value"),
          prevent_initial_call=True)
def build_dataset(_n, columns, lads, year):
    columns = columns or []
    if not columns:
        return no_update, "Choose at least one column."
    rows = kg.dataset_table(columns, lads=lads or None, year=int(year) if year else None)
    sources = kg.dataset_sources(columns)
    scope = f"{len(rows)} LADs" if not lads else f"{len(rows)} selected LAD{'s' if len(rows) != 1 else ''}"
    title = f"Custom dataset: {scope}, {len(columns)} column{'s' if len(columns) != 1 else ''}" + (f", year {year}" if year else "")
    return {"rows": rows, "columns": columns, "title": title, "sources": sources}, f"Built {title.lower()}."


@callback(Output("ds-table", "children"), Output("ds-plot-column", "options"), Output("ds-plot-column", "value"),
          Output("ds-sources", "children"), Output("ds-status", "children", allow_duplicate=True),
          Input("dataset-store", "data"), prevent_initial_call=True)
def render_dataset(ds):
    if not ds or not ds.get("rows"):
        return dataset_table_component([]), [], None, "", no_update
    rows = ds["rows"]
    cols = numeric_columns(rows)
    src = ds.get("sources") or []
    src_children = ["Sources: "] + [x for l in src for x in (html.A(l["label"], href=l["url"], target="_blank"), " · ")]
    src_children.append(html.A("CLEETS knowledge graph", href="https://w3id.org/def/cleets", target="_blank"))
    return (dataset_table_component(rows), [{"label": c, "value": c} for c in cols], cols[0] if cols else None,
            src_children, f"{ds.get('title', 'Dataset')} ({len(rows)} rows). Download or plot below.")


@callback(Output("ds-download-file", "data"), Input("ds-download", "n_clicks"), State("dataset-store", "data"), prevent_initial_call=True)
def download_dataset(_n, ds):
    if not ds or not ds.get("rows"):
        return no_update
    df = pd.DataFrame(ds["rows"])
    stamp = datetime.now().strftime("%Y%m%d-%H%M")
    return dcc.send_data_frame(df.to_csv, f"cleets_dataset_{stamp}.csv", index=False)


@callback(Output("map-custom-store", "data"), Output("map-metric", "value"),
          Input("ds-plot", "n_clicks"), State("dataset-store", "data"), State("ds-plot-column", "value"),
          prevent_initial_call=True)
def plot_dataset_column(_n, ds, column):
    if not ds or not ds.get("rows") or not column:
        return no_update, no_update
    df = pd.DataFrame(ds["rows"])
    if column not in df.columns:
        return no_update, no_update
    vals = pd.to_numeric(df[column], errors="coerce")
    values = {lad: (None if pd.isna(v) else float(v)) for lad, v in zip(df["LAD"], vals)}
    period_col = f"{column} period"
    period = str(df[period_col].iloc[0]) if period_col in df.columns and len(df) else "custom dataset"
    return {"label": column, "unit": "", "values": values, "period": period}, "custom"


@callback(Output("feedback-status", "children", allow_duplicate=True),
          Output("feedback-chip", "children"),
          Input("feedback-submit", "n_clicks"),
          State("last-answer-store", "data"), State("question-meta-store", "data"),
          State("feedback-score", "value"), State("feedback-notes", "value"),
          prevent_initial_call=True)
def submit_feedback(_n, last_answer, meta, score, notes):
    if not last_answer or not meta:
        return "Ask a question first, then score the answer.", chip("Scores collected ", f"{feedback_count()}")
    metric = meta.get("metric")
    if meta.get("family"):
        metric = f"{metric or ''}|family={meta['family']}"
    ok = save_feedback(question=meta.get("question", ""), answer=last_answer, score=score or 0,
                       mode=meta.get("mode", ""), humanized=meta.get("humanized", False),
                       metric=metric, notes=(notes or "").strip() or None)
    status = (f"Saved: {score}/10. Thank you." if ok else "Could not save the score; see the terminal for details.")
    return status, chip("Scores collected ", f"{feedback_count()}")


if __name__ == "__main__":
    print("\n" + "=" * 64)
    print(" CLEETS-CHAT")
    print("=" * 64)
    print(f" Observed graph    : {TTL} ({len(kg.observed_kg):,} triples)")
    print(f" Prediction graphs : {PRED_TTL} ({len(kg.prediction_kg):,} triples)")
    print(f" Prediction types  : {', '.join(FAMILY_KEYS) or 'none'}")
    print(f" Logo              : {'assets/cleets_logo.png' if LOGO_FILE.exists() else 'not found (add assets/cleets_logo.png)'}")
    print(f" Humanisation      : {'enabled' if HAS_API_KEY else 'disabled (set ANTHROPIC_API_KEY in .env)'}")
    print(f" Feedback DB       : {FEEDBACK_DB}")
    port = int(os.getenv("PORT", "8050"))
    print(f"\n -> open http://localhost:{port}")
    print("=" * 64 + "\n")
    app.run(debug=os.getenv("DASH_DEBUG", "false").lower() == "true", host=os.getenv("HOST", "127.0.0.1"), port=port)
