#!/usr/bin/env python3
"""Refresh three prediction types in data/cleets_prediction_families.ttl from the companion notebook's exports.

The exports are those of EVAdoptionWalesPredictionsModels (24 November 2026), kept in data/notebook_exports:

    hierarchical   hierarchical_midpoints.csv, hierarchical_covariate_effects.csv
    turnover       turnover_district_inputs_and_results.csv, turnover_path_central_district_quarter.csv,
                   turnover_path_2045_by_scrappage_period.csv, weibull_ceiling_on_cars.csv
    neural         walk_forward_backtests.csv, multi_horizon_backtest.csv (the model comparison of the paper)

Each family's activity and every resource it generated are replaced; nothing is recomputed beyond ranks, lags and
the first quarter at which a district's path reaches a share. The statements that an older build added to the
diffusion activity are removed, because tools/build_prediction_kg.py now writes them. The charging-constraint and
covariate families are left as they are: they come from the September 2026 notebook and are not part of the paper.

    python tools/update_prediction_families.py
"""
import sys
from pathlib import Path

import pandas as pd
from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, XSD

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from about import PAPER_TITLE  # noqa: E402

EXPORTS = ROOT / "data" / "notebook_exports"
KG = ROOT / "data" / "cleets_prediction_families.ttl"
C = Namespace("https://w3id.org/def/cleets#"); D = Namespace("https://w3id.org/def/cleets/data#")
NOTEBOOK = "EVAdoptionWalesPredictionsModels24Nov.ipynb"
DATE = "2026-11-24"
TARGET = "Private battery-electric cars"
COMPARISON_NOTE = ("Model comparison (paper Table 4): rolling-origin one-step-ahead backtest, held-out quarters 2022 Q1 to 2025 Q4, "
                   "352 district-quarters per model; MAE and RMSE in cars")
HORIZON_NOTE = "Multi-horizon backtest (Supplementary Table S8): MAE in cars, rolled forward from the same origins without later data"
MODEL_NAMES = {"Bounded logistic, full history from 2011-Q4 (projection model)": "Bounded logistic, full history from 2011 Q4 (the model behind the predictions)",
               "Bounded logistic, window from 2019-Q4 (as in the table above)": "Bounded logistic, window from 2019 Q4 (as in the one-step comparison)"}

g = Graph(); g.parse(KG, format="turtle")
names = pd.read_csv(EXPORTS / "hierarchical_midpoints.csv").set_index("name").code.to_dict()      # district name -> ONS code


def ds(ident):
    return D[f"dataset/{ident}"]


def drop_family(key):
    for act in [a for a in g.subjects(RDF.type, PROV.Activity) if str(a).rsplit("/", 1)[-1].split("-")[0] == key]:
        for s in list(g.subjects(PROV.wasGeneratedBy, act)): g.remove((s, None, None))
        g.remove((act, None, None))


def activity(key, label, comment, used, paper, stage, exports):
    act = D[f"activity/{key}-{DATE}"]
    g.add((act, RDF.type, PROV.Activity)); g.add((act, RDFS.label, Literal(label, lang="en"))); g.add((act, RDFS.comment, Literal(comment, lang="en")))
    g.add((act, PROV.endedAtTime, Literal(DATE, datatype=XSD.date)))
    for ident in used: g.add((act, PROV.used, ds(ident)))
    g.add((act, C.paperSection, Literal(paper))); g.add((act, C.notebookStage, Literal(stage)))
    g.add((act, DCTERMS.source, Literal(f"notebook exports: {', '.join(exports)}")))
    g.add((act, DCTERMS.bibliographicCitation, Literal(
        f'Companion notebook to "{PAPER_TITLE}" (manuscript, 2026): {NOTEBOOK}, {stage}; paper {paper}. Values taken from: {", ".join(exports)}.', lang="en")))
    return act, [ds(i) for i in used]


def node(uri, cls, act, sources, label=None):
    g.add((uri, RDF.type, cls)); g.add((uri, PROV.wasGeneratedBy, act))
    for d in sources: g.add((uri, DCTERMS.source, d))
    if label: g.add((uri, RDFS.label, Literal(label)))
    return uri


def lit(v, dt=XSD.decimal, nd=4):
    return Literal(int(round(float(v))), datatype=XSD.integer) if dt == XSD.integer else Literal(round(float(v), nd), datatype=dt)


def period_node(p):
    y, q = int(p[:4]), int(p[-1]); u = D[f"Period{y}Q{q}"]
    if (u, RDF.type, None) not in g:
        g.add((u, RDF.type, C.Quarter)); g.add((u, RDF.type, C.Time))
        g.add((u, C.year, Literal(y, datatype=XSD.integer))); g.add((u, C.quarter, Literal(q, datatype=XSD.integer)))
        g.add((u, C.yearQuarter, Literal(f"{y}-Q{q}"))); g.add((u, RDFS.label, Literal(f"{y}-Q{q}")))
    return u


for prop, label in [
        ("bevShare2045", "battery-electric share of private cars at 2045 Q4"), ("bevShareEnd", "battery-electric share of private cars at 2053 Q4"),
        ("residualNonBEV", "petrol and diesel cars remaining in private keepership at 2045 Q4 (hybrids included)"),
        ("impliedAnnualReplacementPct", "cars entering the stock in a year, as a percentage of the stock"),
        ("medianScrappageYears", "median life of a car in years (observed for the turnover path, assumed for the Weibull ceiling)"),
        ("shortfallFrom100pp", "shortfall of the 2045 Q4 share from 100%, in percentage points"),
        ("arrivalRank", "rank of the district by the quarter in which its turnover path reaches 50% (1 = first)"),
        ("bevCarsAtStart", "private battery-electric cars at 2026 Q2 (VEH9901)"), ("bevShareAtStart", "battery-electric share of private cars at 2026 Q2"),
        ("meanAgeYears", "mean age of private cars at 2026 Q2, in years"), ("shareAged15Plus", "share of private cars aged 15 years or more at 2026 Q2"),
        ("firstYearEntryShare", "share of the cars entering private keepership that are in their year of first registration"),
        ("relativeBEVUptake", "battery-electric odds of the district's first-year private cars relative to all UK cars of the vintage"),
        ("bevShare2030", "battery-electric share of private cars on the turnover path at 2030 Q1"),
        ("bevShare2035", "battery-electric share of private cars on the turnover path at 2035 Q1"),
        ("bevShare2040", "battery-electric share of private cars on the turnover path at 2040 Q4"),
        ("turnoverModel", "turnover model behind a Wales-wide result: the turnover path or the Weibull ceiling"),
        ("horizonQuarters", "quarters ahead at which a backtest error is measured")]:
    g.add((C[prop], RDF.type, OWL.DatatypeProperty)); g.set((C[prop], RDFS.label, Literal(label, lang="en")))
g.set((C.TurnoverCeiling, RDFS.comment, Literal("Wales-wide result of a turnover model at 2045 Q4: the turnover path under the scrappage rates of one period, "
                                                  "or the Weibull ceiling under one assumed median life.", lang="en")))
g.set((C.ElectrificationArrival, RDFS.comment, Literal("A district's inputs to the turnover model and its results on the central turnover path.", lang="en")))

# statements that an older build attached to the diffusion activity (now written by tools/build_prediction_kg.py)
for act in [a for a in set(g.subjects()) if str(a).startswith(str(D) + "activity/diffusion")]:
    for s in list(g.subjects(PROV.wasGeneratedBy, act)): g.remove((s, None, None))
    g.remove((act, None, None))

# ------------------------------------------------------------------ hierarchical diffusion
drop_family("hierarchical")
act, src = activity(
    "hierarchical", "Hierarchical diffusion (two-stage empirical Bayes)",
    "Each district's logistic curve is fitted independently to its adoption share (private battery-electric cars over private cars, 2011 Q4 to 2025 Q4); the "
    "fitted midpoint and rate are meta-regressed on standardised population density and population with a DerSimonian-Laird between-district variance, and each "
    "district is shrunk towards the value its covariates predict in proportion to its sampling variance. Intervals come from a parametric bootstrap of 300 "
    "replicates. The estimates describe the fitted curves before the turnover path is applied.",
    ("VEH0105", "VEH0142", "ONSDensity", "StatsWalesPopulation"), "Sections 4.3 and 5.4", "Section 8 of the companion notebook",
    ("hierarchical_midpoints.csv", "hierarchical_covariate_effects.csv"))
h = pd.read_csv(EXPORTS / "hierarchical_midpoints.csv").sort_values("midpoint_quarters", ascending=False).reset_index(drop=True)
median = h.midpoint_quarters.median()
for i, r in h.iterrows():
    s = node(D[f"hier/{r.code}"], C.DiffusionParameterEstimate, act, src, f"{r['name']} hierarchical diffusion parameters")
    g.add((s, C.forLAD, D[r.code])); g.add((s, C.forTime, period_node(r.midpoint_period))); g.add((s, C.midpointPeriod, Literal(str(r.midpoint_period))))
    g.add((s, C.slowestRank, Literal(i + 1, datatype=XSD.integer))); g.add((s, C.lagVsMedianYears, lit((r.midpoint_quarters - median) / 4, nd=3)))
    g.add((s, C.ciWidthYears, lit(r.ci_width_years, nd=3))); g.add((s, C.shrinkageWeight, lit(r.shrinkage_weight, nd=3))); g.add((s, C.ratePerQuarter, lit(r.rate_per_quarter, nd=3)))
for r in pd.read_csv(EXPORTS / "hierarchical_covariate_effects.csv").itertuples():
    s = node(D[f"hier/effect/{r.term}"], C.CovariateEffect, act, src)
    g.add((s, C.covariateTerm, Literal(str(r.term)))); g.add((s, C.betaMidpointQuarters, lit(r.beta_midpoint_quarters, nd=3)))
    g.add((s, C.betaLo, lit(r.lo, nd=3))); g.add((s, C.betaHi, lit(r.hi, nd=3))); g.add((s, C.crossesZero, Literal(bool(r.lo < 0 < r.hi), datatype=XSD.boolean)))
print(f"hierarchical: {len(h)} districts, midpoints {h.midpoint_period.iloc[-1]} to {h.midpoint_period.iloc[0]}, spread {(h.midpoint_quarters.max() - h.midpoint_quarters.min()) / 4:.2f} years")

# ------------------------------------------------------------------ fleet turnover path
drop_family("turnover")
act, src = activity(
    "turnover", "Fleet turnover path from observed scrappage and second-hand entry",
    "A stock-flow model of private cars by district, fuel and year of first registration, started from the cars licensed at 2026 Q2 (VEH9901). Cars leave at the "
    "retention rates observed for British cohorts between year ends (VEH1111; 2021 to 2025 in the central scenario) and are replaced one for one, so each district's "
    "private car stock is held at its 2026 Q2 level. Cars enter private keepership at the ages at which they do so in each district, new and second hand, and "
    "their battery-electric share follows the sales rule for new cars (24.7% in 2026 rising to 80% in 2030 and 100% in 2035), adjusted for the lower uptake of "
    "Welsh private keepers, which converges on the national mix by 2030. The result is a path, an estimate of what the sales rule delivers to the private car "
    "stock, and not an upper bound. The Weibull ceiling (14-year median life, every scrapped car replaced by a new one) is kept as a benchmark.",
    ("VEH9901", "VEH1111", "VEH0142", "VEH0105"), "Sections 4.6 and 5.6 to 5.8; Supplementary Tables S15 to S18", "Sections 6 and 11 of the companion notebook",
    ("turnover_district_inputs_and_results.csv", "turnover_path_central_district_quarter.csv", "turnover_path_2045_by_scrappage_period.csv", "weibull_ceiling_on_cars.csv"))
t = pd.read_csv(EXPORTS / "turnover_district_inputs_and_results.csv")
t["code"] = t.district.map(names)
assert t.code.notna().all() and len(t) == 22
path = pd.read_csv(EXPORTS / "turnover_path_central_district_quarter.csv")
first = lambda code, thr: next(iter(path[(path.code == code) & (path.bev_share >= thr)].sort_values("period").period), None)
t["half"] = [first(c, 0.5) for c in t.code]
assert (t.half == t["reaches 50%"]).all(), "the 50% quarters of the two exports differ"
t = t.sort_values(["half", "BEV share 2045Q4 (%)"], ascending=[True, False]).reset_index(drop=True)
n_ms = 0
for i, r in t.iterrows():
    at = lambda p: path[(path.code == r.code) & (path.period == p)].iloc[0]
    s = node(D[f"turnover/{r.code}"], C.ElectrificationArrival, act, src, f"{r.district}: inputs and results of the central turnover path")
    g.add((s, C.forLAD, D[r.code])); g.add((s, C.scenario, Literal("turnover-path-central"))); g.add((s, C.arrivalRank, Literal(i + 1, datatype=XSD.integer)))
    assert abs(100 * at("2045Q4").bev_share - r["BEV share 2045Q4 (%)"]) < 1e-6
    for prop, v, dt, nd in [("privateCarStock", r["private cars 2026Q2"], XSD.integer, 0), ("bevCarsAtStart", r["BEV cars 2026Q2"], XSD.integer, 0),
                            ("bevShareAtStart", r["BEV share 2026Q2 (%)"] / 100, XSD.decimal, 4), ("meanAgeYears", r["mean age of private cars (years)"], XSD.decimal, 2),
                            ("shareAged15Plus", r["cars aged 15 years or more (%)"] / 100, XSD.decimal, 4),
                            ("firstYearEntryShare", r["first-year cars among cars entering (%)"] / 100, XSD.decimal, 4),
                            ("relativeBEVUptake", r["relative BEV uptake (odds ratio)"], XSD.decimal, 3),
                            ("bevShare2030", r["BEV share 2030Q1 (%)"] / 100, XSD.decimal, 4), ("bevShare2035", r["BEV share 2035Q1 (%)"] / 100, XSD.decimal, 4),
                            ("bevShare2040", r["BEV share 2040Q4 (%)"] / 100, XSD.decimal, 4), ("bevShare2045", r["BEV share 2045Q4 (%)"] / 100, XSD.decimal, 4),
                            ("bevShareEnd", at("2053Q4").bev_share, XSD.decimal, 4), ("residualNonBEV", at("2045Q4").ice_stock, XSD.integer, 0)]:
        g.add((s, C[prop], lit(v, dt, nd)))
    for thr in (0.5, 0.9):
        p = first(r.code, thr)
        if p is None: continue                              # not reached by 2053 Q4
        m = node(D[f"turnover/{r.code}/milestone/{int(1000 * thr)}"], C.AdoptionMilestonePrediction, act, src)
        g.add((m, C.forLAD, D[r.code])); g.add((m, C.forTime, period_node(p))); g.add((m, C.thresholdShare, Literal(thr, datatype=XSD.decimal)))
        g.add((m, C.scenario, Literal("turnover-path-central"))); n_ms += 1
for r in pd.read_csv(EXPORTS / "turnover_path_2045_by_scrappage_period.csv").itertuples(index=False):
    period = str(r[0]); s = node(D[f"turnover/wales/path/{period.replace(' ', '-')}"], C.TurnoverCeiling, act, src, f"Wales turnover path at 2045 Q4, scrappage rates of {period}")
    g.add((s, C.turnoverModel, Literal("turnover path"))); g.add((s, C.scrappageRatesPeriod, Literal(period))); g.add((s, C.medianScrappageYears, lit(r[1], nd=2)))
    g.add((s, C.impliedAnnualReplacementPct, lit(r[3], nd=2))); g.add((s, C.bevShare2045, lit(r[4] / 100))); g.add((s, C.shortfallFrom100pp, lit(r[5], nd=2)))
    g.add((s, C.residualNonBEV, lit(r[6], XSD.integer)))
for r in pd.read_csv(EXPORTS / "weibull_ceiling_on_cars.csv").itertuples(index=False):
    s = node(D[f"turnover/wales/weibull/{r[0]:g}y"], C.TurnoverCeiling, act, src, f"Wales Weibull ceiling at 2045 Q4, {r[0]:g}-year median life")
    g.add((s, C.turnoverModel, Literal("Weibull ceiling"))); g.add((s, C.medianScrappageYears, lit(r[0], nd=1))); g.add((s, C.impliedAnnualReplacementPct, lit(r[1], nd=2)))
    g.add((s, C.bevShare2045, lit(r[5] / 100))); g.add((s, C.shortfallFrom100pp, lit(100 - r[5], nd=2)))
print(f"turnover: {len(t)} districts, 50% between {t.half.min()} and {t.half.max()}, 2045 Q4 share {t['BEV share 2045Q4 (%)'].min():.2f}% to {t['BEV share 2045Q4 (%)'].max():.2f}%, {n_ms} milestones")

# ------------------------------------------------------------------ model comparison (neural and graph neural predictions)
drop_family("neural")
act, src = activity(
    "neural", "Turnover-constrained neural and graph neural predictions (model comparison)",
    "A multilayer perceptron and a two-layer graph convolutional network over a 22-district similarity graph predict the battery-electric share of the cars that "
    "enter private keepership in a district and quarter; the stock follows from the turnover identity, so a prediction cannot grow faster than the entering cars "
    "permit (1.48% of the private car stock each quarter, from the turnover model). They are compared with a bounded logistic, a persistence-with-drift baseline "
    "and an unconstrained perceptron under one rolling-origin protocol: one quarter ahead for every test quarter from 2022 Q1 to 2025 Q4 (352 district-quarters "
    "per model), and rolled forward 1 to 16 quarters from the same origins. The networks are evaluated only; the predictions to 2045 come from the bounded "
    "logistic capped by the turnover path.",
    ("VEH0105", "VEH0142", "VEH9901", "VEH1111"), "Sections 4.4, 4.5 and 5.5; Supplementary Table S8", "Sections 9 and 10 of the companion notebook",
    ("walk_forward_backtests.csv", "multi_horizon_backtest.csv"))
wf = pd.read_csv(EXPORTS / "walk_forward_backtests.csv")
for i, r in wf.iterrows():
    s = node(D[f"neural/metric/comparison/{i}"], C.ModelMetric, act, src)
    g.add((s, C.metricTarget, Literal(TARGET))); g.add((s, C.modelName, Literal(MODEL_NAMES.get(r.model, r.model)))); g.add((s, C.mae, lit(r.MAE, nd=2)))
    g.add((s, C.rmse, lit(r.RMSE, nd=2))); g.add((s, C.r2, lit(r.mean_R2, nd=4))); g.add((s, C.pooledR2, lit(r.pooled_R2, nd=4)))
    g.add((s, C.nPredictions, Literal(int(r.n), datatype=XSD.integer))); g.add((s, C.metricNote, Literal(COMPARISON_NOTE)))
mh = pd.read_csv(EXPORTS / "multi_horizon_backtest.csv")
for i, r in mh.iterrows():
    for col in [c for c in mh.columns if c != "model"]:
        s = node(D[f"neural/metric/horizon/{i}/{col}"], C.ModelMetric, act, src)
        g.add((s, C.metricTarget, Literal(TARGET))); g.add((s, C.modelName, Literal(MODEL_NAMES.get(r.model, r.model)))); g.add((s, C.mae, lit(r[col], nd=2)))
        g.add((s, C.horizonQuarters, Literal(int(col.rstrip("q")), datatype=XSD.integer))); g.add((s, C.metricNote, Literal(HORIZON_NOTE)))
print(f"model comparison: {len(wf)} models one quarter ahead (lowest MAE {wf.MAE.min():.2f}, {wf.model[wf.MAE.idxmin()]}), {len(mh)} models at {len(mh.columns) - 1} horizons")

g.serialize(destination=KG, format="turtle")
print(f"{len(g):,} triples -> {KG}")
