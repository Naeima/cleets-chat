#!/usr/bin/env python3
"""Rebuild data/cleets_prediction_kg.ttl from the companion notebook's scenario export.

Inputs (written by the notebook EVAdoptionWalesPredictionsModels, kept in data/notebook_exports):

    diffusion_scenarios_to_2045.csv   one row per scenario, district and quarter: the fitted share of private
                                      cars that are battery electric, the district's turnover path, the reported
                                      share (the lower of the two), whether the path is the lower, and the count
    turnover_path_wales_summary.csv   the definition of each scenario and the Wales path

The adoption share is private battery-electric cars (VEH0142) over private cars (VEH0105). The turnover path is
the share that the sales rule for new cars delivers given observed scrappage (VEH1111) and the age at which cars
enter private keepership (VEH9901, VEH1111). Scenarios: central (legislated sales rule, scrappage rates of 2021
to 2025), low (2030 level of the rule cut to 50%), high (scrappage rates of 2014 to 2019).

For every scenario, district and predicted quarter (2026 Q1 to 2045 Q4) the graph gets one
cleets:EVAdoptionPrediction with the predicted battery-electric cars and share, the petrol and diesel cars that
remain (hybrids included), the fitted curve, the turnover path and whether the reported value is the path. A
Wales total is added per scenario and quarter, and the first quarter at which each district reaches 10%, 25%,
50% and 75% is recorded as a milestone when it falls inside the horizon. Districts are kept from the existing
graph; scenario, prediction and milestone individuals are replaced.

    python tools/build_prediction_kg.py
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, XSD

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from about import PAPER_TITLE  # noqa: E402

EXPORTS = ROOT / "data" / "notebook_exports"
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else EXPORTS / "diffusion_scenarios_to_2045.csv"
KG = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "cleets_prediction_kg.ttl"
C = Namespace("https://w3id.org/def/cleets#"); D = Namespace("https://w3id.org/def/cleets/data#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
SCENARIOS = {"central": (0.80, "2021 to 2025"), "low": (0.50, "2021 to 2025"), "high": (0.80, "2014 to 2019")}   # 2030 level of the sales rule, scrappage period
THRESHOLDS = (0.10, 0.25, 0.50, 0.75)
FIRST, LAST = "2026Q1", "2045Q4"
WALES = D["W92000004"]
USED = ("VEH0105", "VEH0142", "VEH9901", "VEH1111")
NOTEBOOK = "EVAdoptionWalesPredictionsModels24Nov.ipynb"

df = pd.read_csv(SRC)
df = df[(df.period >= FIRST) & (df.period <= LAST)].copy()
assert set(df.scenario) == set(SCENARIOS) and df.code.nunique() == 22 and df.period.nunique() == 80, "unexpected export"
assert df.turnover_share.notna().all() and (df.predicted_adoption_share <= df[["unconstrained_share", "turnover_share"]].min(axis=1) + 1e-12).all()
stock = (df.predicted_bev_count / df.predicted_adoption_share).groupby(df.code).median().round()      # private cars at 2026 Q2 (VEH9901)
df["stock"] = df.code.map(stock)
df["non_bev"] = df.stock - df.predicted_bev_count
summary = pd.read_csv(EXPORTS / "turnover_path_wales_summary.csv").set_index("scenario")

g = Graph(); g.parse(KG, format="turtle")
act = next(g.subjects(RDF.type, PROV.Activity))
codes = sorted(str(g.value(l, C.ladCode)) for l in g.subjects(RDF.type, C.WelshLAD))
assert codes == sorted(df.code.unique()), "districts in the export do not match the graph"

for cls in (C.Scenario, C.EVAdoptionPrediction, C.AdoptionMilestonePrediction):
    for s in list(g.subjects(RDF.type, cls)): g.remove((s, None, None))
for old in ("midpointShiftQuarters", "turnoverCeilingShare", "atTurnoverCeiling", "privateVehicleStock", "medianScrappageYears"):
    g.remove((C[old], None, None))
for prop, label in [
        ("predictedKeepership", "predicted private battery-electric cars"),
        ("predictedAdoptionShare", "predicted share of private cars that are battery electric"),
        ("predictedNonBEVStock", "predicted petrol and diesel cars remaining in private keepership (hybrids included)"),
        ("fittedCurveShare", "share on the fitted diffusion curve, before the turnover path is applied"),
        ("turnoverPathShare", "share on the district's fleet turnover path"),
        ("onTurnoverPath", "the reported prediction is the turnover path (the lower of the path and the fitted curve)"),
        ("privateCarStock", "private cars, held at the 2026 Q2 level (VEH9901)"),
        ("salesShareAt2030", "battery-electric share of new cars in 2030 under the scenario's sales rule"),
        ("scrappageRatesPeriod", "years whose observed scrappage rates the scenario uses")]:
    g.add((C[prop], RDF.type, OWL.DatatypeProperty)); g.set((C[prop], RDFS.label, Literal(label, lang="en")))
g.set((C.terminalTargetShare, RDFS.label, Literal("Wales turnover path at 2045 Q4 under the scenario", lang="en")))
g.set((C.Scenario, RDFS.comment, Literal("A named set of assumptions behind the turnover path: the sales rule for new cars and the scrappage rates.", lang="en")))

# dataset records the predictions cite (copied from the observed graph and its supplements)
obs = Graph()
for name in ("cleets_cskg_enriched.ttl", "cleets_private_cars.ttl", "cleets_car_cohorts.ttl"):
    obs.parse(ROOT / "data" / name, format="turtle")
for d in list(g.subjects(RDF.type, DCAT.Dataset)):
    if str(d).endswith(("dataset/VEH0105", "dataset/VEH0132")): g.remove((d, None, None))
sources = []
for ident in USED:
    d = D[f"dataset/{ident}"]; sources.append(d)
    assert (d, RDF.type, DCAT.Dataset) in obs, f"{ident} has no record in the observed graph"
    g.add((d, RDF.type, DCAT.Dataset)); g.set((d, RDFS.label, Literal(ident)))
    for p in (DCTERMS.identifier, DCTERMS.title, DCTERMS.publisher, DCTERMS.license, DCTERMS.bibliographicCitation, DCAT.landingPage):
        v = obs.value(d, p)
        assert v is not None, f"{ident} lacks {p}"
        g.set((d, p, v))

# activity and the record of the prediction graph itself
g.remove((act, PROV.used, None))
for d in sources: g.add((act, PROV.used, d))
g.set((act, RDFS.label, Literal("Bounded logistic diffusion capped by the fleet turnover path")))
g.set((act, RDFS.comment, Literal(
    "Per-district logistic curves (rate, midpoint) are fitted independently to the quarterly adoption share, private "
    "battery-electric cars (VEH0142) over private cars (VEH0105), 2011 Q4 to 2025 Q4, recency-weighted. The reported "
    "trajectory is the lower, in every predicted quarter, of the district's fitted curve and its own fleet turnover path. "
    "The path is a stock-flow model started from the private cars licensed at 2026 Q2 by fuel and year of first registration "
    "(VEH9901): cars leave at the scrappage rates observed for British cohorts (VEH1111), cars enter private keepership at "
    "the ages at which they do so in each district, new and second hand, and the battery-electric share of new cars rises "
    "from 24.7% in 2026 to 80% in 2030 and 100% in 2035 (new pure petrol and diesel car sales end in 2030; every new car is "
    "zero emission from 2035). Central scenario: this rule with the scrappage rates of 2021 to 2025. Low: the 2030 level cut "
    "to 50%. High: the scrappage rates of 2014 to 2019. Counts are the share multiplied by the district's private cars at "
    "2026 Q2; the petrol and diesel cars remaining, hybrids included, are those cars less the predicted battery-electric cars.")))
g.set((act, PROV.endedAtTime, Literal(datetime.now(timezone.utc).isoformat(timespec="seconds"), datatype=XSD.dateTime)))
g.set((act, C.paperSection, Literal("Sections 4.2 and 4.6 (methods); 5.4, 5.6, 5.7 and 5.8 (results)")))
g.set((act, C.notebookStage, Literal("Sections 6 and 7 of the companion notebook (export in Section 13)")))
g.set((act, DCTERMS.bibliographicCitation, Literal(
    f'Companion notebook to "{PAPER_TITLE}" (manuscript, 2026): {NOTEBOOK}, export diffusion_scenarios_to_2045.csv.', lang="en")))
ds = D["dataset/PredictionKG"]
g.set((ds, DCTERMS.title, Literal("CLEETS Prediction KG: quarterly predictions of private battery-electric cars, their share of private cars and the "
                                  "petrol and diesel cars remaining, by Welsh district to 2045, capped by the fleet turnover path", lang="en")))
g.set((ds, DCTERMS.modified, Literal(datetime.now(timezone.utc).date().isoformat(), datatype=XSD.date)))
g.remove((ds, DCTERMS.source, None))
for d in sources: g.add((ds, DCTERMS.source, d))


def period_node(p):
    y, q = int(p[:4]), int(p[-1]); u = D[f"Period{y}Q{q}"]
    if (u, RDF.type, None) not in g:
        g.add((u, RDF.type, C.Quarter)); g.add((u, RDF.type, C.Time))
        g.add((u, C.year, Literal(y, datatype=XSD.integer))); g.add((u, C.quarter, Literal(q, datatype=XSD.integer)))
        g.add((u, C.yearQuarter, Literal(f"{y}-Q{q}"))); g.add((u, RDFS.label, Literal(f"{y}-Q{q}")))
    return u


def cite(node):
    g.add((node, PROV.wasGeneratedBy, act))
    for u in sources: g.add((node, DCTERMS.source, u))


def assert_pred(node, area, period, scen, share, count, non_bev, fitted, path, on_path, stk):
    g.add((node, RDF.type, C.EVAdoptionPrediction)); g.add((node, C.forLAD, area)); g.add((node, C.forTime, period_node(period)))
    g.add((node, C.scenario, Literal(scen))); g.add((node, C.underScenario, D[f"scenario/{scen}"]))
    g.add((node, C.predictedAdoptionShare, Literal(round(float(share), 6), datatype=XSD.decimal)))
    g.add((node, C.predictedKeepership, Literal(int(round(count)), datatype=XSD.integer)))
    g.add((node, C.predictedNonBEVStock, Literal(int(round(stk)) - int(round(count)), datatype=XSD.integer)))
    g.add((node, C.fittedCurveShare, Literal(round(float(fitted), 6), datatype=XSD.decimal)))
    g.add((node, C.turnoverPathShare, Literal(round(float(path), 6), datatype=XSD.decimal)))
    g.add((node, C.onTurnoverPath, Literal(bool(on_path), datatype=XSD.boolean)))
    g.add((node, C.privateCarStock, Literal(int(round(stk)), datatype=XSD.integer)))
    cite(node)


n_pred = n_ms = 0
for scen, (level, rates) in SCENARIOS.items():
    d = df[df.scenario == scen]
    w = lambda col: (d[col] * d.stock).groupby(d.period).sum()
    tot = pd.DataFrame({"count": d.groupby("period").predicted_bev_count.sum(), "stock": d.groupby("period").stock.sum(),
                        "path": w("turnover_share"), "fitted": w("unconstrained_share"), "on_path": d.groupby("period").capped.all()})
    tot["share"] = tot["count"] / tot.stock; tot["path"] /= tot.stock; tot["fitted"] /= tot.stock
    end = tot.loc[LAST]
    row = summary.loc[scen]
    assert abs(100 * end.path - row["BEV share 2045Q4 (%)"]) < 0.005, f"{scen}: Wales path {100 * end.path:.3f} does not match the notebook summary"
    half = tot.index[tot.share >= 0.5]
    sn = D[f"scenario/{scen}"]
    g.add((sn, RDF.type, C.Scenario)); g.add((sn, RDFS.label, Literal(f"{scen} scenario", lang="en")))
    g.add((sn, C.salesShareAt2030, Literal(level, datatype=XSD.decimal)))
    g.add((sn, C.scrappageRatesPeriod, Literal(rates)))
    cite(sn)
    g.add((sn, C.terminalTargetShare, Literal(round(float(end.path), 4), datatype=XSD.decimal)))
    g.add((sn, RDFS.comment, Literal(
        f"{str(row['definition'])[:1].upper() + str(row['definition'])[1:]}. Each district follows the lower of its fitted diffusion curve and its "
        f"turnover path. The Wales path is {100 * end.path:.2f}% of private cars at 2045 Q4, the predicted Wales share is {100 * end.share:.2f}% "
        f"and Wales reaches 50% in {half[0][:4]} Q{half[0][-1]}.", lang="en")))
    for r in d.itertuples():
        assert_pred(D[f"pred/{scen}/{r.code}/{r.period}"], D[r.code], r.period, scen, r.predicted_adoption_share, r.predicted_bev_count,
                    r.non_bev, r.unconstrained_share, r.turnover_share, r.capped, r.stock); n_pred += 1
    for period, r in tot.iterrows():
        assert_pred(D[f"pred/{scen}/WALES/{period}"], WALES, period, scen, r.share, r["count"], r.stock - r["count"], r.fitted, r.path, r.on_path, r.stock)
    for code, dd in d.groupby("code"):
        dd = dd.sort_values("period")
        for thr in THRESHOLDS:
            hit = dd[dd.predicted_adoption_share >= thr]
            if hit.empty: continue                       # not reached by 2045 Q4 under this scenario
            node = D[f"milestone/{scen}/{code}/{int(100 * thr)}"]
            g.add((node, RDF.type, C.AdoptionMilestonePrediction)); g.add((node, C.forLAD, D[code])); g.add((node, C.forTime, period_node(hit.period.iloc[0])))
            g.add((node, C.thresholdShare, Literal(thr, datatype=XSD.decimal))); g.add((node, C.scenario, Literal(scen)))
            g.add((node, C.underScenario, sn)); cite(node); n_ms += 1
    print(f"{scen:8s} 2030 level {level:.0%}, scrappage of {rates}: Wales path {100 * end.path:.2f}%, predicted share {100 * end.share:.2f}%, "
          f"BEV cars {end['count']:,.0f}, petrol and diesel cars {end.stock - end['count']:,.0f} at {LAST}; 50% in {half[0]}")
g.serialize(destination=KG, format="turtle")
print(f"{n_pred:,} district predictions, {n_ms} milestones, {len(g):,} triples -> {KG}")
