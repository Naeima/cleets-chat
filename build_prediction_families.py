#!/usr/bin/env python3
"""
build_prediction_families.py: add the paper's other prediction types to the
CLEETS Prediction KG so that CLEETS-CHAT can serve them side by side with the
bounded logistic diffusion scenarios.

Families (paper section / companion-notebook stage):
  hierarchical   Hierarchical diffusion, two-stage empirical Bayes   (S2.3.6, S3.5; Stage 11)
  turnover       Age-structured turnover and 2032 phase-out           (S2.3.5, S3.6, S3.8; Stages 7-9)
  charging       Charging-provision constraint classification         (Stage 8, research question 2)
  neural         Scenario-constrained neural / graph neural forecasts (S2.3.2-2.3.4, S3.4.1; Stages 6e, 13-14)
  covariates     Cross-sectional covariate comparison and residuals   (S3.4.2; Stages 4a-bis, 5)

Inputs, in order of preference:
  --csv-dir DIR      the notebook's cleets_out/ exports (full quarterly series)
  --notebook FILE    the executed .ipynb; the tables printed by the stages are
                     parsed from the cell outputs (per-LAD summary tables only)

Output: a Turtle file (default cleets_prediction_families.ttl) using the same
vocabulary as cleets_prediction_kg.ttl: one prov:Activity per family, and
per-LAD resources linked to it with prov:wasGeneratedBy. Load both files in
app.py (PREDICTION_TTL accepts a comma-separated list).

    python build_prediction_families.py --notebook Final_Modelling_CLEETS.ipynb
    python build_prediction_families.py --csv-dir cleets_out --notebook Final_Modelling_CLEETS.ipynb
"""

from __future__ import annotations

import argparse
import io
import json
import re
from datetime import date
from pathlib import Path

import pandas as pd
from rdflib import Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCAT, DCTERMS, OWL, PROV, RDF, RDFS, XSD

CLEETS = Namespace("https://w3id.org/def/cleets#")
DATA = Namespace("https://w3id.org/def/cleets/data#")

# ----------------------------------------------------------------------------- family metadata
FAMILIES = {
    "hierarchical": {
        "label": "Hierarchical diffusion (two-stage empirical Bayes)",
        "comment": ("Stage 11 of the companion notebook (paper S2.3.6, S3.5, Table 9, Figures 4-5). Each LAD's "
                    "logistic curve is fitted independently, the fitted rate and midpoint are meta-regressed on "
                    "standardised covariates (population density, population) with a DerSimonian-Laird between-LAD "
                    "variance, and each LAD is shrunk toward its covariate prediction in proportion to how noisily "
                    "it was estimated. Evaluated on first differences of the adoption share. Outputs: per-LAD "
                    "midpoint period, rate per quarter, 95% interval width, shrinkage weight and lag against the "
                    "Welsh median."),
        "paper": "S2.3.6, S3.5 (Table 9, Figures 4-5)", "stage": "Stage 11",
        "used": ["VEH0105", "VEH0132", "StatsWalesPopulation", "ONSDensity"],
    },
    "turnover": {
        "label": "Age-structured fleet turnover under a 2032 new-sales phase-out",
        "comment": ("Stages 7-9 of the companion notebook (paper S2.3.5, S3.6, S3.8, Table 10, Figures 6-7). New "
                    "non-BEV private registrations decline linearly to zero by 2032 Q4 and all replacement "
                    "registrations are BEV from 2033 Q1; each LAD's private vehicle stock is held at its latest "
                    "VEH0105 value; vehicles retire under a Weibull survival curve calibrated on median scrappage "
                    "age (12, 14 and 16 years; central 14) rather than a constant hazard, and the observed BEV "
                    "vintages are carried forward cohort by cohort to 2053 Q4. The result is a ceiling, not a "
                    "forecast: it assumes every new private vehicle from the ban onward is a BEV. Outputs: BEV "
                    "share at 2045 Q4 and 2053 Q4, residual non-BEV stock, and the first quarter at which 95%, "
                    "99% and 99.5% BEV share is reached."),
        "paper": "S2.3.5, S3.6, S3.8 (Table 10, Figures 6-7)", "stage": "Stages 7-9",
        "used": ["VEH0105", "VEH0132"],
    },
    "charging": {
        "label": "Charging-provision constraint classification (2045)",
        "comment": ("Stage 8, research question 2 of the companion notebook. Each LAD's 2045 BEV count from the "
                    "turnover trajectory is set against public charging devices grown at 5% a year for 20 years "
                    "('slow' scenario) and a benchmark of 20 BEVs per public device. LADs that diffuse slowly AND "
                    "fall short of the benchmark are classed as 'charging plausibly binding'; the rest as "
                    "'provision will bind later'. Sensitivity: frozen, slow and sustained (12%/yr) charger growth "
                    "all leave every LAD below the benchmark. Assumption-driven; not an official forecast."),
        "paper": "Discussion (charging provision), Stage 8 outputs", "stage": "Stage 8",
        "used": ["VEH0105", "VEH0132", "EVCI9001"],
    },
    "neural": {
        "label": "Scenario-constrained neural and graph neural forecasts",
        # Quarterly revision (2026-09): Stage 13 backtests the bounded logistic off the released KG and
        # Stage 14 runs the networks on identical folds, so Table 7 compares all approaches directly.
        "comment": ("Stages 6e, 13 and 14 of the companion notebook, quarterly revision (paper S2.3.2-S2.3.4, "
                    "S3.4.1, Tables 5-7). A multilayer perceptron (quarter index -> level), a scenario-constrained "
                    "perceptron (quarter index and capacity K as inputs), a two-layer graph convolutional network "
                    "over a 22-node LAD similarity graph, its scenario-constrained variant, a persistence-plus-drift "
                    "baseline (last value plus the mean quarterly change over the preceding four quarters) and the "
                    "bounded logistic of Stage 13 are evaluated on one quarterly LAD panel extracted from the released "
                    "KG by SPARQL (Listing 1) under a single rolling-origin one-step-ahead protocol: every quarter from "
                    "2022 Q1 to the end of the panel is held out in turn, the model trains on everything before it, "
                    "only LADs with at least eight training quarters enter a fold, giving 352 held-out LAD-quarters per "
                    "configuration for both targets (private BEV keepership, VEH0132; public charging devices, EVCI9001). "
                    "Scenario capacity follows the revised Equation 2, K = alpha x the last TRAINING observation with "
                    "alpha = 6 (low), 10 (central) and 15 (high), so no post-training value enters any fit. Mean R2 is the "
                    "mean of per-LAD R2; pooled R2 over all held-out LAD-quarters is reported alongside. Stage 6e "
                    "additionally trains a small feed-forward network on the quarterly matched-scope adoption ratio and "
                    "scores it on first differences against persistence and linear drift. Charger counts are excluded as "
                    "adoption features. The printed notebook tables give evaluation metrics only; no network forecast to "
                    "2045 is produced, the bounded logistic remains the forecasting instrument."),
        "comment_annual": ("Stages 6e, 13 and 14 of the companion notebook (paper S2.3.2-S2.3.4, S3.4.1, Tables 5-7). "
                           "A multilayer perceptron, a scenario-constrained perceptron (capacity K = alpha x latest "
                           "stock as an input), a graph neural network over LAD contiguity and its scenario-constrained "
                           "variant are compared with the bounded logistic under one walk-forward protocol (test years "
                           "2023-2025, annual district panel extracted by SPARQL). Stage 6e additionally trains a small "
                           "feed-forward network on the quarterly matched-scope adoption ratio computed inside a single "
                           "SPARQL query, scores it on first differences against persistence and linear-drift baselines, "
                           "and rolls it forward recursively to 2030 Q4 only. Charger counts are deliberately excluded as "
                           "features. Per-LAD forecasts load from nn_adoption_ratio_forecast_2030.csv when available; "
                           "the printed notebook tables give evaluation metrics only."),
        "paper": "S2.3.2-S2.3.4, S3.4.1 (Tables 5-7)", "stage": "Stages 6e, 13, 14",
        "used": ["VEH0105", "VEH0132", "EVCI9001"],
    },
    "covariates": {
        "label": "Cross-sectional covariate comparison (leave-one-out)",
        "comment": ("Stages 4a-bis and 5 of the companion notebook (paper S3.4.2, Table 8). Node features per LAD "
                    "(population, population density, land area; chargers and EV counts are extracted but charger "
                    "features are excluded from the predictors) are used to predict EVs per 1,000 residents at the "
                    "target quarter with a mean baseline, Ridge, Random Forest, Extra Trees, GCN, GAT and GraphSAGE "
                    "under leave-one-out evaluation over the 22 LADs, stochastic models refit under five seeds. The "
                    "seed spread is at least as large as the gap between the best model and the mean baseline, so "
                    "no single winning architecture is reported. Ridge residuals rank which LADs adopt above or "
                    "below what population, density and area alone would predict."),
        "paper": "S3.4.2 (Table 8)", "stage": "Stages 4a-bis, 5",
        "used": ["VEH0132", "EVCI9001", "StatsWalesPopulation", "ONSDensity"],
    },
}

# Extra terms so the new resources are self-describing.
TERMS = {
    "DiffusionParameterEstimate": ("Diffusion parameter estimate", "Per-LAD logistic-curve parameters from the hierarchical model. Not an observed value."),
    "ElectrificationArrival": ("Electrification arrival estimate", "Per-LAD BEV share and residual non-BEV stock from the age-structured turnover trajectory. A ceiling, not an observed value."),
    "ChargingConstraintAssessment": ("Charging-constraint assessment", "Per-LAD classification of whether public charging provision plausibly binds adoption by 2045 under stated assumptions."),
    "CovariateResidual": ("Covariate residual", "Observed adoption minus the cross-sectional Ridge prediction from population, density and area."),
    "ModelMetric": ("Model evaluation metric", "Walk-forward or leave-one-out error metric for one model configuration."),
    "midpointPeriod": ("midpoint period", None), "ratePerQuarter": ("logistic rate per quarter", None),
    "lagVsMedianYears": ("lag against Welsh median midpoint (years)", None), "ciWidthYears": ("95% interval width of the midpoint (years)", None),
    "shrinkageWeight": ("empirical-Bayes shrinkage weight", None), "slowestRank": ("rank, slowest diffusion first", None),
    "arrivalRank": ("arrival rank (earliest first)", None), "bevShare2045": ("BEV share of private stock at 2045 Q4", None),
    "bevShareEnd": ("BEV share of private stock at horizon end (2053 Q4)", None), "residualNonBEV": ("residual non-BEV private vehicles at horizon end", None),
    "reachesShare": ("first quarter at which the threshold share is reached", None),
    "evsPerChargePoint2045": ("BEVs per public charging device at 2045 Q4", None), "provisionAdequacy": ("provision adequacy (benchmark 20 BEVs per device)", None),
    "constraintClass": ("constraint class", None), "lagYearsAt80pc": ("diffusion lag at 80% BEV share (years behind Wales)", None),
    "chargerShortfall2045": ("public charging devices short of the benchmark at 2045", None),
    "observedValue": ("observed value", None), "predictedValue": ("model-predicted value", None), "residual": ("residual (observed minus predicted)", None),
    "metricTarget": ("metric target", None), "modelName": ("model name", None), "mae": ("mean absolute error", None),
    "rmse": ("root mean squared error", None), "r2": ("coefficient of determination", None), "metricNote": ("metric note", None),
    "pooledR2": ("pooled coefficient of determination over all held-out LAD-quarters", None), "nPredictions": ("number of held-out predictions", None),
    "medianScrappageYears": ("median scrappage age (years)", None), "impliedAnnualReplacementPct": ("implied annual replacement (%)", None),
    "shortfallFrom100pp": ("shortfall from 100% (percentage points)", None), "paperSection": ("paper section", None), "notebookStage": ("notebook stage", None),
    "betaMidpointQuarters": ("covariate effect on the midpoint (quarters per 1 sd)", None), "betaLo": ("lower bound", None), "betaHi": ("upper bound", None),
    "betaLogRate": ("covariate effect on log rate", None), "crossesZero": ("interval crosses zero", None), "covariateTerm": ("covariate term", None),
    "CovariateEffect": ("Covariate effect", "Meta-regression coefficient of a covariate on the diffusion midpoint (hierarchical model)."),
    "TurnoverCeiling": ("Turnover ceiling", "Wales-wide BEV share ceiling at 2045 Q4 for one median scrappage age."),
}


# ----------------------------------------------------------------------------- helpers
def _local_name(uri) -> str:
    s = str(uri)
    return s.rsplit("#", 1)[-1].rsplit("/", 1)[-1]


def q_uri(period: str) -> URIRef:
    """'2045Q3' or '2045-Q3' -> data:Period2045Q3 (same pattern as the prediction KG)."""
    m = re.match(r"(\d{4})-?Q([1-4])", str(period).strip())
    if not m:
        raise ValueError(f"bad period {period!r}")
    return DATA[f"Period{m.group(1)}Q{m.group(2)}"]


def ensure_period(g: Graph, period: str):
    t = q_uri(period)
    if (t, RDF.type, CLEETS.Quarter) not in g:
        m = re.match(r"(\d{4})-?Q([1-4])", str(period).strip())
        y, q = int(m.group(1)), int(m.group(2))
        g.add((t, RDF.type, CLEETS.Quarter)); g.add((t, RDF.type, CLEETS.Time))
        g.add((t, RDFS.label, Literal(f"{y}-Q{q}")))
        g.add((t, CLEETS.year, Literal(y, datatype=XSD.integer)))
        g.add((t, CLEETS.quarter, Literal(q, datatype=XSD.integer)))
        g.add((t, CLEETS.yearQuarter, Literal(f"{y}-Q{q}")))
    return t


def lad_lookup(prediction_kg: Graph) -> dict:
    """display name (casefold) -> LAD uri, from the existing prediction KG."""
    out = {}
    for lad in prediction_kg.subjects(RDF.type, CLEETS.WelshLAD):
        label = prediction_kg.value(lad, RDFS.label)
        if label:
            out[str(label).strip().casefold()] = lad
        code = prediction_kg.value(lad, CLEETS.ladCode)
        if code:
            out[str(code).casefold()] = lad
    return out


def read_printed_table(text: str, first_col: str) -> pd.DataFrame | None:
    """Parse a pandas DataFrame printed to a cell output (fixed width).

    Handles the two shapes pandas prints: an unnamed integer index (dropped), or a
    named index whose name sits alone on the line under the header (kept as a column).
    Data rows are the lines up to the first blank line that contain a digit; prose
    lines printed after a table are ignored.
    """
    lines = text.splitlines()
    start = next((i for i, l in enumerate(lines) if first_col in l.split()), None)
    if start is None:
        return None
    header = lines[start]
    rows, index_name = [], None
    for l in lines[start + 1:]:
        if not l.strip():
            break
        if not re.search(r"\d", l):
            if len(l.split()) == 1 and not rows:
                index_name = l.strip()
            continue
        if len(re.findall(r"\s{2,}", l.strip())) < 1 and len(l.split()) > 3:
            break  # prose after the table (single-spaced words)
        rows.append(l)
    if not rows:
        return None
    # Column boundaries = character positions that are blank in the header and every row.
    block = [header] + rows
    width = max(len(l) for l in block)
    block = [l.ljust(width) for l in block]
    blank = [all(l[i] == " " for l in block) for i in range(width)]
    fields, cur = [], None
    for i, b in enumerate(blank):
        if not b and cur is None:
            cur = i
        elif b and cur is not None:
            fields.append((cur, i)); cur = None
    if cur is not None:
        fields.append((cur, width))
    names = [header[a:b].strip() for a, b in fields]
    names = [n if n or i == 0 else f"col{i}" for i, n in enumerate(names)]  # only the first column may be unnamed
    data = [[r[a:b].strip() for a, b in fields] for r in rows]
    df = pd.DataFrame(data, columns=names)
    for c in df.columns:
        try:
            df[c] = pd.to_numeric(df[c])
        except (ValueError, TypeError):
            pass
    first = df.columns[0]
    if first == "":
        col = df[first].astype(str).str.strip()
        if index_name:
            df = df.rename(columns={first: index_name})
        elif col.str.fullmatch(r"\d+").all():
            df = df.drop(columns=[first])  # pandas' positional index
        else:
            df = df.rename(columns={first: "index"})
    return df.reset_index(drop=True)


def cell_outputs(nb) -> list[str]:
    texts = []
    for c in nb["cells"]:
        t = ""
        for o in c.get("outputs", []):
            if o.get("output_type") == "stream":
                t += "".join(o.get("text", []))
            elif o.get("output_type") in ("execute_result", "display_data"):
                t += "".join(o.get("data", {}).get("text/plain", [])) + "\n"
        texts.append(t)
    return texts


def find_output(texts: list[str], marker: str) -> str | None:
    return next((t for t in texts if marker in t), None)


# ----------------------------------------------------------------------------- builders
PAPER_TITLE = "Predicting EV adoption in Wales using Semantic Knowledge Graph"
DATASET_PROPS = (RDFS.label, DCTERMS.identifier, DCTERMS.title, DCTERMS.publisher, DCTERMS.license,
                 DCTERMS.bibliographicCitation, DCTERMS.issued)


class FamilyBuilder:
    def __init__(self, prediction_kg_path: str, observed_kg_path: str = None):
        self.base = Graph()
        self.base.parse(prediction_kg_path, format="turtle")
        self.observed = Graph()
        if observed_kg_path:
            try:
                self.observed.parse(observed_kg_path, format="turtle")
            except Exception as exc:  # citations of datasets outside the prediction KG then stay unresolved
                print(f"warning: could not read {observed_kg_path}: {exc}")
        self.lads = lad_lookup(self.base)
        self.g = Graph()
        for p, ns in (("cleets", CLEETS), ("data", DATA), ("prov", PROV), ("dcterms", DCTERMS), ("dcat", DCAT)):
            self.g.bind(p, ns)
        self._dataset_records_added = set()
        for term, (label, comment) in TERMS.items():
            node = CLEETS[term]
            self.g.add((node, RDF.type, OWL.Class if term[0].isupper() else OWL.DatatypeProperty))
            self.g.add((node, RDFS.label, Literal(label, lang="en")))
            if comment:
                self.g.add((node, RDFS.comment, Literal(comment, lang="en")))
        self.counts = {}

    def lad(self, name) -> URIRef | None:
        return self.lads.get(str(name).strip().casefold())

    def activity(self, key: str, source: str, comment: str = None) -> URIRef:
        meta = FAMILIES[key]
        act = DATA[f"activity/{key}-{date.today().isoformat()}"]
        g = self.g
        g.add((act, RDF.type, PROV.Activity))
        g.add((act, RDFS.label, Literal(meta["label"], lang="en")))
        g.add((act, RDFS.comment, Literal(comment or meta["comment"], lang="en")))
        g.add((act, CLEETS.paperSection, Literal(meta["paper"])))
        g.add((act, CLEETS.notebookStage, Literal(meta["stage"])))
        g.add((act, DCTERMS.source, Literal(source)))
        g.add((act, DCTERMS.bibliographicCitation, Literal(
            f"Companion notebook to \"{PAPER_TITLE}\" (manuscript, 2026), {meta['stage']}; paper {meta['paper']}. "
            f"Values taken from: {source}.", lang="en")))
        g.add((act, PROV.endedAtTime, Literal(date.today().isoformat(), datatype=XSD.date)))
        for ds in meta["used"]:
            node = DATA[f"dataset/{ds}"]
            g.add((act, PROV.used, node))
            self._ensure_dataset_record(node)
        return act

    def _ensure_dataset_record(self, node):
        """Make sure the dcat:Dataset record (identifier, title, publisher, licence, citation, landing
        page) is complete once the prediction KG and this file are loaded together. Records the
        prediction KG lacks are copied from the observed KG; records it carries but leaves incomplete
        (e.g. VEH0105/VEH0132 without dcterms:identifier and dcterms:license) get the missing fields."""
        if node in self._dataset_records_added:
            return
        self._dataset_records_added.add(node)
        in_base = (node, RDF.type, DCAT.Dataset) in self.base
        src = self.observed if (node, RDF.type, DCAT.Dataset) in self.observed else None
        if src is None:
            if not in_base:
                print(f"warning: no dataset record found for {node}; citation will be incomplete")
            return
        if not in_base:
            self.g.add((node, RDF.type, DCAT.Dataset))
        for p in DATASET_PROPS + (DCAT.landingPage,):
            if in_base and self.base.value(node, p) is not None:
                continue
            for o in src.objects(node, p):
                self.g.add((node, p, o))

    # Record of the released prediction KG itself (its dataset node carries only title/licence/created).
    PREDICTION_KG_RECORD = {
        DCTERMS.identifier: Literal("CLEETS-PredictionKG"),
        DCTERMS.publisher: Literal("Cardiff University (CLEETS project)"),
        DCTERMS.bibliographicCitation: Literal(
            "Hamed, N. et al. (2026) CLEETS Prediction KG: quarterly per-LAD private BEV diffusion scenarios for "
            f"Wales to 2045 [Data set]. Companion to \"{PAPER_TITLE}\" (manuscript). https://w3id.org/def/cleets", lang="en"),
        DCAT.landingPage: URIRef("https://w3id.org/def/cleets"),
    }

    def complete_base_citations(self):
        """Close the citation gaps of the released prediction KG without editing that file (RDF merges
        at load time): the KG's own dataset record gets identifier, publisher, citation and landing page;
        dataset records it carries incompletely are completed from the observed KG; the diffusion activity
        gets a bibliographic citation and paper/notebook pointers; and the cleets:Scenario nodes cite the
        activity and the datasets that produced them."""
        g = self.g
        for node in self.base.subjects(RDF.type, DCAT.Dataset):
            if _local_name(node) == "PredictionKG":
                for p, o in self.PREDICTION_KG_RECORD.items():
                    if self.base.value(node, p) is None:
                        g.add((node, p, o))
                continue
            self._ensure_dataset_record(node)
        act = next((a for a in self.base.subjects(RDF.type, PROV.Activity) if _local_name(a).startswith("diffusion")), None)
        if act is None:
            return
        if self.base.value(act, DCTERMS.bibliographicCitation) is None:
            g.add((act, DCTERMS.bibliographicCitation, Literal(
                f"Companion notebook to \"{PAPER_TITLE}\" (manuscript, 2026), Stage 6 (bounded logistic scenario fit) "
                "and Stage 15 (Prediction KG export); paper S2.3.6, S3.4.3, S3.5.", lang="en")))
        if self.base.value(act, CLEETS.paperSection) is None:
            g.add((act, CLEETS.paperSection, Literal("S2.3.6, S3.4.3, S3.5")))
        if self.base.value(act, CLEETS.notebookStage) is None:
            g.add((act, CLEETS.notebookStage, Literal("Stages 6 and 15")))
        used = list(self.base.objects(act, PROV.used))
        for sc in self.base.subjects(RDF.type, CLEETS.Scenario):
            if self.base.value(sc, PROV.wasGeneratedBy) is None:
                g.add((sc, PROV.wasGeneratedBy, act))
            for d in used:
                if (sc, DCTERMS.source, d) not in self.base:
                    g.add((sc, DCTERMS.source, d))

    def _cite(self, s, act):
        """Every per-LAD resource cites its activity and the datasets the activity used."""
        self.add(s, PROV.wasGeneratedBy, act)
        for d in self.g.objects(act, PROV.used):
            self.add(s, DCTERMS.source, d)

    def add(self, s, p, o, dt=None):
        if o is None or (isinstance(o, float) and pd.isna(o)):
            return
        self.g.add((s, p, o if isinstance(o, (URIRef, Literal)) else Literal(o, datatype=dt) if dt else Literal(o)))

    # -- hierarchical (Stage 11) ---------------------------------------------------------
    def hierarchical(self, df: pd.DataFrame, source: str, effects: pd.DataFrame | None = None):
        act = self.activity("hierarchical", source)
        n = 0
        for _, r in df.iterrows():
            lad = self.lad(r["name"])
            if lad is None:
                continue
            s = DATA[f"hier/{lad.split('#')[-1]}"]
            self.add(s, RDF.type, CLEETS.DiffusionParameterEstimate)
            self.add(s, CLEETS.forLAD, lad)
            self._cite(s, act)
            self.add(s, RDFS.label, Literal(f"{r['name']} hierarchical diffusion parameters"))
            self.add(s, CLEETS.forTime, ensure_period(self.g, r["midpoint_period"]))
            self.add(s, CLEETS.midpointPeriod, str(r["midpoint_period"]))
            self.add(s, CLEETS.slowestRank, int(r["slowest_rank"]), XSD.integer)
            self.add(s, CLEETS.lagVsMedianYears, float(r["lag_vs_median_years"]), XSD.decimal)
            self.add(s, CLEETS.ciWidthYears, float(r["ci_width_years"]), XSD.decimal)
            self.add(s, CLEETS.shrinkageWeight, float(r["shrinkage_weight"]), XSD.decimal)
            self.add(s, CLEETS.ratePerQuarter, float(r["rate_per_quarter"]), XSD.decimal)
            n += 1
        if effects is not None:
            for _, r in effects.iterrows():
                s = DATA[f"hier/effect/{r['term']}"]
                self.add(s, RDF.type, CLEETS.CovariateEffect)
                self._cite(s, act)
                self.add(s, CLEETS.covariateTerm, str(r["term"]))
                self.add(s, CLEETS.betaMidpointQuarters, float(r["beta_midpoint_q"]), XSD.decimal)
                self.add(s, CLEETS.betaLo, float(r["lo"]), XSD.decimal)
                self.add(s, CLEETS.betaHi, float(r["hi"]), XSD.decimal)
                self.add(s, CLEETS.betaLogRate, float(r["beta_lograte"]), XSD.decimal)
                self.add(s, CLEETS.crossesZero, str(r["crosses_zero"]).strip().lower() == "true", XSD.boolean)
        self.counts["hierarchical"] = n

    # -- turnover (Stages 7-9) -----------------------------------------------------------
    def turnover(self, arrival: pd.DataFrame, source: str, table10: pd.DataFrame | None = None,
                 trajectories: pd.DataFrame | None = None):
        act = self.activity("turnover", source)
        n = 0
        for _, r in arrival.iterrows():
            lad = self.lad(r["name"])
            if lad is None:
                continue
            code = lad.split('#')[-1]
            s = DATA[f"turnover/{code}"]
            self.add(s, RDF.type, CLEETS.ElectrificationArrival)
            self.add(s, CLEETS.forLAD, lad)
            self._cite(s, act)
            self.add(s, CLEETS.scenario, "ban2032-median14y")
            self.add(s, RDFS.label, Literal(f"{r['name']} age-structured turnover trajectory (2032 phase-out, median scrappage 14 years)"))
            self.add(s, CLEETS.arrivalRank, int(r["arrival_rank"]), XSD.integer)
            self.add(s, CLEETS.bevShare2045, float(r["bev_share_2045_pct"]) / 100.0, XSD.decimal)
            self.add(s, CLEETS.bevShareEnd, float(r["bev_share_end_pct"]) / 100.0, XSD.decimal)
            self.add(s, CLEETS.residualNonBEV, float(r["residual_ice_end"]), XSD.decimal)
            for col, thr in (("reaches_95pc", 0.95), ("reaches_99pc", 0.99), ("reaches_99.5pc", 0.995)):
                if col in arrival.columns and isinstance(r[col], str) and re.match(r"\d{4}Q[1-4]", r[col]):
                    m = DATA[f"turnover/{code}/milestone/{int(thr*1000)}"]
                    self.add(m, RDF.type, CLEETS.AdoptionMilestonePrediction)
                    self.add(m, CLEETS.forLAD, lad)
                    self.add(m, CLEETS.scenario, "ban2032-median14y")
                    self.add(m, CLEETS.thresholdShare, thr, XSD.decimal)
                    self.add(m, CLEETS.forTime, ensure_period(self.g, r[col]))
                    self._cite(m, act)
            # 2045 Q4 share as an EVAdoptionPrediction so the generic prediction tools see it
            p = DATA[f"turnover/{code}/2045Q4"]
            self.add(p, RDF.type, CLEETS.EVAdoptionPrediction)
            self.add(p, CLEETS.forLAD, lad)
            self.add(p, CLEETS.forTime, ensure_period(self.g, "2045Q4"))
            self.add(p, CLEETS.scenario, "ban2032-median14y")
            self.add(p, CLEETS.predictedAdoptionShare, float(r["bev_share_2045_pct"]) / 100.0, XSD.decimal)
            self._cite(p, act)
            n += 1
        if table10 is not None:
            for _, r in table10.iterrows():
                s = DATA[f"turnover/wales/ceiling/{int(round(float(r['median_scrappage_years'])))}y"]
                self.add(s, RDF.type, CLEETS.TurnoverCeiling)
                self._cite(s, act)
                self.add(s, CLEETS.medianScrappageYears, float(r["median_scrappage_years"]), XSD.decimal)
                self.add(s, CLEETS.impliedAnnualReplacementPct, float(r["implied_annual_replacement_pct"]), XSD.decimal)
                self.add(s, CLEETS.bevShare2045, float(r["wales_bev_share_2045_pct"]) / 100.0, XSD.decimal)
                self.add(s, CLEETS.shortfallFrom100pp, float(r["shortfall_from_100_pp"]), XSD.decimal)
                self.add(s, CLEETS.residualNonBEV, float(r["residual_non_bev_cars"]), XSD.decimal)
        if trajectories is not None:  # welsh_lad_electrification_to_2053.csv (quarterly)
            share_col = next((c for c in trajectories.columns if "share" in c.lower()), None)
            name_col = next((c for c in trajectories.columns if c.lower() in ("name", "lad", "lad_name")), None)
            if share_col and name_col:
                for _, r in trajectories.iterrows():
                    lad = self.lad(r[name_col])
                    if lad is None or not re.match(r"\d{4}-?Q[1-4]", str(r["period"])):
                        continue
                    per = re.sub("-", "", str(r["period"]))
                    p = DATA[f"turnover/{lad.split('#')[-1]}/{per}"]
                    val = float(r[share_col]); val = val / 100.0 if val > 1.0 else val
                    self.add(p, RDF.type, CLEETS.EVAdoptionPrediction)
                    self.add(p, CLEETS.forLAD, lad); self.add(p, CLEETS.forTime, ensure_period(self.g, per))
                    self.add(p, CLEETS.scenario, "ban2032-median14y")
                    self.add(p, CLEETS.predictedAdoptionShare, val, XSD.decimal)
                    self._cite(p, act)
        self.counts["turnover"] = n

    # -- charging constraint (Stage 8) ---------------------------------------------------
    def charging(self, df: pd.DataFrame, source: str, flagged: pd.DataFrame | None = None):
        act = self.activity("charging", source)
        shortfall = {}
        if flagged is not None and "charger_shortfall_2045" in flagged.columns:
            shortfall = {str(r["name"]).strip(): float(r["charger_shortfall_2045"]) for _, r in flagged.iterrows()}
        n = 0
        for _, r in df.iterrows():
            lad = self.lad(r["name"])
            if lad is None:
                continue
            s = DATA[f"charging/{lad.split('#')[-1]}"]
            self.add(s, RDF.type, CLEETS.ChargingConstraintAssessment)
            self.add(s, CLEETS.forLAD, lad)
            self._cite(s, act)
            self.add(s, RDFS.label, Literal(f"{r['name']} charging-provision constraint assessment for 2045"))
            self.add(s, CLEETS.forTime, ensure_period(self.g, "2045Q4"))
            self.add(s, CLEETS.bevShare2045, float(r["share_2045_pct"]) / 100.0, XSD.decimal)
            self.add(s, CLEETS.lagYearsAt80pc, float(r["lag_years_at_80pc"]), XSD.decimal)
            self.add(s, CLEETS.evsPerChargePoint2045, float(r["evs_per_charge_point_2045"]), XSD.decimal)
            self.add(s, CLEETS.provisionAdequacy, float(r["provision_adequacy"]), XSD.decimal)
            self.add(s, CLEETS.constraintClass, str(r["constraint_class"]).strip())
            if str(r["name"]).strip() in shortfall:
                self.add(s, CLEETS.chargerShortfall2045, shortfall[str(r["name"]).strip()], XSD.decimal)
            n += 1
        self.counts["charging"] = n

    # -- neural (Stages 6e, 13, 14) ------------------------------------------------------
    def neural(self, source: str, table7: pd.DataFrame | None = None, metrics6e: pd.DataFrame | None = None,
               forecast: pd.DataFrame | None = None):
        quarterly = table7 is not None and "pooled_R2" in table7.columns
        act = self.activity("neural", source, comment=None if quarterly else FAMILIES["neural"]["comment_annual"])
        n = 0
        if table7 is not None:
            note = ("Table 7: best configuration per approach, rolling-origin one-step-ahead quarterly backtest 2022 Q1-2025 Q4 "
                    "(352 held-out LAD-quarters per configuration), K = alpha x last training observation"
                    if quarterly else "Table 7: best configuration per approach, walk-forward 2023-2025, annual LAD panel")
            for i, r in table7.iterrows():
                s = DATA[f"neural/metric/table7/{i}"]
                self.add(s, RDF.type, CLEETS.ModelMetric); self._cite(s, act)
                self.add(s, CLEETS.metricTarget, str(r["Target"])); self.add(s, CLEETS.modelName, str(r["Model"]))
                self.add(s, CLEETS.scenario, str(r["Scenario"]))
                self.add(s, CLEETS.mae, float(r["MAE"]), XSD.decimal); self.add(s, CLEETS.rmse, float(r["RMSE"]), XSD.decimal)
                self.add(s, CLEETS.r2, float(r["R2"]), XSD.decimal)
                if quarterly:
                    self.add(s, CLEETS.pooledR2, float(r["pooled_R2"]), XSD.decimal)
                    self.add(s, CLEETS.nPredictions, 352, XSD.integer)
                self.add(s, CLEETS.metricNote, note)
        if metrics6e is not None:
            for i, r in metrics6e.iterrows():
                s = DATA[f"neural/metric/stage6e/{i}"]
                self.add(s, RDF.type, CLEETS.ModelMetric); self._cite(s, act)
                self.add(s, CLEETS.metricTarget, "adoption ratio, first differences (pp)")
                self.add(s, CLEETS.modelName, str(r["model"]))
                self.add(s, CLEETS.mae, float(r["MAE(pp)"]), XSD.decimal); self.add(s, CLEETS.rmse, float(r["RMSE(pp)"]), XSD.decimal)
                self.add(s, CLEETS.r2, float(r["R2 diff"]), XSD.decimal)
                self.add(s, CLEETS.metricNote, "Stage 6e: walk-forward over the last eight quarters, 176 LAD-quarter predictions")
        if forecast is not None:  # nn_adoption_ratio_forecast_2030.csv: lad, period, adoption_ratio
            for _, r in forecast.iterrows():
                code = re.search(r"(W\d{8})", str(r["lad"]))
                lad = self.lads.get(code.group(1).casefold()) if code else self.lad(r["lad"])
                if lad is None:
                    continue
                per = re.sub("-", "", str(r["period"]))
                p = DATA[f"nn6e/{lad.split('#')[-1]}/{per}"]
                self.add(p, RDF.type, CLEETS.EVAdoptionPrediction)
                self.add(p, CLEETS.forLAD, lad); self.add(p, CLEETS.forTime, ensure_period(self.g, per))
                self.add(p, CLEETS.scenario, "nn-stage6e")
                self.add(p, CLEETS.predictedAdoptionShare, float(r["adoption_ratio"]), XSD.decimal)
                self._cite(p, act)
                n += 1
        self.counts["neural"] = n

    # -- diffusion backtest (Stage 13, quarterly revision) ---------------------------------
    def diffusion_backtest(self, text: str, source: str):
        """Parse the Stage 13 rolling-origin backtest of the bounded logistic run off the released KG
        and attach the metrics to the diffusion activity already present in the prediction KG."""
        act = next((a for a in self.base.subjects(RDF.type, PROV.Activity) if _local_name(a).startswith("diffusion")), None)
        if act is None:
            return
        n = 0
        target = None
        for line in text.splitlines():
            m = re.match(r"=== (EV keepership|EV chargers): rolling-origin (\S+)\.\.(\S+)", line)
            if m:
                target, span = m.group(1), f"{m.group(2)}-{m.group(3)}"
                continue
            m = re.match(r"\s*(Low|Central|High)\s+n=\s*(\d+)\s+MAE=\s*([\d.]+)\s+RMSE=\s*([\d.]+)\s+mean per-LAD R2=\s*([-\d.]+)\s+pooled R2=\s*([-\d.]+)", line)
            if m and target:
                scen = m.group(1)
                s = DATA[f"diffusion/metric/stage13/{target.split()[-1]}/{scen.lower()}"]
                self.add(s, RDF.type, CLEETS.ModelMetric); self._cite(s, act)
                self.add(s, CLEETS.metricTarget, target); self.add(s, CLEETS.modelName, "Bounded logistic (released KG)")
                self.add(s, CLEETS.scenario, scen)
                self.add(s, CLEETS.nPredictions, int(m.group(2)), XSD.integer)
                self.add(s, CLEETS.mae, float(m.group(3)), XSD.decimal); self.add(s, CLEETS.rmse, float(m.group(4)), XSD.decimal)
                self.add(s, CLEETS.r2, float(m.group(5)), XSD.decimal); self.add(s, CLEETS.pooledR2, float(m.group(6)), XSD.decimal)
                self.add(s, CLEETS.metricNote, f"Stage 13: rolling-origin one-step-ahead quarterly backtest {span} off the released KG; scenario capacity anchored on the last training observation")
                n += 1
        self.counts["diffusion backtest metrics"] = n

    # -- covariates (Stages 4a-bis, 5) ---------------------------------------------------
    def covariates(self, source: str, table8: pd.DataFrame | None = None, residuals: pd.DataFrame | None = None):
        act = self.activity("covariates", source)
        n = 0
        if table8 is not None:
            for i, r in table8.iterrows():
                s = DATA[f"covariates/metric/{i}"]
                self.add(s, RDF.type, CLEETS.ModelMetric); self._cite(s, act)
                self.add(s, CLEETS.metricTarget, "EVs per 1,000 residents (leave-one-out, 22 LADs)")
                self.add(s, CLEETS.modelName, str(r["model"]))
                self.add(s, CLEETS.mae, float(r["MAE"]), XSD.decimal); self.add(s, CLEETS.rmse, float(r["RMSE"]), XSD.decimal)
                self.add(s, CLEETS.r2, float(r["R2"]), XSD.decimal)
                self.add(s, CLEETS.metricNote, "Table 8: features population, density, area_km2; stochastic models averaged over five seeds")
        if residuals is not None:
            for _, r in residuals.iterrows():
                lad = self.lad(r["name"])
                if lad is None:
                    continue
                s = DATA[f"covariates/residual/{lad.split('#')[-1]}"]
                self.add(s, RDF.type, CLEETS.CovariateResidual); self._cite(s, act)
                self.add(s, CLEETS.forLAD, lad)
                self.add(s, RDFS.label, Literal(f"{r['name']} EVs per 1,000 residents against the Ridge covariate prediction"))
                self.add(s, CLEETS.observedValue, float(r["evs_per_1000"]), XSD.decimal)
                self.add(s, CLEETS.predictedValue, float(r["pred_ridge"]), XSD.decimal)
                self.add(s, CLEETS.residual, float(r["residual"]), XSD.decimal)
                n += 1
        self.counts["covariates"] = n

    def write(self, path: str):
        self.complete_base_citations()
        self.g.serialize(destination=path, format="turtle")
        return len(self.g)


# ----------------------------------------------------------------------------- notebook parsing
def from_notebook(b: FamilyBuilder, nb_path: str):
    nb = json.load(open(nb_path, encoding="utf-8"))
    texts = cell_outputs(nb)
    src = f"companion notebook cell outputs: {Path(nb_path).name}"

    t = find_output(texts, "WHICH LADs DIFFUSE MOST SLOWLY")
    if t:
        df = read_printed_table(t, "slowest_rank")
        eff = read_printed_table(t.split("Covariate effect on the midpoint")[-1], "term") if "Covariate effect" in t else None
        if df is not None:
            b.hierarchical(df, src, eff)

    t = find_output(texts, "ELECTRIFICATION ARRIVAL BY LAD")
    t10 = find_output(texts, "TABLE 10")
    if t:
        arrival = read_printed_table(t, "arrival_rank")
        table10 = read_printed_table(t10.split("TABLE 10")[-1], "median_scrappage_years") if t10 else None
        if arrival is not None:
            b.turnover(arrival, src, table10)

    t = find_output(texts, "Full classification:")
    if t:
        full = read_printed_table(t.split("Full classification:")[-1], "name")
        flagged = read_printed_table(t.split("LADs where charging is plausibly the binding constraint")[-1], "name") \
            if "LADs where charging is plausibly" in t else None
        if full is not None:
            b.charging(full, src, flagged)

    t7 = find_output(texts, "TABLE 7")
    t6e = find_output(texts, "Walk-forward on FIRST DIFFERENCES of the adoption ratio")
    table7 = read_printed_table(t7.split("TABLE 7")[-1], "Target") if t7 else None
    m6e = None
    if t6e:
        block = t6e.split("errors in percentage points:")[-1]
        m6e = read_printed_table(block, "model")
        if m6e is not None:
            m6e = m6e[m6e["model"].isin(["nn", "persist", "drift"])]
    if table7 is not None or m6e is not None:
        b.neural(src, table7, m6e)

    t13 = find_output(texts, "=== EV chargers: rolling-origin")
    if t13:
        b.diffusion_backtest(t13, src)

    t8 = find_output(texts, "leave-one-out: n=22 LADs")
    tres = find_output(texts, "Selected Ridge alpha")
    table8 = None
    if t8:
        block = t8.split("graph=")[-1].split("\n", 1)[-1]
        table8 = read_printed_table(block, "MAE_sd")  # header row; the index name 'model' sits on the next line
        if table8 is not None and "model" not in table8.columns:
            table8 = table8.rename(columns={table8.columns[0]: "model"})
    residuals = read_printed_table(tres.split("Selected Ridge alpha")[-1], "code") if tres else None
    if table8 is not None or residuals is not None:
        b.covariates(src, table8, residuals)


def from_csv_dir(b: FamilyBuilder, csv_dir: str):
    d = Path(csv_dir)
    src = f"notebook exports in {d}"

    def rd(name):
        p = d / name
        return pd.read_csv(p) if p.exists() else None

    hier = rd("hierarchical_diffusion_parameters.csv")
    if hier is not None and {"name", "midpoint_period"} <= set(hier.columns):
        b.hierarchical(hier, src)
    arrival = rd("welsh_lad_electrification_arrival.csv")
    if arrival is not None:
        b.turnover(arrival, src, rd("table10_turnover_ceiling.csv"), rd("welsh_lad_electrification_to_2053.csv"))
    nn = rd("nn_adoption_ratio_forecast_2030.csv")
    t7 = rd("table7_best_configuration.csv")
    if nn is not None or t7 is not None:
        b.neural(src, t7, None, nn)


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--prediction-kg", default="cleets_prediction_kg.ttl", help="existing diffusion prediction KG (for LAD URIs)")
    ap.add_argument("--observed-kg", default="cleets_cskg_enriched.ttl", help="observed KG (dataset records are copied from it so every family cites its datasets)")
    ap.add_argument("--notebook", help="executed companion notebook (.ipynb)")
    ap.add_argument("--csv-dir", help="directory with the notebook's CSV exports (cleets_out)")
    ap.add_argument("--output", default="cleets_prediction_families.ttl")
    a = ap.parse_args()
    if not a.notebook and not a.csv_dir:
        ap.error("give --notebook and/or --csv-dir")
    from kg_service import find_data_file
    b = FamilyBuilder(find_data_file(a.prediction_kg), find_data_file(a.observed_kg))
    if a.csv_dir:
        from_csv_dir(b, a.csv_dir)
    if a.notebook:
        from_notebook(b, a.notebook)
    n = b.write(a.output)
    print(f"Wrote {n:,} triples to {a.output}")
    for k, v in b.counts.items():
        print(f"  {k:<14} {v} per-LAD resources")


if __name__ == "__main__":
    main()
