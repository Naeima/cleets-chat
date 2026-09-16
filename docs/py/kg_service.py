#!/usr/bin/env python3
"""
kg_service.py: RDF interface to the CLEETS knowledge graphs.

Loads the observed graph (cleets_cskg_enriched.ttl) and the prediction graph
(cleets_prediction_kg.ttl) with rdflib, builds small in-memory indexes once,
and exposes the query methods used by qa.py / qa_with_humanization.py and the
dashboards:

    kg = CLEETSKG("cleets_cskg_enriched.ttl", "cleets_prediction_kg.ttl")
    kg.lad_map()                                  # {slug: (display name, uri)}
    kg.find_lads_in_text("Compare Cardiff and Swansea")
    kg.prediction_rows(2045, "central", "Cardiff")
    kg.prediction_year_summary(2045, "central")
    kg.prediction_inventory() / kg.actual_inventory()
    kg.actual_search("Show Cardiff EV keepership data")
    kg.source_links_for_subject(subject_uri, prediction=False)

Every value returned is read from the graphs; nothing is estimated here.
"""

from __future__ import annotations

import logging
import re
from collections import defaultdict
from typing import Dict, Iterable, List, Optional, Tuple

try:
    from rdflib import Graph, Literal, Namespace, URIRef
    from rdflib.namespace import DCAT, DCTERMS, OWL, PROV, RDF, RDFS, SKOS
    HAVE_RDFLIB = True
except ImportError:  # snapshot mode (e.g. Pyodide in the browser): no graph parsing, JSON indexes only
    HAVE_RDFLIB = False

    class Namespace(str):  # minimal stand-in: CLEETS.year -> "https://...#year"
        def __getattr__(self, item):
            if item.startswith("__"):
                raise AttributeError(item)
            return str(self) + item

        def __getitem__(self, item):
            return str(self) + item

    URIRef = str
    Literal = str
    Graph = None
    DCAT = Namespace("http://www.w3.org/ns/dcat#"); DCTERMS = Namespace("http://purl.org/dc/terms/")
    OWL = Namespace("http://www.w3.org/2002/07/owl#"); PROV = Namespace("http://www.w3.org/ns/prov#")
    RDF = Namespace("http://www.w3.org/1999/02/22-rdf-syntax-ns#"); RDFS = Namespace("http://www.w3.org/2000/01/rdf-schema#")
    SKOS = Namespace("http://www.w3.org/2004/02/skos/core#")

logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
logger = logging.getLogger("kg_service")

CLEETS = Namespace("https://w3id.org/def/cleets#")
DATA = Namespace("https://w3id.org/def/cleets/data#")
ONTOLOGY_URL = "https://w3id.org/def/cleets"

# Observation classes in the observed graph and the predicate holding their value.
VALUE_PREDICATES = {
    CLEETS.EVKeepership: (CLEETS.keepershipValue, "private BEV keepership"),
    CLEETS.EVChargerCount: (CLEETS.chargerCountValue, "public charging devices"),
    CLEETS.AdoptionRatioObservation: (CLEETS.keeperChargerRatio, "keepers per charger"),
    CLEETS.IncomeDeprivation: (CLEETS.incomeDeprivationValue, "income deprivation (mean WIMD decile)"),
    CLEETS.Population: (CLEETS.populationValue, "resident population"),
    CLEETS.PopulationDensity: (CLEETS.densityValue, "population density (persons per sq km)"),
    # Generic cleets:Observation resources carry cleets:hasSimpleResult and are
    # distinguished by observesProperty; labelled in _measure_key().
    CLEETS.Observation: (CLEETS.hasSimpleResult, "observation"),
}

# Keyword -> measure key used by actual_search().
MEASURE_KEYWORDS = [
    ("keepership", ("keepership", "keeper", "bev", "battery electric", "electric vehicle", "ev uptake",
                    "ev adoption", "adoption", "uptake", "ulev")),
    ("chargers", ("charger", "charging", "chargepoint", "charge point", "charging device")),
    ("ratio", ("ratio", "per charger", "keepers per")),
    ("chargers_per_100k", ("per 100k", "per 100,000", "per 100 000", "per capita", "per resident")),
    ("evs_per_1000", ("per thousand", "per 1000", "per 1,000")),
    ("vehicle_stock", ("vehicle stock", "all vehicles", "total vehicles", "licensed vehicles")),
    ("population", ("population",)),
    ("density", ("density",)),
    ("deprivation", ("deprivation", "wimd", "income", "deprived")),
]

MEASURE_LABELS = {
    "keepership": "private BEV keepership",
    "chargers": "public charging devices",
    "ratio": "keepers per charger",
    "chargers_per_100k": "chargers per 100k residents",
    "evs_per_1000": "EVs per 1,000 residents",
    "vehicle_stock": "private vehicle stock",
    "population": "resident population",
    "density": "population density (persons per sq km)",
    "deprivation": "income deprivation (mean WIMD decile)",
}

# Extra spellings stakeholders use for LADs (display name -> aliases).
LAD_ALIASES = {
    "Isle of Anglesey": ("Anglesey", "Ynys Mon", "Ynys Môn"),
    "Rhondda Cynon Taf": ("RCT", "Rhondda"),
    "Neath Port Talbot": ("Neath", "Port Talbot"),
    "Merthyr Tydfil": ("Merthyr",),
    "Blaenau Gwent": ("Blaenau",),
    "Vale of Glamorgan": ("The Vale", "Glamorgan"),
    "Carmarthenshire": ("Carmarthen",),
    "Pembrokeshire": ("Pembroke",),
    "Monmouthshire": ("Monmouth",),
    "Denbighshire": ("Denbigh",),
    "Flintshire": ("Flint",),
    "Cardiff": ("Caerdydd",),
    "Swansea": ("Abertawe",),
    "Newport": ("Casnewydd",),
}


def find_data_file(name: str) -> str:
    """Resolve a knowledge-graph file name against the working directory, ./data,
    the package directory and its data/ folder (so `python app.py` works from a
    clone of the repository as well as from a flat extracted folder)."""
    from pathlib import Path
    p = Path(name)
    if p.exists():
        return str(p)
    here = Path(__file__).resolve().parent
    for base in (Path.cwd() / "data", here, here / "data"):
        cand = base / p.name
        if cand.exists():
            return str(cand)
    return name


def _local(uri) -> str:
    s = str(uri)
    for sep in ("#", "/"):
        if sep in s:
            s = s.rsplit(sep, 1)[-1]
    return s


def _num(lit) -> Optional[float]:
    if lit is None:
        return None
    try:
        return float(lit.toPython()) if isinstance(lit, Literal) else float(lit)
    except (TypeError, ValueError):
        try:
            return float(str(lit))
        except ValueError:
            return None


def _fmt(v: Optional[float]) -> str:
    if v is None:
        return "n/a"
    if float(v).is_integer():
        return f"{int(v):,}"
    return f"{v:,.4g}" if abs(v) < 1 else f"{v:,.2f}"


class CLEETSKG:
    """CLEETS knowledge-graph service (observed + prediction graphs)."""

    def __init__(self, observed_path: str = "cleets_cskg_enriched.ttl",
                 prediction_path="cleets_prediction_kg.ttl"):
        """
        prediction_path may be one file, a comma-separated list, or a list of
        files. All prediction files are merged into one graph; each prediction
        family is recognised by the prov:Activity that generated it.
        """
        self.observed_path = observed_path
        self.prediction_paths = self._as_paths(prediction_path)
        self.prediction_path = self.prediction_paths[0] if self.prediction_paths else ""
        self.observed_kg = self._load(observed_path, "observed")
        self.prediction_kg = Graph()
        for p in self.prediction_paths:
            self._load(p, "prediction", into=self.prediction_kg)

        # Backwards-compatible namespace attributes.
        self.CLEETS, self.DATA = CLEETS, DATA
        self.DCAT, self.DCTERMS, self.RDFS, self.PROV, self.SKOS = DCAT, DCTERMS, RDFS, PROV, SKOS

        self._snapshot = False
        self._build_lad_index()
        self._build_period_index()
        self._build_family_index()
        self._build_prediction_index()
        self._build_family_resources()
        self._build_observation_index()
        self._build_dataset_index()
        self._counts = {"observed_triples": len(self.observed_kg), "prediction_triples": len(self.prediction_kg),
                        "subjects": len(set(self.observed_kg.subjects())), "predicates": len(set(self.observed_kg.predicates()))}
        logger.info("CLEETSKG ready: %d LADs, %d predictions in %d families, %d observations",
                    len(self._lads), self._prediction_count, len(self._families),
                    sum(len(v) for v in self._obs_by_lad.values()))

    # ------------------------------------------------------------------ loading
    @staticmethod
    def _as_paths(spec) -> List[str]:
        if not spec:
            return []
        if isinstance(spec, (list, tuple)):
            return [str(p).strip() for p in spec if str(p).strip()]
        return [p.strip() for p in str(spec).split(",") if p.strip()]

    @staticmethod
    def _load(path: str, kind: str, into: Graph = None) -> Graph:
        g = into if into is not None else Graph()
        try:
            path = find_data_file(path)
            logger.info("Loading %s graph: %s", kind, path)
            before = len(g)
            g.parse(path, format="turtle")
            logger.info("Loaded %s graph: %d triples", kind, len(g) - before)
        except Exception as exc:  # reported to the user, app keeps running
            logger.error("Could not load %s graph %s: %s", kind, path, exc)
        return g

    # ------------------------------------------------------------------ indexes
    def _build_lad_index(self):
        """Welsh LADs from both graphs: uri -> display name, plus alias lookup."""
        self._lads: Dict[URIRef, str] = {}
        self._lad_code: Dict[URIRef, str] = {}
        for g in (self.observed_kg, self.prediction_kg):
            for uri in g.subjects(RDF.type, CLEETS.WelshLAD):
                label = g.value(uri, RDFS.label) or g.value(uri, SKOS.prefLabel)
                if label and uri not in self._lads:
                    self._lads[uri] = str(label).strip()
                code = g.value(uri, CLEETS.ladCode)
                if code:
                    self._lad_code[uri] = str(code)
        # Alias table (lower-case text -> uri), longest alias first for matching.
        self._alias: Dict[str, URIRef] = {}
        for uri, name in self._lads.items():
            self._alias[name.casefold()] = uri
            if uri in self._lad_code:
                self._alias[self._lad_code[uri].casefold()] = uri
            for alias in LAD_ALIASES.get(name, ()):
                self._alias[alias.casefold()] = uri
        self._alias_patterns = [
            (re.compile(r"(?<![\w-])" + re.escape(a) + r"(?![\w-])", re.IGNORECASE), uri)
            for a, uri in sorted(self._alias.items(), key=lambda kv: -len(kv[0]))
        ]

    def _build_period_index(self):
        """Time nodes (both graphs): uri -> (year, quarter or None, label)."""
        self._periods: Dict[URIRef, Tuple[int, Optional[int], str]] = {}
        for g in (self.observed_kg, self.prediction_kg):
            for t in set(g.subjects(RDF.type, CLEETS.Time)) | set(g.subjects(RDF.type, CLEETS.Quarter)):
                y = _num(g.value(t, CLEETS.year))
                if y is None:
                    continue
                q = _num(g.value(t, CLEETS.quarter))
                label = g.value(t, CLEETS.yearQuarter) or g.value(t, RDFS.label) or (
                    f"{int(y)}-Q{int(q)}" if q else str(int(y)))
                self._periods[t] = (int(y), int(q) if q is not None else None, str(label))

    def _period(self, t) -> Tuple[Optional[int], Optional[int], str]:
        if t in self._periods:
            return self._periods[t]
        return (None, None, _local(t) if t is not None else "")

    # Family keys are the first token of the activity's local name
    # (activity/diffusion-q2026rev -> "diffusion", activity/turnover-2026-09-15 -> "turnover").
    FAMILY_LABELS = {
        "diffusion": "Bounded logistic diffusion scenarios",
        "hierarchical": "Hierarchical diffusion (two-stage empirical Bayes)",
        "turnover": "Age-structured fleet turnover, 2032 phase-out",
        "charging": "Charging-provision constraint (2045)",
        "neural": "Scenario-constrained neural and graph neural forecasts",
        "covariates": "Cross-sectional covariate comparison",
    }

    def _build_family_index(self):
        """prov:Activity nodes in the prediction graph -> family descriptors."""
        g = self.prediction_kg
        self._families: Dict[str, dict] = {}
        self._activity_family: Dict[URIRef, str] = {}
        for act in g.subjects(RDF.type, PROV.Activity):
            local = _local(act)
            key = re.split(r"[-_]", local, 1)[0].lower() or local
            self._activity_family[act] = key
            fam = self._families.setdefault(key, {
                "key": key, "activities": [], "label": self.FAMILY_LABELS.get(key, str(g.value(act, RDFS.label) or key)),
                "comment": "", "paper": "", "stage": "", "ended": "", "citation": "", "used": [], "scenarios": [],
                "predictions": 0, "milestones": 0, "resources": 0, "kinds": [],
            })
            fam["activities"].append(str(act))
            fam["comment"] = fam["comment"] or str(g.value(act, RDFS.comment) or "")
            fam["activity_label"] = str(g.value(act, RDFS.label) or "")
            fam["paper"] = fam["paper"] or str(g.value(act, CLEETS.paperSection) or "")
            fam["stage"] = fam["stage"] or str(g.value(act, CLEETS.notebookStage) or "")
            fam["ended"] = fam["ended"] or str(g.value(act, PROV.endedAtTime) or "")
            fam["citation"] = fam["citation"] or str(g.value(act, DCTERMS.bibliographicCitation) or "")
            for d in g.objects(act, PROV.used):
                fam["used"].append(str(d))
        if "diffusion" in self._families:
            f = self._families["diffusion"]
            f.setdefault("paper", ""); f["paper"] = f["paper"] or "S2.3.6, S3.4.3, S3.5"
            f["stage"] = f["stage"] or "Stage 6 (companion notebook)"

    def _family_of(self, s) -> str:
        act = self.prediction_kg.value(s, PROV.wasGeneratedBy)
        return self._activity_family.get(act, "diffusion" if act is None else _local(act))

    def _build_prediction_index(self):
        """(lad_uri, scenario) -> chronologically sorted prediction rows (all families)."""
        self._pred: Dict[Tuple[URIRef, str], List[dict]] = defaultdict(list)
        # Aggregate (non-LAD) areas such as Wales (W92000004) are kept apart so
        # that LAD rankings never mix a country total with district values.
        self._area_pred: Dict[Tuple[URIRef, str], List[dict]] = defaultdict(list)
        self._area_names: Dict[URIRef, str] = {}
        self._milestones: List[dict] = []
        g = self.prediction_kg
        for s in g.subjects(RDF.type, CLEETS.EVAdoptionPrediction):
            lad = g.value(s, CLEETS.forLAD)
            scen = g.value(s, CLEETS.scenario)
            y, q, label = self._period(g.value(s, CLEETS.forTime))
            if lad is None or scen is None or y is None:
                continue
            fam = self._family_of(s)
            row = {
                "subject": str(s),
                "family": fam,
                "lad_uri": str(lad),
                "lad_name": self._lads.get(lad) or str(g.value(lad, RDFS.label) or _local(lad)).strip(),
                "scenario": str(scen),
                "year": y,
                "quarter": q or 0,
                "period": label,
                "keepership": _num(g.value(s, CLEETS.predictedKeepership)),
                "adoption_share": _num(g.value(s, CLEETS.predictedAdoptionShare)),
            }
            if lad in self._lads:
                self._pred[(lad, str(scen))].append(row)
            else:
                self._area_pred[(lad, str(scen))].append(row)
                self._area_names[lad] = row["lad_name"]
            if fam in self._families and lad in self._lads:
                self._families[fam]["predictions"] += 1
                if str(scen) not in self._families[fam]["scenarios"]:
                    self._families[fam]["scenarios"].append(str(scen))
        for rows in list(self._pred.values()) + list(self._area_pred.values()):
            rows.sort(key=lambda r: (r["year"], r["quarter"]))
        self._prediction_count = sum(len(v) for v in self._pred.values())
        for s in g.subjects(RDF.type, CLEETS.AdoptionMilestonePrediction):
            lad = g.value(s, CLEETS.forLAD)
            y, q, label = self._period(g.value(s, CLEETS.forTime))
            fam = self._family_of(s)
            self._milestones.append({
                "subject": str(s),
                "family": fam,
                "lad_uri": str(lad),
                "lad_name": self._lads.get(lad, _local(lad)),
                "scenario": str(g.value(s, CLEETS.scenario) or ""),
                "threshold_share": _num(g.value(s, CLEETS.thresholdShare)),
                "year": y, "quarter": q or 0, "period": label,
            })
            if fam in self._families:
                self._families[fam]["milestones"] += 1
        self._milestones.sort(key=lambda r: (r["lad_name"], r["scenario"], r["threshold_share"] or 0))
        # Scenario list and period range of the diffusion family (the quarterly scenario forecasts).
        diff_rows = [r for rows in self._pred.values() for r in rows if r["family"] == "diffusion"]
        self._scenarios = sorted({r["scenario"] for r in diff_rows}) or sorted({k[1] for k in self._pred})
        self._pred_periods = sorted({(r["year"], r["quarter"], r["period"]) for r in (diff_rows or [r for rows in self._pred.values() for r in rows])})

    def _build_family_resources(self):
        """Per-LAD resources of the non-quarterly families (parameters, arrivals, assessments, residuals, metrics)."""
        g = self.prediction_kg
        self._hier: List[dict] = []
        self._effects: List[dict] = []
        self._turnover: List[dict] = []
        self._ceilings: List[dict] = []
        self._charging: List[dict] = []
        self._residuals: List[dict] = []
        self._metrics: List[dict] = []

        def lad_row(s):
            lad = g.value(s, CLEETS.forLAD)
            return lad, {"subject": str(s), "family": self._family_of(s), "lad_uri": str(lad or ""),
                         "lad_name": self._lads.get(lad, _local(lad) if lad else "")}

        for s in g.subjects(RDF.type, CLEETS.DiffusionParameterEstimate):
            lad, r = lad_row(s)
            r.update({"midpoint_period": str(g.value(s, CLEETS.midpointPeriod) or ""),
                      "slowest_rank": _num(g.value(s, CLEETS.slowestRank)),
                      "lag_vs_median_years": _num(g.value(s, CLEETS.lagVsMedianYears)),
                      "ci_width_years": _num(g.value(s, CLEETS.ciWidthYears)),
                      "shrinkage_weight": _num(g.value(s, CLEETS.shrinkageWeight)),
                      "rate_per_quarter": _num(g.value(s, CLEETS.ratePerQuarter))})
            self._hier.append(r)
        self._hier.sort(key=lambda r: r["slowest_rank"] or 0)
        for s in g.subjects(RDF.type, CLEETS.CovariateEffect):
            self._effects.append({"subject": str(s), "family": self._family_of(s),
                                  "term": str(g.value(s, CLEETS.covariateTerm) or ""),
                                  "beta_midpoint_q": _num(g.value(s, CLEETS.betaMidpointQuarters)),
                                  "lo": _num(g.value(s, CLEETS.betaLo)), "hi": _num(g.value(s, CLEETS.betaHi)),
                                  "beta_lograte": _num(g.value(s, CLEETS.betaLogRate)),
                                  "crosses_zero": str(g.value(s, CLEETS.crossesZero) or "").lower() == "true"})
        for s in g.subjects(RDF.type, CLEETS.ElectrificationArrival):
            lad, r = lad_row(s)
            r.update({"scenario": str(g.value(s, CLEETS.scenario) or ""),
                      "arrival_rank": _num(g.value(s, CLEETS.arrivalRank)),
                      "bev_share_2045": _num(g.value(s, CLEETS.bevShare2045)),
                      "bev_share_end": _num(g.value(s, CLEETS.bevShareEnd)),
                      "residual_non_bev": _num(g.value(s, CLEETS.residualNonBEV))})
            for m in self._milestones:
                if m["lad_uri"] == r["lad_uri"] and m["family"] == r["family"]:
                    r[f"reaches_{m['threshold_share']:g}"] = m["period"]
            self._turnover.append(r)
        self._turnover.sort(key=lambda r: r["arrival_rank"] or 0)
        for s in g.subjects(RDF.type, CLEETS.TurnoverCeiling):
            self._ceilings.append({"subject": str(s), "family": self._family_of(s),
                                   "median_scrappage_years": _num(g.value(s, CLEETS.medianScrappageYears)),
                                   "implied_annual_replacement_pct": _num(g.value(s, CLEETS.impliedAnnualReplacementPct)),
                                   "bev_share_2045": _num(g.value(s, CLEETS.bevShare2045)),
                                   "shortfall_pp": _num(g.value(s, CLEETS.shortfallFrom100pp)),
                                   "residual_non_bev": _num(g.value(s, CLEETS.residualNonBEV))})
        self._ceilings.sort(key=lambda r: r["median_scrappage_years"] or 0)
        for s in g.subjects(RDF.type, CLEETS.ChargingConstraintAssessment):
            lad, r = lad_row(s)
            r.update({"bev_share_2045": _num(g.value(s, CLEETS.bevShare2045)),
                      "lag_years_at_80pc": _num(g.value(s, CLEETS.lagYearsAt80pc)),
                      "evs_per_charge_point_2045": _num(g.value(s, CLEETS.evsPerChargePoint2045)),
                      "provision_adequacy": _num(g.value(s, CLEETS.provisionAdequacy)),
                      "constraint_class": str(g.value(s, CLEETS.constraintClass) or ""),
                      "charger_shortfall_2045": _num(g.value(s, CLEETS.chargerShortfall2045))})
            self._charging.append(r)
        self._charging.sort(key=lambda r: -(r["evs_per_charge_point_2045"] or 0))
        for s in g.subjects(RDF.type, CLEETS.CovariateResidual):
            lad, r = lad_row(s)
            r.update({"observed": _num(g.value(s, CLEETS.observedValue)),
                      "predicted": _num(g.value(s, CLEETS.predictedValue)),
                      "residual": _num(g.value(s, CLEETS.residual))})
            self._residuals.append(r)
        self._residuals.sort(key=lambda r: r["residual"] or 0)
        for s in g.subjects(RDF.type, CLEETS.ModelMetric):
            self._metrics.append({"subject": str(s), "family": self._family_of(s),
                                  "target": str(g.value(s, CLEETS.metricTarget) or ""),
                                  "model": str(g.value(s, CLEETS.modelName) or ""),
                                  "scenario": str(g.value(s, CLEETS.scenario) or ""),
                                  "mae": _num(g.value(s, CLEETS.mae)), "rmse": _num(g.value(s, CLEETS.rmse)),
                                  "r2": _num(g.value(s, CLEETS.r2)), "pooled_r2": _num(g.value(s, CLEETS.pooledR2)),
                                  "n": _num(g.value(s, CLEETS.nPredictions)),
                                  "note": str(g.value(s, CLEETS.metricNote) or "")})
        self._metrics.sort(key=lambda r: (r["family"], r["target"], r["mae"] or 0))
        for key, rows, kind in (("hierarchical", self._hier, "parameters"), ("turnover", self._turnover, "arrival"),
                                ("charging", self._charging, "assessment"), ("covariates", self._residuals, "residuals")):
            for r in rows:
                fam = self._families.get(r["family"])
                if fam is not None:
                    fam["resources"] += 1
                    if kind not in fam["kinds"]:
                        fam["kinds"].append(kind)
        for r in self._metrics:
            fam = self._families.get(r["family"])
            if fam is not None and "metrics" not in fam["kinds"]:
                fam["kinds"].append("metrics")
        for fam in self._families.values():
            if fam["predictions"] and "quarterly" not in fam["kinds"]:
                fam["kinds"].insert(0, "quarterly")

    def _measure_key(self, cls: URIRef, observes: Optional[URIRef]) -> str:
        if cls == CLEETS.EVKeepership:
            return "keepership"
        if cls == CLEETS.EVChargerCount:
            return "chargers"
        if cls == CLEETS.AdoptionRatioObservation:
            return "ratio"
        if cls == CLEETS.IncomeDeprivation:
            return "deprivation"
        if cls == CLEETS.Population:
            return "population"
        if cls == CLEETS.PopulationDensity:
            return "density"
        prop = _local(observes) if observes is not None else ""
        if prop.startswith("ChargersPer100k"):
            return "chargers_per_100k"
        if prop.startswith("EVsPerThousand"):
            return "evs_per_1000"
        if prop.startswith("PrivateVehicleStock"):
            return "vehicle_stock"
        return prop or "observation"

    def _build_observation_index(self):
        """lad_uri -> list of observation rows (Welsh LADs only)."""
        g = self.observed_kg
        self._obs_by_lad: Dict[URIRef, List[dict]] = defaultdict(list)
        seen = set()

        def add(s, lad, cls):
            if s in seen or lad not in self._lads:
                return
            seen.add(s)
            value_pred, _ = VALUE_PREDICATES.get(cls, (None, None))
            value = _num(g.value(s, value_pred)) if value_pred is not None else None
            t = g.value(s, CLEETS.forTime)
            if t is not None:
                y, q, label = self._period(t)
            else:  # annual resources (Population, PopulationDensity) carry dcterms:date
                d = g.value(s, DCTERMS.date)
                y = int(str(d)[:4]) if d and str(d)[:4].isdigit() else None
                q, label = None, str(int(y)) if y else ""
            measure = self._measure_key(cls, g.value(s, CLEETS.observesProperty))
            self._obs_by_lad[lad].append({
                "subject": str(s),
                "subject_label": str(g.value(s, RDFS.label) or _local(s)).strip(),
                "lad_uri": str(lad),
                "lad_name": self._lads[lad],
                "class": _local(cls),
                "measure": measure,
                "measure_label": MEASURE_LABELS.get(measure, measure),
                "value": value,
                "year": y, "quarter": q or 0, "period": label,
                "decile": _num(g.value(s, CLEETS.deprivationDecile)) if cls == CLEETS.IncomeDeprivation else None,
                "comment": str(g.value(s, RDFS.comment) or ""),
            })

        for cls in VALUE_PREDICATES:
            for s in g.subjects(RDF.type, cls):
                lad = g.value(s, CLEETS.forLAD)
                if lad is not None:
                    add(s, lad, cls)
        for lad in self._lads:
            for s in g.objects(lad, CLEETS.hasPopulation):
                add(s, lad, CLEETS.Population)
            for s in g.objects(lad, CLEETS.hasPopulationDensity):
                add(s, lad, CLEETS.PopulationDensity)
        for rows in self._obs_by_lad.values():
            rows.sort(key=lambda r: (r["measure"], r["year"] or 0, r["quarter"]))

    def _build_dataset_index(self):
        """dataset uri -> (label, identifier, landing page, title) from both graphs."""
        self._datasets: Dict[URIRef, Tuple[str, str, str, str]] = {}
        self._dataset_meta: Dict[str, dict] = {}
        self._observed_datasets = set(self.observed_kg.subjects(RDF.type, DCAT.Dataset))
        for g in (self.observed_kg, self.prediction_kg):
            for d in g.subjects(RDF.type, DCAT.Dataset):
                ident = str(g.value(d, DCTERMS.identifier) or g.value(d, RDFS.label) or _local(d))
                title = str(g.value(d, DCTERMS.title) or ident)
                url = str(g.value(d, DCAT.landingPage) or "")
                if d not in self._datasets or (url and not self._datasets[d][2]):
                    self._datasets[d] = (ident, ident, url, title)
                    self._dataset_meta[str(d)] = {"publisher": str(g.value(d, DCTERMS.publisher) or ""),
                                                  "license": str(g.value(d, DCTERMS.license) or ""),
                                                  "citation": str(g.value(d, DCTERMS.bibliographicCitation) or "")}

    # --------------------------------------------------------------------- LADs
    def lad_map(self) -> Dict[str, Tuple[str, str]]:
        """{slug: (display name, uri)} for the 22 Welsh LADs, sorted by name."""
        items = {name.lower().replace(" ", "_"): (name, str(uri)) for uri, name in self._lads.items()}
        return dict(sorted(items.items(), key=lambda kv: kv[1][0]))

    def lad_names(self) -> List[str]:
        return sorted(self._lads.values())

    def resolve_lad(self, name_or_uri) -> Optional[URIRef]:
        """Accept a display name, alias, LAD code (W06000015) or URI."""
        if name_or_uri is None:
            return None
        s = str(name_or_uri).strip()
        if s.startswith("http"):
            u = s if self._snapshot else URIRef(s)
            return u if u in self._lads else None
        return self._alias.get(s.casefold()) or self._alias.get(s.casefold().replace("_", " "))

    def get_lad_label(self, name) -> str:
        uri = self.resolve_lad(name)
        return self._lads[uri] if uri else str(name)

    def find_lads_in_text(self, text: str) -> List[Tuple[str, str]]:
        """LADs mentioned in free text, in order of appearance: [(name, uri), ...]."""
        found: List[Tuple[int, str, str]] = []
        taken: List[Tuple[int, int]] = []
        for pattern, uri in self._alias_patterns:
            for m in pattern.finditer(text or ""):
                span = (m.start(), m.end())
                if any(a <= span[0] < b or a < span[1] <= b for a, b in taken):
                    continue
                taken.append(span)
                found.append((m.start(), self._lads[uri], str(uri)))
        out, seen = [], set()
        for _, name, uri in sorted(found):
            if uri not in seen:
                seen.add(uri)
                out.append((name, uri))
        return out

    # -------------------------------------------------------------- predictions
    def prediction_rows(self, year: int, scenario: str, lad_name, family: str = None) -> List[dict]:
        """Quarterly prediction rows for one LAD/scenario in `year`, chronological.

        Each row: subject, family, lad_name, scenario, year, quarter, period,
        keepership, adoption_share. Empty list if the LAD/year is not covered.
        """
        uri = self.resolve_lad(lad_name)
        if uri is None:
            logger.warning("prediction_rows: unknown LAD %r", lad_name)
            return []
        rows = self._pred.get((uri, (scenario or "central").lower()), [])
        return [dict(r) for r in rows if r["year"] == int(year) and (family is None or r["family"] == family)]

    def prediction_series(self, scenario: str, lad_name, year_from: int = None, year_to: int = None) -> List[dict]:
        """All quarterly rows for one LAD/scenario (optionally bounded by year)."""
        uri = self.resolve_lad(lad_name)
        if uri is None:
            return []
        rows = self._pred.get((uri, (scenario or "central").lower()), [])
        return [dict(r) for r in rows
                if (year_from is None or r["year"] >= year_from) and (year_to is None or r["year"] <= year_to)]

    def area_prediction_rows(self, year: int, scenario: str, area: str = "Wales") -> List[dict]:
        """Quarterly rows for an aggregate area (e.g. Wales, W92000004) if the graph has one."""
        scenario = (scenario or "central").lower()
        for (uri, scen), rows in self._area_pred.items():
            if scen != scenario:
                continue
            name = self._area_names.get(uri, "")
            if area.casefold() in (name.casefold(), _local(uri).casefold()) or area.casefold() in name.casefold():
                return [dict(r) for r in rows if r["year"] == int(year)]
        return []

    def prediction_year_summary(self, year: int, scenario: str, family: str = None) -> List[dict]:
        """Year-end (last available quarter) row per LAD, sorted by keepership desc
        (adoption share desc when the family carries no counts)."""
        out = []
        scenario = (scenario or "central").lower()
        for (uri, scen), rows in self._pred.items():
            if scen != scenario:
                continue
            year_rows = [r for r in rows if r["year"] == int(year) and (family is None or r["family"] == family)]
            if year_rows:
                out.append(dict(year_rows[-1]))
        if out and all(r["keepership"] is None for r in out):
            out.sort(key=lambda r: (r["adoption_share"] is None, -(r["adoption_share"] or 0)))
        else:
            out.sort(key=lambda r: (r["keepership"] is None, -(r["keepership"] or 0)))
        return out

    def prediction_inventory(self) -> dict:
        lads = sorted({self._lads[k[0]] for k in self._pred})
        diffusion_count = sum(1 for rows in self._pred.values() for r in rows if r["family"] == "diffusion")
        return {
            "prediction_count": diffusion_count or self._prediction_count,
            "all_prediction_count": self._prediction_count,
            "families": [f["key"] for f in self.prediction_families()],
            "milestone_count": len(self._milestones),
            "lads": lads,
            "scenarios": self._scenarios,
            "periods": [p[2] for p in self._pred_periods],
            "years": (self._pred_periods[0][0], self._pred_periods[-1][0]) if self._pred_periods else (None, None),
            "measures": ["predictedKeepership (private BEV keepership)",
                         "predictedAdoptionShare (BEV share of private vehicle stock)",
                         "thresholdShare milestones"],
            "triples": self._counts["prediction_triples"],
        }

    def milestones(self, lad_name=None, scenario: str = None) -> List[dict]:
        """Quarter in which each LAD/scenario is predicted to cross an adoption-share threshold."""
        uri = self.resolve_lad(lad_name) if lad_name else None
        return [dict(m) for m in self._milestones
                if (uri is None or m["lad_uri"] == str(uri)) and (scenario is None or m["scenario"] == scenario.lower())]

    def prediction_activity(self) -> dict:
        """Provenance of the forecasts (prov:Activity that generated them)."""
        if self._snapshot:
            return dict(self._activity)
        g = self.prediction_kg
        acts = list(g.subjects(RDF.type, PROV.Activity))
        act = next((a for a in acts if self._activity_family.get(a) == "diffusion"), acts[0] if acts else None)
        if act is None:
            return {}
        return {
            "uri": str(act),
            "label": str(g.value(act, RDFS.label) or _local(act)),
            "comment": str(g.value(act, RDFS.comment) or ""),
            "ended": str(g.value(act, PROV.endedAtTime) or ""),
            "used": [self._dataset_link(d) for d in g.objects(act, PROV.used)],
            "scenarios": [{"scenario": _local(s), "terminal_target_share": _num(g.value(s, CLEETS.terminalTargetShare)),
                           "midpoint_shift_quarters": _num(g.value(s, CLEETS.midpointShiftQuarters))}
                          for s in g.subjects(RDF.type, CLEETS.Scenario)],
        }

    # ----------------------------------------------------------- prediction families
    def prediction_families(self) -> List[dict]:
        """One descriptor per prediction family (prov:Activity group), diffusion first."""
        order = ["diffusion", "hierarchical", "turnover", "charging", "neural", "covariates"]
        fams = sorted(self._families.values(), key=lambda f: (order.index(f["key"]) if f["key"] in order else 99, f["key"]))
        out = []
        for f in fams:
            d = dict(f)
            d["used_links"] = [self._dataset_link(URIRef(u)) for u in f["used"]]
            out.append(d)
        return out

    def family(self, key: str) -> Optional[dict]:
        return next((f for f in self.prediction_families() if f["key"] == key), None)

    def hierarchical_params(self, lad_name=None) -> List[dict]:
        uri = self.resolve_lad(lad_name) if lad_name else None
        return [dict(r) for r in self._hier if uri is None or r["lad_uri"] == str(uri)]

    def covariate_effects(self) -> List[dict]:
        return [dict(r) for r in self._effects]

    def turnover_rows(self, lad_name=None) -> List[dict]:
        uri = self.resolve_lad(lad_name) if lad_name else None
        return [dict(r) for r in self._turnover if uri is None or r["lad_uri"] == str(uri)]

    def turnover_ceilings(self) -> List[dict]:
        return [dict(r) for r in self._ceilings]

    def charging_assessments(self, lad_name=None) -> List[dict]:
        uri = self.resolve_lad(lad_name) if lad_name else None
        return [dict(r) for r in self._charging if uri is None or r["lad_uri"] == str(uri)]

    def covariate_residuals(self, lad_name=None) -> List[dict]:
        uri = self.resolve_lad(lad_name) if lad_name else None
        return [dict(r) for r in self._residuals if uri is None or r["lad_uri"] == str(uri)]

    def model_metrics(self, family: str = None) -> List[dict]:
        return [dict(r) for r in self._metrics if family is None or r["family"] == family]

    # Targets of the comparable backtests (Table 7 and the Stage 13 logistic run), by keyword.
    METRIC_TARGETS = {"chargers": "EV chargers", "keepership": "EV keepership"}

    def _metric_rows(self, marker: str, target: str = None) -> Dict[str, List[dict]]:
        wanted = self.METRIC_TARGETS.get((target or "").casefold(), target)
        out: Dict[str, List[dict]] = {}
        for m in self._metrics:
            if marker in m.get("note", "") and (not wanted or m["target"] == wanted):
                out.setdefault(m["target"], []).append(dict(m))
        for rows in out.values():
            rows.sort(key=lambda r: (r["mae"] if r["mae"] is not None else float("inf")))
        return dict(sorted(out.items()))

    def model_ranking(self, target: str = None) -> Dict[str, List[dict]]:
        """{target label: metric rows ranked by MAE} for the approaches compared under one protocol
        (Table 7: best configuration of each approach, identical rolling-origin folds). Falls back to
        the Stage 13 bounded-logistic run when Table 7 is not loaded. `target` may be 'chargers',
        'keepership' or a target label; None gives every target."""
        return self._metric_rows("Table 7", target) or self._metric_rows("Stage 13", target)

    def logistic_backtest(self, target: str = None) -> Dict[str, List[dict]]:
        """{target label: Stage 13 rows} — the bounded logistic re-run off the released KG under the
        low/central/high capacity multipliers (K = alpha x last training observation)."""
        return self._metric_rows("Stage 13", target)

    def best_models(self, target: str = None) -> Dict[str, dict]:
        """{target label: lowest-MAE metric row} of the comparable backtests."""
        return {t: rows[0] for t, rows in self.model_ranking(target).items() if rows}

    # ----------------------------------------------------------- dataset extraction
    # Column catalogue for dataset_table(): key -> (label, kind, argument)
    DATASET_COLUMNS = {
        "keepership": ("Private BEV keepership (latest)", "obs", "keepership"),
        "chargers": ("Public charging devices (latest)", "obs", "chargers"),
        "ratio": ("Keepers per charger (latest)", "obs", "ratio"),
        "chargers_per_100k": ("Chargers per 100k residents (latest)", "obs", "chargers_per_100k"),
        "evs_per_1000": ("EVs per 1,000 residents (latest)", "obs", "evs_per_1000"),
        "vehicle_stock": ("Private vehicle stock (latest)", "obs", "vehicle_stock"),
        "population": ("Resident population (latest)", "obs", "population"),
        "density": ("Population density, persons per sq km (latest)", "obs", "density"),
        "deprivation": ("Income deprivation, mean WIMD 2025 decile", "obs", "deprivation"),
        "pred_keepership_low": ("Predicted BEV keepership, low scenario", "pred", "low"),
        "pred_keepership_central": ("Predicted BEV keepership, central scenario", "pred", "central"),
        "pred_keepership_high": ("Predicted BEV keepership, high scenario", "pred", "high"),
        "pred_share_central": ("Predicted BEV share, central scenario", "share", "central"),
        "hier_midpoint": ("Hierarchical diffusion midpoint (quarter)", "hier", "midpoint_period"),
        "hier_rate": ("Hierarchical diffusion rate per quarter", "hier", "rate_per_quarter"),
        "hier_lag": ("Lag against Welsh median midpoint (years)", "hier", "lag_vs_median_years"),
        "turnover_share_2045": ("Turnover ceiling: BEV share at 2045 Q4", "turnover", "bev_share_2045"),
        "turnover_residual": ("Turnover: residual non-BEV vehicles at 2053 Q4", "turnover", "residual_non_bev"),
        "turnover_reaches_99": ("Turnover: first quarter at 99% BEV share", "turnover", "reaches_0.99"),
        "charging_class": ("Charging-constraint class (2045)", "charging", "constraint_class"),
        "charging_evs_per_device": ("BEVs per public charging device at 2045", "charging", "evs_per_charge_point_2045"),
        "covariate_residual": ("Ridge covariate residual, EVs per 1,000", "covariates", "residual"),
    }

    def dataset_columns(self) -> List[Tuple[str, str]]:
        """[(key, label)] of the columns available given the loaded graphs."""
        avail = []
        for key, (label, kind, arg) in self.DATASET_COLUMNS.items():
            if kind == "obs" and not any(r["measure"] == arg for rows in self._obs_by_lad.values() for r in rows):
                continue
            if kind in ("pred", "share") and "diffusion" not in self._families and not self._pred:
                continue
            if kind == "hier" and not self._hier:
                continue
            if kind == "turnover" and not self._turnover:
                continue
            if kind == "charging" and not self._charging:
                continue
            if kind == "covariates" and not self._residuals:
                continue
            avail.append((key, label))
        return avail

    def dataset_table(self, columns: List[str], lads=None, year: int = None, forecast_year: int = 2045) -> List[dict]:
        """One row per LAD with the requested columns, read from the graphs.

        columns: keys from DATASET_COLUMNS. Observed columns use the latest
        observation (or the latest in `year` when given) and add a
        '<column> period' column so the vintage of every value is visible.
        """
        lad_uris = [self.resolve_lad(l) for l in (lads or [])] if lads else list(self._lads)
        lad_uris = [u for u in lad_uris if u is not None]
        by_hier = {r["lad_uri"]: r for r in self._hier}
        by_turn = {r["lad_uri"]: r for r in self._turnover}
        by_chg = {r["lad_uri"]: r for r in self._charging}
        by_res = {r["lad_uri"]: r for r in self._residuals}
        rows = []
        for uri in sorted(lad_uris, key=lambda u: self._lads[u]):
            row = {"LAD": self._lads[uri], "LAD code": self._lad_code.get(uri, "")}
            for key in columns:
                if key not in self.DATASET_COLUMNS:
                    continue
                label, kind, arg = self.DATASET_COLUMNS[key]
                if kind == "obs":
                    obs = [r for r in self._obs_by_lad.get(uri, []) if r["measure"] == arg]
                    if year:
                        obs = [r for r in obs if r["year"] == year] or obs
                    row[label] = obs[-1]["value"] if obs else None
                    row[f"{label} period"] = obs[-1]["period"] if obs else ""
                elif kind in ("pred", "share"):
                    pr = self.prediction_rows(forecast_year, arg, uri)
                    pr = [r for r in pr if r["family"] == "diffusion"] or pr
                    if pr:
                        row[f"{label} ({pr[-1]['period']})"] = pr[-1]["keepership"] if kind == "pred" else pr[-1]["adoption_share"]
                    else:
                        row[f"{label} ({forecast_year})"] = None
                elif kind == "hier":
                    row[label] = by_hier.get(str(uri), {}).get(arg)
                elif kind == "turnover":
                    row[label] = by_turn.get(str(uri), {}).get(arg)
                elif kind == "charging":
                    row[label] = by_chg.get(str(uri), {}).get(arg)
                elif kind == "covariates":
                    row[label] = by_res.get(str(uri), {}).get(arg)
            rows.append(row)
        return rows

    def dataset_sources(self, columns: List[str]) -> List[dict]:
        """Dataset links behind the requested columns (for citation)."""
        links, seen = [], set()
        for key in columns:
            label, kind, arg = self.DATASET_COLUMNS.get(key, ("", "", ""))
            if kind == "obs":
                sample = next((r for rows in self._obs_by_lad.values() for r in rows if r["measure"] == arg), None)
                cand = self.source_links_for_subject(sample["subject"]) if sample else []
            else:
                fam = {"pred": "diffusion", "share": "diffusion", "hier": "hierarchical", "turnover": "turnover",
                       "charging": "charging", "covariates": "covariates"}.get(kind)
                f = self._families.get(fam, {})
                cand = [{"label": l["label"], "url": l["url"]} for l in (self._dataset_link(URIRef(u)) for u in f.get("used", []))]
            for l in cand:
                if l["url"] not in seen:
                    seen.add(l["url"]); links.append(l)
        return links

    # ----------------------------------------------------------------- observed
    def actual_inventory(self) -> dict:
        datasets = sorted({(ident, ident, url) for d, (ident, _, url, _t) in self._datasets.items()
                           if d in self._observed_datasets})
        return {
            "triples": self._counts["observed_triples"],
            "subjects": self._counts["subjects"],
            "predicates": self._counts["predicates"],
            "datasets": datasets,
            "lads": self.lad_names(),
            "measures": sorted({r["measure_label"] for rows in self._obs_by_lad.values() for r in rows}),
        }

    def dataset_catalogue(self) -> List[dict]:
        """One row per dcat:Dataset record in the loaded graphs, with the measures it supplies to the
        Welsh LAD observations (derived from the dcterms:source links, so a newly added dataset appears
        here automatically). Stored in the site snapshot for the browser build."""
        if getattr(self, "_dataset_catalogue", None) is not None:
            return [dict(r) for r in self._dataset_catalogue]
        if self._snapshot:
            return []
        g = self.observed_kg
        usage: Dict[str, dict] = {}
        for rows in self._obs_by_lad.values():
            for r in rows:
                for d in g.objects(URIRef(r["subject"]), DCTERMS.source):
                    if d not in self._datasets:
                        continue
                    u = usage.setdefault(str(d), {"measures": {}, "n": 0, "first": None, "last": None,
                                                  "first_key": None, "last_key": None})
                    u["measures"][r["measure_label"]] = u["measures"].get(r["measure_label"], 0) + 1
                    u["n"] += 1
                    if r["year"]:
                        key = (r["year"], r["quarter"])
                        if u["first_key"] is None or key < u["first_key"]:
                            u["first_key"], u["first"] = key, r["period"]
                        if u["last_key"] is None or key > u["last_key"]:
                            u["last_key"], u["last"] = key, r["period"]
        out = []
        for d, (ident, _, url, title) in self._datasets.items():
            meta = self._dataset_meta.get(str(d), {})
            u = usage.get(str(d))
            local = _local(d)
            if u:
                role = "source"
            elif str(d).rstrip("/") == str(DATA).rstrip("#"):
                role = "graph"
            elif local == "PredictionKG":
                role = "prediction"
            else:
                role = "reference"
            out.append({"uri": str(d), "identifier": ident, "title": title, "publisher": meta.get("publisher", ""),
                        "license": meta.get("license", ""), "citation": meta.get("citation", ""), "landing_page": url,
                        "role": role, "measures": sorted((u or {}).get("measures", {})),
                        "observations": (u or {}).get("n", 0), "first": (u or {}).get("first"), "last": (u or {}).get("last")})
        order = {"source": 0, "reference": 1, "graph": 2, "prediction": 3}
        out.sort(key=lambda r: (order[r["role"]], -r["observations"], r["identifier"]))
        self._dataset_catalogue = out
        return [dict(r) for r in out]

    def observation_years(self) -> Tuple[Optional[int], Optional[int]]:
        years = [r["year"] for rows in self._obs_by_lad.values() for r in rows if r["year"]]
        return (min(years), max(years)) if years else (None, None)

    def observations(self, lad_name, measure: str = None, year: int = None) -> List[dict]:
        """Observation rows for a LAD (optionally one measure / one year), chronological."""
        uri = self.resolve_lad(lad_name)
        if uri is None:
            return []
        rows = self._obs_by_lad.get(uri, [])
        rows = [r for r in rows if (measure is None or r["measure"] == measure) and (year is None or r["year"] == year)]
        return [dict(r) for r in sorted(rows, key=lambda r: (r["year"] or 0, r["quarter"]))]

    def latest_observation(self, lad_name, measure: str) -> Optional[dict]:
        rows = self.observations(lad_name, measure)
        return rows[-1] if rows else None

    def latest_by_lad(self, measure: str) -> List[dict]:
        """Latest observation of `measure` for every Welsh LAD, sorted by value desc."""
        out = []
        for uri in self._lads:
            rows = [r for r in self._obs_by_lad.get(uri, []) if r["measure"] == measure]
            if rows:
                out.append(dict(rows[-1]))
        out.sort(key=lambda r: (r["value"] is None, -(r["value"] or 0)))
        return out

    def ontology_terms(self) -> List[dict]:
        if self._snapshot:
            return [dict(t) for t in self._ontology_terms]
        g = self.observed_kg
        out = []
        for kind, cls in (("class", OWL.Class), ("object property", OWL.ObjectProperty),
                          ("datatype property", OWL.DatatypeProperty)):
            for s in g.subjects(RDF.type, cls):
                if not isinstance(s, URIRef) or not str(s).startswith(str(CLEETS)):
                    continue
                out.append({"subject": str(s), "kind": kind, "label": str(g.value(s, RDFS.label) or _local(s)),
                            "comment": str(g.value(s, RDFS.comment) or "")})
        return sorted(out, key=lambda r: (r["kind"], r["label"]))

    # ----------------------------------------------------------------- search
    @staticmethod
    def _measures_in_text(q: str) -> List[str]:
        q = " " + q.casefold() + " "
        found = []
        for key, words in MEASURE_KEYWORDS:
            if any(w in q for w in words) and key not in found:
                found.append(key)
        # "EV"/"EVs" alone means keepership unless chargers were named.
        if re.search(r"\bevs?\b", q) and "keepership" not in found and "chargers" not in found:
            found.insert(0, "keepership")
        return found

    def _obs_statements(self, r: dict, include_sources: bool = True) -> List[dict]:
        """Rows for actual_answer(): subject, subject_label, predicate_label, object."""
        base = {"subject": r["subject"], "subject_label": r["subject_label"], "lad_name": r["lad_name"]}
        stmts = [
            {**base, "predicate": "value", "predicate_label": r["measure_label"], "object": _fmt(r["value"])},
            {**base, "predicate": "period", "predicate_label": "period", "object": r["period"]},
        ]
        if r.get("decile") is not None:
            stmts.append({**base, "predicate": "decile", "predicate_label": "WIMD income decile (1 = most deprived)",
                          "object": _fmt(r["decile"])})
        if include_sources:
            for link in self.source_links_for_subject(r["subject"]):
                stmts.append({**base, "predicate": "source", "predicate_label": f"source: {link['label']}",
                              "object": link["url"]})
        return stmts

    def actual_search(self, question: str, limit: int = 30) -> Iterable[dict]:
        """Evidence retrieval over the observed graph for a free-text question.

        Returns statement rows {subject, subject_label, predicate_label, object}
        grouped by subject, most relevant subject first. The caller shows the
        first few subjects, so ordering encodes relevance:
          * LAD named, no measure  -> latest value of each measure for that LAD
          * measure named, no LAD  -> latest value per LAD, ranked (desc)
          * LAD + measure          -> that series (most recent first)
          * two or more LADs       -> side-by-side latest values
          * ontology / provenance  -> class definitions / dataset metadata
        """
        q = (question or "").strip()
        ql = q.casefold()
        lads = [self.resolve_lad(uri) for _, uri in self.find_lads_in_text(q)]
        measures = self._measures_in_text(ql)
        years = [int(y) for y in re.findall(r"\b(20[0-4]\d)\b", q)]
        wants_series = any(w in ql for w in ("over time", "changed", "change", "trend", "history", "since", "between"))
        stmts: List[dict] = []

        if any(w in ql for w in ("ontology", "class", "properties", "property", "vocabulary")) and not lads and not measures:
            for t in self.ontology_terms():
                stmts.append({"subject": t["subject"], "subject_label": f"{t['label']} ({t['kind']})",
                              "predicate_label": "definition", "object": t["comment"] or t["label"]})
            return stmts[:limit]

        if lads and not measures:
            order = ["keepership", "chargers", "ratio", "chargers_per_100k", "evs_per_1000",
                     "population", "density", "deprivation", "vehicle_stock"]
            for lad in lads:
                for m in order:
                    rows = [r for r in self._obs_by_lad.get(lad, []) if r["measure"] == m]
                    if years:
                        rows = [r for r in rows if r["year"] in years] or rows
                    if rows:
                        stmts.extend(self._obs_statements(rows[-1]))
        elif measures and not lads:
            # Ranking across Wales for the first measure (latest value per LAD); for
            # relationship questions add the second measure for the same LADs.
            primary = self.latest_by_lad(measures[0])
            if years:
                primary = [r for r in primary if r["year"] in years] or primary
            for r in primary:
                stmts.extend(self._obs_statements(r, include_sources=False))
                for m in measures[1:]:
                    other = self.latest_observation(r["lad_uri"], m)
                    if other:
                        stmts.extend(self._obs_statements(other, include_sources=False))
        elif lads and measures:
            for lad in lads:
                for m in measures:
                    rows = [r for r in self._obs_by_lad.get(lad, []) if r["measure"] == m]
                    if years:
                        rows = [r for r in rows if r["year"] in years] or rows
                    if not rows:
                        continue
                    chosen = rows if (wants_series or (len(lads) == 1 and len(measures) == 1)) else rows[-1:]
                    for r in reversed(chosen):  # most recent first
                        stmts.extend(self._obs_statements(r, include_sources=(r is chosen[-1])))
        else:
            # Provenance / dataset questions: dataset metadata is the evidence.
            for d, (ident, _, url, title) in sorted(self._datasets.items(), key=lambda kv: kv[1][0]):
                if d not in self._observed_datasets:
                    continue
                meta = self._dataset_meta.get(str(d), {})
                base = {"subject": str(d), "subject_label": f"Dataset {ident}"}
                stmts.append({**base, "predicate_label": "title", "object": title})
                if meta.get("publisher"):
                    stmts.append({**base, "predicate_label": "publisher", "object": meta["publisher"]})
                if url:
                    stmts.append({**base, "predicate_label": "landing page", "object": url})
                if meta.get("license"):
                    stmts.append({**base, "predicate_label": "licence", "object": meta["license"]})
        return stmts[:limit]

    # ------------------------------------------------------------------ sources
    def _dataset_link(self, d) -> dict:
        entry = self._datasets.get(d)
        if entry is None:  # snapshot mode keeps plain-string keys
            entry = self._datasets.get(str(d), (_local(d), _local(d), "", _local(d)))
        ident, _, url, title = entry
        return {"label": ident, "url": url or ONTOLOGY_URL, "title": title, "uri": str(d)}

    def source_links_for_subject(self, subject, prediction: bool = False) -> List[dict]:
        """[{label, url}] for the datasets a resource cites (dcterms:source / prov:wasDerivedFrom)."""
        s = URIRef(str(subject))
        if self._snapshot:
            links = [self._dataset_link(d) for d in self._subject_sources.get(str(subject), [])]
            if not links and prediction:
                fam = next((f for f in self._families.values() if any(str(subject).startswith(a.rsplit("/", 1)[0]) for a in f["activities"])), None)
                links = [self._dataset_link(u) for u in (fam or {}).get("used", [])]
            return [{"label": l["label"], "url": l["url"]} for l in links]
        g = self.prediction_kg if prediction else self.observed_kg
        links, seen = [], set()
        for pred in (DCTERMS.source, PROV.wasDerivedFrom, PROV.used):
            for d in g.objects(s, pred):
                if d in self._datasets and d not in seen:
                    seen.add(d)
                    links.append(self._dataset_link(d))
        if not links and prediction:
            act = g.value(s, PROV.wasGeneratedBy)
            if act is not None:
                for d in g.objects(act, PROV.used):
                    if d in self._datasets and d not in seen:
                        seen.add(d)
                        links.append(self._dataset_link(d))
        return [{"label": l["label"], "url": l["url"]} for l in links]

    def get_sources(self, lad_name=None, metric: str = "keepership") -> List[str]:
        """Compatibility helper: landing pages of datasets behind a measure."""
        rows = self.latest_by_lad(metric) if not lad_name else [self.latest_observation(lad_name, metric)]
        urls = []
        for r in rows:
            if r:
                urls.extend(l["url"] for l in self.source_links_for_subject(r["subject"]))
        return list(dict.fromkeys(urls)) or [ONTOLOGY_URL]

    # ------------------------------------------------------------ citation audit
    # Resource classes an answer can draw on, per graph.
    CITED_CLASSES = {
        "observed": ("EVKeepership", "EVChargerCount", "AdoptionRatioObservation", "Observation",
                     "Population", "PopulationDensity", "IncomeDeprivation"),
        "prediction": ("EVAdoptionPrediction", "AdoptionMilestonePrediction", "Scenario",
                       "DiffusionParameterEstimate", "CovariateEffect", "ElectrificationArrival", "TurnoverCeiling",
                       "ChargingConstraintAssessment", "CovariateResidual", "ModelMetric"),
    }
    DATASET_FIELDS = (("identifier", "dcterms:identifier"), ("title", "dcterms:title"), ("publisher", "dcterms:publisher"),
                      ("license", "dcterms:license"), ("citation", "dcterms:bibliographicCitation"),
                      ("landing_page", "dcat:landingPage"))

    def _reaches_dataset(self, g, s) -> bool:
        for p in (DCTERMS.source, PROV.wasDerivedFrom, PROV.used):
            if any(d in self._datasets for d in g.objects(s, p)):
                return True
        act = g.value(s, PROV.wasGeneratedBy)
        return act is not None and any(d in self._datasets for d in g.objects(act, PROV.used))

    def citation_audit(self) -> dict:
        """Check that everything an answer can draw on is citable.

        A resource counts as cited when it, or the prov:Activity that generated it, links to a
        dcat:Dataset record (dcterms:source, prov:wasDerivedFrom, prov:used). A dataset record counts
        as complete when it carries identifier, title, publisher, licence, bibliographic citation and
        landing page. Activities are checked for prov:used datasets and a bibliographic citation.
        The result is cached (and stored in the site snapshot, so the browser build can show it)."""
        if getattr(self, "_citation_audit", None):
            return dict(self._citation_audit)
        if self._snapshot:  # older snapshot without a stored audit
            return {"datasets": [], "datasets_total": 0, "datasets_complete": 0, "resources": [], "resources_total": 0,
                    "resources_uncited": 0, "activities": [], "activities_uncited": 0, "complete": False, "available": False}
        preds = {"identifier": DCTERMS.identifier, "title": DCTERMS.title, "publisher": DCTERMS.publisher,
                 "license": DCTERMS.license, "citation": DCTERMS.bibliographicCitation, "landing_page": DCAT.landingPage}
        graphs = [g for g in (self.observed_kg, self.prediction_kg) if g is not None]
        datasets = []
        for d, (ident, _, url, title) in sorted(self._datasets.items(), key=lambda kv: kv[1][0]):
            missing = [label for key, label in self.DATASET_FIELDS
                       if not any(g.value(d, preds[key]) is not None for g in graphs)]
            datasets.append({"uri": str(d), "identifier": ident, "title": title, "landing_page": url,
                             "missing": missing, "complete": not missing})
        resources = []
        for graph_name, g in (("observed", self.observed_kg), ("prediction", self.prediction_kg)):
            if g is None:
                continue
            for cls in self.CITED_CLASSES[graph_name]:
                subjects = list(g.subjects(RDF.type, CLEETS[cls]))
                if not subjects:
                    continue
                uncited = [str(s) for s in subjects if not self._reaches_dataset(g, s)]
                resources.append({"graph": graph_name, "class": cls, "total": len(subjects),
                                  "uncited": len(uncited), "examples": uncited[:3]})
        activities = []
        if self.prediction_kg is not None:
            g = self.prediction_kg
            for act in sorted(g.subjects(RDF.type, PROV.Activity), key=str):
                used = [d for d in g.objects(act, PROV.used) if d in self._datasets]
                activities.append({"uri": str(act), "label": str(g.value(act, RDFS.label) or _local(act)),
                                   "family": self._activity_family.get(act, _local(act)),
                                   "used": len(used), "has_citation": g.value(act, DCTERMS.bibliographicCitation) is not None,
                                   "has_paper_section": g.value(act, CLEETS.paperSection) is not None})
        audit = {
            "datasets": datasets,
            "datasets_total": len(datasets), "datasets_complete": sum(1 for d in datasets if d["complete"]),
            "resources": resources,
            "resources_total": sum(r["total"] for r in resources), "resources_uncited": sum(r["uncited"] for r in resources),
            "activities": activities,
            "activities_uncited": sum(1 for a in activities if not (a["used"] and a["has_citation"])),
        }
        audit["complete"] = (audit["datasets_complete"] == audit["datasets_total"] and audit["resources_uncited"] == 0
                             and audit["activities_uncited"] == 0)
        self._citation_audit = audit
        return dict(audit)

    # -------------------------------------------------------------------- misc
    def __len__(self) -> int:
        return self._counts["observed_triples"] + self._counts["prediction_triples"]

    def __repr__(self) -> str:
        return (f"CLEETSKG(observed={self._counts['observed_triples']} triples, prediction={self._counts['prediction_triples']} triples, "
                f"lads={len(self._lads)}, predictions={self._prediction_count}{', snapshot' if self._snapshot else ''})")

    # ------------------------------------------------------------------ snapshots
    SNAPSHOT_VERSION = 1

    def to_snapshot(self) -> dict:
        """Serialise every index to plain JSON types so a CLEETSKG can be rebuilt without rdflib
        (used by build_site.py for the static GitHub Pages version of CLEETS-CHAT)."""
        subject_sources: Dict[str, List[str]] = {}
        if not self._snapshot:
            g_o, g_p = self.observed_kg, self.prediction_kg
            for rows in self._obs_by_lad.values():
                for r in rows:
                    subj = URIRef(r["subject"])
                    srcs = [str(d) for pred in (DCTERMS.source, PROV.wasDerivedFrom) for d in g_o.objects(subj, pred) if d in self._datasets]
                    subject_sources[r["subject"]] = list(dict.fromkeys(srcs))
            for rows in list(self._pred.values()) + list(self._area_pred.values()):
                for r in rows:
                    subj = URIRef(r["subject"])
                    srcs = [str(d) for d in g_p.objects(subj, DCTERMS.source) if d in self._datasets]
                    subject_sources[r["subject"]] = list(dict.fromkeys(srcs))
        else:
            subject_sources = dict(self._subject_sources)
        return {
            "version": self.SNAPSHOT_VERSION,
            "counts": self._counts,
            "lads": {str(k): v for k, v in self._lads.items()},
            "lad_code": {str(k): v for k, v in self._lad_code.items()},
            "alias": {k: str(v) for k, v in self._alias.items()},
            "periods": {str(k): list(v) for k, v in self._periods.items()},
            "families": {k: {**f, "activities": list(f["activities"]), "used": list(f["used"])} for k, f in self._families.items()},
            "pred": [{"lad_uri": str(k[0]), "scenario": k[1], "rows": rows} for k, rows in self._pred.items()],
            "area_pred": [{"lad_uri": str(k[0]), "scenario": k[1], "rows": rows} for k, rows in self._area_pred.items()],
            "area_names": {str(k): v for k, v in self._area_names.items()},
            "milestones": self._milestones,
            "scenarios": self._scenarios,
            "pred_periods": [list(p) for p in self._pred_periods],
            "hier": self._hier, "effects": self._effects, "turnover": self._turnover, "ceilings": self._ceilings,
            "charging": self._charging, "residuals": self._residuals, "metrics": self._metrics,
            "obs_by_lad": {str(k): v for k, v in self._obs_by_lad.items()},
            "datasets": {str(k): list(v) for k, v in self._datasets.items()},
            "dataset_meta": self._dataset_meta,
            "observed_datasets": [str(d) for d in self._observed_datasets],
            "ontology_terms": self.ontology_terms(),
            "activity": self.prediction_activity(),
            "subject_sources": subject_sources,
            "citation_audit": self.citation_audit(),
            "dataset_catalogue": self.dataset_catalogue(),
        }

    @classmethod
    def from_snapshot(cls, data) -> "CLEETSKG":
        """Rebuild a CLEETSKG from to_snapshot() output (a dict or JSON text). No rdflib needed."""
        import json as _json
        if isinstance(data, (str, bytes)):
            data = _json.loads(data)
        self = cls.__new__(cls)
        self._snapshot = True
        self.observed_kg = self.prediction_kg = None
        self.observed_path, self.prediction_path, self.prediction_paths = "snapshot", "snapshot", ["snapshot"]
        self.CLEETS, self.DATA = CLEETS, DATA
        self.DCAT, self.DCTERMS, self.RDFS, self.PROV, self.SKOS = DCAT, DCTERMS, RDFS, PROV, SKOS
        self._counts = data["counts"]
        self._lads = dict(data["lads"])
        self._lad_code = dict(data["lad_code"])
        self._alias = dict(data["alias"])
        self._alias_patterns = [
            (re.compile(r"(?<![\w-])" + re.escape(a) + r"(?![\w-])", re.IGNORECASE), uri)
            for a, uri in sorted(self._alias.items(), key=lambda kv: -len(kv[0]))
        ]
        self._periods = {k: tuple(v) for k, v in data["periods"].items()}
        self._families = data["families"]
        self._activity_family = {a: k for k, f in self._families.items() for a in f["activities"]}
        self._pred = defaultdict(list, {(e["lad_uri"], e["scenario"]): e["rows"] for e in data["pred"]})
        self._area_pred = defaultdict(list, {(e["lad_uri"], e["scenario"]): e["rows"] for e in data["area_pred"]})
        self._area_names = dict(data["area_names"])
        self._prediction_count = sum(len(v) for v in self._pred.values())
        self._milestones = data["milestones"]
        self._scenarios = data["scenarios"]
        self._pred_periods = [tuple(p) for p in data["pred_periods"]]
        self._hier, self._effects, self._turnover, self._ceilings = data["hier"], data["effects"], data["turnover"], data["ceilings"]
        self._charging, self._residuals, self._metrics = data["charging"], data["residuals"], data["metrics"]
        self._obs_by_lad = defaultdict(list, data["obs_by_lad"])
        self._datasets = {k: tuple(v) for k, v in data["datasets"].items()}
        self._dataset_meta = data.get("dataset_meta", {})
        self._observed_datasets = set(data["observed_datasets"])
        self._ontology_terms = data.get("ontology_terms", [])
        self._activity = data.get("activity", {})
        self._subject_sources = data.get("subject_sources", {})
        self._citation_audit = data.get("citation_audit", {})
        self._dataset_catalogue = data.get("dataset_catalogue", [])
        return self


if __name__ == "__main__":
    kg = CLEETSKG()
    print(kg)
    print("\nWelsh LADs:", ", ".join(kg.lad_names()))
    rows = kg.prediction_rows(2045, "central", "Cardiff")
    if rows:
        r = rows[-1]
        print(f"\nCardiff {r['period']} central: keepership {r['keepership']:,.0f}, share {r['adoption_share']:.2%}")
    top = kg.prediction_year_summary(2045, "central")[:3]
    print("Top 3 (2045, central):", [(r["lad_name"], int(r["keepership"])) for r in top])
    latest = kg.latest_observation("Cardiff", "keepership")
    if latest:
        print("Latest observed Cardiff keepership:", latest["period"], latest["value"])
        print("Sources:", kg.source_links_for_subject(latest["subject"]))
