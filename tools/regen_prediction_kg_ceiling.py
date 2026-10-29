"""Rebuild data/cleets_prediction_kg.ttl with ceiling-anchored scenario targets.

Recovers each LAD's fitted (rate, midpoint) and stock from the served central
trajectory (exact, since every prediction is logistic(t; r, m+shift) x stock),
re-solves the three midpoint shifts for the new targets with the notebook's
bisection, and rewrites every scenario, prediction and milestone individual
exactly as notebook Stage 15 does. Nothing else in the graph is touched.
"""
import sys, json, numpy as np
from rdflib import Graph, URIRef, Literal, Namespace, RDF, RDFS
from rdflib.namespace import XSD, PROV, DCTERMS

SRC, DST = sys.argv[1], sys.argv[2]
TARGETS = {"low": 0.90, "central": 0.9607, "high": 0.9884}
THRESH = (0.50, 0.90, 0.95)
C = Namespace("https://w3id.org/def/cleets#"); D = Namespace("https://w3id.org/def/cleets/data#")
ORIGIN = (2011, 4); END = (2045, 4)
def qidx(y, q): return (y - ORIGIN[0]) * 4 + (q - ORIGIN[1])
def period_of(i): y, q = ORIGIN; n = (q - 1) + i; return (y + n // 4, n % 4 + 1)
T_END = qidx(*END)

g = Graph(); g.parse(SRC, format="turtle")
old_shift = {str(s).split("/")[-1]: float(g.value(s, C.midpointShiftQuarters)) for s in g.subjects(RDF.type, C.Scenario)}
act = next(g.subjects(RDF.type, PROV.Activity))
src_nodes = sorted({o for s in g.subjects(RDF.type, C.EVAdoptionPrediction) for o in g.objects(s, DCTERMS.source)})
codes = sorted(str(g.value(l, C.ladCode)) for l in g.subjects(RDF.type, C.WelshLAD))
WALES = D["W92000004"]

# recover (r, m, stock) per LAD from the central series
fits = {}
for c in codes:
    pts = []
    for p in g.subjects(RDF.type, C.EVAdoptionPrediction):
        if str(p).startswith(str(D[f"pred/central/{c}/"])):
            t = g.value(p, C.forTime); y = int(g.value(t, C.year)); q = int(g.value(t, C.quarter))
            sh = float(g.value(p, C.predictedAdoptionShare)); k = int(g.value(p, C.predictedKeepership))
            pts.append((qidx(y, q), sh, k))
    pts.sort(); t = np.array([x[0] for x in pts], float); sh = np.array([x[1] for x in pts]); k = np.array([x[2] for x in pts])
    ok = (sh > 1e-4) & (sh < 1 - 1e-4)
    lg = np.log(sh[ok] / (1 - sh[ok])); A = np.vstack([t[ok], np.ones(ok.sum())]).T
    r, b = np.linalg.lstsq(A, lg, rcond=None)[0]; m_shifted = -b / r
    stock = float(np.round(np.median(k[sh > 0.2] / sh[sh > 0.2]) / 100) * 100)
    fits[c] = (r, m_shifted - old_shift["central"], stock)
rates = np.array([fits[c][0] for c in codes]); mids = np.array([fits[c][1] for c in codes]); caps = np.array([fits[c][2] for c in codes])

def logistic(t, r, m): return 1 / (1 + np.exp(np.clip(-r * (np.asarray(t, float) - m), -60, 60)))
def weighted(d): return float((np.array([logistic([T_END], r, m + d)[0] for r, m in zip(rates, mids)]) * caps).sum() / caps.sum())
def solve(target, lo=-200.0, hi=200.0):
    for _ in range(200):
        mid = 0.5 * (lo + hi)
        if weighted(mid) > target: lo = mid
        else: hi = mid
    return 0.5 * (lo + hi)
shifts = {k: solve(v) for k, v in TARGETS.items()}
print("recovered fits (first 3):", {c: tuple(round(x, 4) for x in fits[c]) for c in codes[:3]})
print("shifts:", {k: round(v, 3) for k, v in shifts.items()}, "| unconstrained 2045Q4:", round(100 * weighted(0), 2))

# drop old scenario / prediction / milestone individuals
for cls in (C.Scenario, C.EVAdoptionPrediction, C.AdoptionMilestonePrediction):
    for s in list(g.subjects(RDF.type, cls)):
        g.remove((s, None, None))

scen_nodes = {}
for name, target in TARGETS.items():
    sn = D[f"scenario/{name}"]; sh = shifts[name]
    g.add((sn, RDF.type, C.Scenario)); g.add((sn, RDFS.label, Literal(f"{name} scenario", lang="en")))
    g.add((sn, C.terminalTargetShare, Literal(round(target, 4), datatype=XSD.decimal)))
    g.add((sn, C.midpointShiftQuarters, Literal(round(sh, 3), datatype=XSD.decimal)))
    g.add((sn, RDFS.comment, Literal(f"Wales-wide private BEV penetration constrained to {100*target:.1f}% of the private vehicle stock at 2045 Q4 (midpoint shift {sh:+.2f} quarters).", lang="en")))
    scen_nodes[name] = sn

def period_node(y, q):
    u = D[f"Period{y}Q{q}"]
    if (u, RDF.type, None) not in g:
        g.add((u, RDF.type, C.Quarter)); g.add((u, RDF.type, C.Time))
        g.add((u, C.year, Literal(y, datatype=XSD.integer))); g.add((u, C.quarter, Literal(q, datatype=XSD.integer)))
        g.add((u, C.yearQuarter, Literal(f"{y}-Q{q}"))); g.add((u, RDFS.label, Literal(f"{y}-Q{q}")))
    return u
def assert_pred(node, area, y, q, share, count, scen):
    g.add((node, RDF.type, C.EVAdoptionPrediction)); g.add((node, C.forLAD, area)); g.add((node, C.forTime, period_node(y, q)))
    g.add((node, C.scenario, Literal(scen))); g.add((node, C.underScenario, scen_nodes[scen]))
    g.add((node, C.predictedAdoptionShare, Literal(round(float(share), 6), datatype=XSD.decimal)))
    g.add((node, C.predictedKeepership, Literal(int(round(count)), datatype=XSD.integer)))
    g.add((node, PROV.wasGeneratedBy, act))
    for u in src_nodes: g.add((node, DCTERMS.source, u))

pred_idx = list(range(qidx(2026, 1), T_END + 1)); t_pred = np.array(pred_idx, float)
for scen, sh in shifts.items():
    wales = np.zeros(len(pred_idx))
    for i, c in enumerate(codes):
        shares = logistic(t_pred, rates[i], mids[i] + sh); counts = np.minimum(caps[i], np.maximum(0.0, shares * caps[i])); wales += counts
        for ti, s_, k_ in zip(pred_idx, shares, counts):
            y, q = period_of(ti); assert_pred(D[f"pred/{scen}/{c}/{y}Q{q}"], D[c], y, q, s_, k_, scen)
    ws = wales / caps.sum()
    for ti, s_, k_ in zip(pred_idx, ws, wales):
        y, q = period_of(ti); assert_pred(D[f"pred/{scen}/WALES/{y}Q{q}"], WALES, y, q, s_, k_, scen)

n_ms = 0
for scen, sh in shifts.items():
    for i, c in enumerate(codes):
        for thr in THRESH:
            t = mids[i] + sh + np.log(thr / (1 - thr)) / rates[i]; y, q = period_of(int(np.ceil(t)))
            if y > 2100: continue
            node = D[f"milestone/{scen}/{c}/{int(100*thr)}"]
            g.add((node, RDF.type, C.AdoptionMilestonePrediction)); g.add((node, C.forLAD, D[c])); g.add((node, C.forTime, period_node(y, q)))
            g.add((node, C.thresholdShare, Literal(thr, datatype=XSD.decimal))); g.add((node, C.scenario, Literal(scen)))
            g.add((node, C.underScenario, scen_nodes[scen])); g.add((node, PROV.wasGeneratedBy, act))
            for u in src_nodes: g.add((node, DCTERMS.source, u))
            n_ms += 1
print("milestones:", n_ms, "| triples:", len(g))
g.serialize(destination=DST, format="turtle")
json.dump({"targets": TARGETS, "shifts": shifts, "fits": {c: fits[c] for c in codes}}, open(DST + ".meta.json", "w"), indent=1)
