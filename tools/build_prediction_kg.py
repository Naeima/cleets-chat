#!/usr/bin/env python3
"""Rebuild data/cleets_prediction_kg.ttl from the companion notebook's scenario export.

Input: diffusion_scenarios_to_2045.csv, written by Section 13 of the notebook
(EVAdoptionWalesPredictionsModels). One row per scenario, district and quarter with the
fitted (unconstrained) share, the district's fleet-turnover ceiling, the reported share
(the lower of the two), whether the ceiling binds, and the predicted keepership.

For every scenario (low, central, high = ceilings under 16, 14 and 12-year median
scrappage ages), district and forecast quarter (2026 Q1 to 2045 Q4) the graph gets one
cleets:EVAdoptionPrediction with the predicted keepership and share, the non-battery-electric
stock that remains, the ceiling and whether it binds. A Wales total is added per scenario and
quarter, and the first quarter at which each district reaches 50%, 90% and 95% is recorded as a
milestone when it falls inside the horizon. Districts, datasets and the generating activity
are kept from the existing graph; scenario, prediction and milestone individuals are replaced.

    python tools/build_prediction_kg.py data/notebook_exports/diffusion_scenarios_to_2045.csv
"""
import sys
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd
from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import DCTERMS, OWL, PROV, XSD

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "notebook_exports" / "diffusion_scenarios_to_2045.csv"
KG = Path(sys.argv[2]) if len(sys.argv) > 2 else ROOT / "data" / "cleets_prediction_kg.ttl"
C = Namespace("https://w3id.org/def/cleets#"); D = Namespace("https://w3id.org/def/cleets/data#")
SCRAPPAGE = {"low": 16, "central": 14, "high": 12}       # median scrappage age behind each scenario's ceiling
THRESHOLDS = (0.50, 0.90, 0.95)
FIRST, LAST = "2026Q1", "2045Q4"
WALES = D["W92000004"]

df = pd.read_csv(SRC)
df = df[(df.period >= FIRST) & (df.period <= LAST)].copy()
assert set(df.scenario) == set(SCRAPPAGE) and df.code.nunique() == 22 and df.period.nunique() == 80, "unexpected export"
stock = (df.predicted_bev_count / df.predicted_adoption_share).groupby(df.code).median().round(-2)    # VEH0105 is published to the nearest 100
df["stock"] = df.code.map(stock)
df["non_bev"] = df.stock - df.predicted_bev_count

g = Graph(); g.parse(KG, format="turtle")
act = next(g.subjects(RDF.type, PROV.Activity))
sources = sorted(set(g.objects(act, PROV.used)))
codes = sorted(str(g.value(l, C.ladCode)) for l in g.subjects(RDF.type, C.WelshLAD))
assert codes == sorted(df.code.unique()), "districts in the export do not match the graph"

for cls in (C.Scenario, C.EVAdoptionPrediction, C.AdoptionMilestonePrediction):
    for s in list(g.subjects(RDF.type, cls)): g.remove((s, None, None))
g.remove((C.midpointShiftQuarters, None, None))
for prop, label, kind in [
        ("predictedNonBEVStock", "predicted non-battery-electric private stock remaining", OWL.DatatypeProperty),
        ("turnoverCeilingShare", "fleet-turnover ceiling on the battery-electric share", OWL.DatatypeProperty),
        ("atTurnoverCeiling", "prediction is held at the fleet-turnover ceiling", OWL.DatatypeProperty),
        ("privateVehicleStock", "private vehicle stock (held at its 2025 Q4 level)", OWL.DatatypeProperty),
        ("medianScrappageYears", "median scrappage age in years", OWL.DatatypeProperty)]:
    g.add((C[prop], RDF.type, kind)); g.set((C[prop], RDFS.label, Literal(label, lang="en")))

# activity and dataset record
g.set((act, RDFS.label, Literal("Turnover-constrained bounded logistic diffusion")))
g.set((act, RDFS.comment, Literal(
    "Per-LAD logistic curves (rate, midpoint) fitted independently to the quarterly matched-scope adoption share "
    "(VEH0132 private BEV / VEH0105 private licensed vehicles, all body types), 2011 Q4 to 2025 Q4, recency-weighted. "
    "The reported trajectory is the lower, in every forecast quarter, of the district's fitted curve and its own "
    "fleet-turnover ceiling (age-structured Weibull survival; pure petrol and diesel sales end 2030 Q1, hybrid sales end "
    "2035 Q1). The low, central and high scenarios use the ceiling under 16, 14 and 12-year median scrappage ages. "
    "Counts are the share multiplied by the district's 2025 Q4 private stock; the non-battery-electric stock remaining is "
    "that stock less the predicted keepership.")))
g.set((act, PROV.endedAtTime, Literal(datetime.now(timezone.utc).isoformat(), datatype=XSD.dateTime)))
ds = D["dataset/PredictionKG"]
g.set((ds, DCTERMS.title, Literal("CLEETS Prediction KG: quarterly per-LAD private BEV keepership, share and remaining non-BEV stock for Wales to 2045, turnover-constrained", lang="en")))
g.set((ds, DCTERMS.modified, Literal(datetime.now(timezone.utc).date().isoformat(), datatype=XSD.date)))

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

def assert_pred(node, area, period, scen, share, count, non_bev, ceiling, binds, stk):
    g.add((node, RDF.type, C.EVAdoptionPrediction)); g.add((node, C.forLAD, area)); g.add((node, C.forTime, period_node(period)))
    g.add((node, C.scenario, Literal(scen))); g.add((node, C.underScenario, D[f"scenario/{scen}"]))
    g.add((node, C.predictedAdoptionShare, Literal(round(float(share), 6), datatype=XSD.decimal)))
    g.add((node, C.predictedKeepership, Literal(int(round(count)), datatype=XSD.integer)))
    g.add((node, C.predictedNonBEVStock, Literal(int(round(non_bev)), datatype=XSD.integer)))
    g.add((node, C.turnoverCeilingShare, Literal(round(float(ceiling), 6), datatype=XSD.decimal)))
    g.add((node, C.atTurnoverCeiling, Literal(bool(binds), datatype=XSD.boolean)))
    g.add((node, C.privateVehicleStock, Literal(int(round(stk)), datatype=XSD.integer)))
    cite(node)

n_pred = n_ms = 0
for scen, age in SCRAPPAGE.items():
    d = df[df.scenario == scen]
    tot = d.groupby("period").agg(count=("predicted_bev_count", "sum"), stock=("stock", "sum"),
                                  ceil=("ceiling_share", lambda s: float((s * d.loc[s.index, "stock"]).sum())), binds=("ceiling_binds", "all"))
    tot["share"] = tot["count"] / tot.stock; tot["ceil"] = tot.ceil / tot.stock
    end = tot.loc[LAST]
    sn = D[f"scenario/{scen}"]
    g.add((sn, RDF.type, C.Scenario)); g.add((sn, RDFS.label, Literal(f"{scen} scenario", lang="en")))
    g.add((sn, C.medianScrappageYears, Literal(age, datatype=XSD.decimal)))
    g.add((sn, C.terminalTargetShare, Literal(round(float(end.ceil), 4), datatype=XSD.decimal)))
    g.add((sn, RDFS.comment, Literal(
        f"Each district follows the lower of its fitted diffusion curve and its fleet-turnover ceiling under a {age}-year median "
        f"scrappage age. The Wales ceiling is {100 * end.ceil:.2f}% of the private vehicle stock at 2045 Q4 and the constrained Wales "
        f"share is {100 * end.share:.2f}%.", lang="en")))
    for r in d.itertuples():
        assert_pred(D[f"pred/{scen}/{r.code}/{r.period}"], D[r.code], r.period, scen, r.predicted_adoption_share, r.predicted_bev_count,
                    r.non_bev, r.ceiling_share, r.ceiling_binds, r.stock); n_pred += 1
    for period, r in tot.iterrows():
        assert_pred(D[f"pred/{scen}/WALES/{period}"], WALES, period, scen, r.share, r["count"], r.stock - r["count"], r.ceil, r.binds, r.stock)
    for code, dd in d.groupby("code"):
        dd = dd.sort_values("period")
        for thr in THRESHOLDS:
            hit = dd[dd.predicted_adoption_share >= thr]
            if hit.empty: continue                       # not reached by 2045 Q4 under this scenario
            node = D[f"milestone/{scen}/{code}/{int(100 * thr)}"]
            g.add((node, RDF.type, C.AdoptionMilestonePrediction)); g.add((node, C.forLAD, D[code])); g.add((node, C.forTime, period_node(hit.period.iloc[0])))
            g.add((node, C.thresholdShare, Literal(thr, datatype=XSD.decimal))); g.add((node, C.scenario, Literal(scen)))
            g.add((node, C.underScenario, sn)); cite(node); n_ms += 1
    print(f"{scen:8s} {age}-year median: Wales ceiling {100 * end.ceil:.2f}%, constrained share {100 * end.share:.2f}%, "
          f"BEV {end['count']:,.0f}, non-BEV remaining {end.stock - end['count']:,.0f} at {LAST}")
g.serialize(destination=KG, format="turtle")
print(f"{n_pred:,} district predictions, {n_ms} milestones, {len(g):,} triples -> {KG}")
