#!/usr/bin/env python3
"""enrich_citations.py: add a citation layer to CLEETS-KG so that CLEETS-CHAT can
list the source of every retrieved triple.

Design (all vocabulary already used by the graph: dcterms, dcat, prov, schema.org, void, shacl):

  retrievable subject --dcterms:source--> dcat:Dataset --dcterms:bibliographicCitation--> "Harvard string"
                      --prov:wasGeneratedBy--> prov:Activity (derivation method; cite the KG itself)
                      --rdfs:isDefinedBy--> owl:Ontology (definitions; cite the ontology)

Nothing in the rendered citations is invented: every field comes from the graph itself or
from cleets_sources.json, where each value carries a verification note. Fields that are
null in the manifest are omitted, never replaced with placeholder text.

Usage:
  python enrich_citations.py --in cleets_kg_v1301.ttl --out cleets_kg_v1301_cited.ttl \
      --manifest cleets_sources.json [--version 1.3.1] [--strip-label-whitespace] \
      [--no-fingerprints] [--no-derivations] [--no-lads] [--no-shapes] [--report report.json]
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import re
import sys
from collections import Counter, defaultdict
from pathlib import Path

from rdflib import BNode, Graph, Literal, Namespace, URIRef
from rdflib.namespace import DCAT, DCTERMS, OWL, PROV, RDF, RDFS, SH, SKOS, XSD

CLEETS = Namespace("https://w3id.org/def/cleets#")
CDATA = Namespace("https://w3id.org/def/cleets/data#")
CAG = Namespace("https://w3id.org/def/cleets/agent#")
CSH = Namespace("https://w3id.org/def/cleets/shapes#")
SCHEMA = Namespace("https://schema.org/")
TIME = Namespace("http://www.w3.org/2006/time#")
VOID = Namespace("http://rdfs.org/ns/void#")
FOAF = Namespace("http://xmlns.com/foaf/0.1/")

KG_IRI = URIRef("https://w3id.org/def/cleets/data")
ONT_IRI = URIRef("https://w3id.org/def/cleets")

MONTHS = ["January", "February", "March", "April", "May", "June", "July",
          "August", "September", "October", "November", "December"]


# ----------------------------------------------------------------------------- helpers
def en(text: str) -> Literal:
    return Literal(text, lang="en")


def set_single(g: Graph, s, p, o) -> None:
    """Replace every value of (s, p) with o."""
    g.remove((s, p, None))
    g.add((s, p, o))


def fmt_date(iso: str) -> str:
    d = dt.date.fromisoformat(iso)
    return f"{d.day} {MONTHS[d.month - 1]} {d.year}"


def harvard_dataset(d: dict, title: str, licence_label: str | None) -> str:
    """Cite Them Right style Harvard reference for a data set. Omits unknown parts."""
    who = d["publisher_string"]
    year = f"({d['year']})" if d.get("year") else "(no date)"
    t = title
    if d.get("edition") and d["edition"] not in t and (not d.get("series") or d["edition"] not in d["series"]):
        t = f"{t} ({d['edition']} edition)"
    parts = [f"{who} {year} {t} [{d.get('type_label') or 'Data set'}]."]
    if d.get("series"):
        parts.append(f"{d['series']}.")
    if d.get("doi"):
        url = f"https://doi.org/{d['doi']}"
    else:
        url = d.get("access_url") or d["landing_page"]
    parts.append(f"Available at: {url}")
    if d.get("accessed"):
        parts.append(f"(Accessed: {fmt_date(d['accessed'])}).")
    return " ".join(parts)


def harvard_authors(names: list[str], amp: bool = False) -> str:
    """'Naeima Hamed' -> 'Hamed, N.'; join with 'and' (or '&')."""
    out = []
    for n in names:
        bits = n.split()
        surname = bits[-1]
        initials = " ".join(f"{b[0]}." for b in bits[:-1])
        out.append(f"{surname}, {initials}")
    if len(out) == 1:
        return out[0]
    joiner = " & " if amp else " and "
    return ", ".join(out[:-1]) + joiner + out[-1]


def ordered_names_from_citation(citation: str, names: list[str]) -> list[str]:
    """Order full names by the position of their surname in an existing citation string."""
    def pos(n):
        i = citation.find(n.split()[-1])
        return i if i >= 0 else 10**9
    return sorted(names, key=pos)


def quarter_bounds(year: int, q: int) -> tuple[str, str]:
    start = dt.date(year, 3 * (q - 1) + 1, 1)
    end_month = 3 * q
    next_start = dt.date(year + (end_month // 12), (end_month % 12) + 1, 1)
    end = next_start - dt.timedelta(days=1)
    return start.isoformat(), end.isoformat()


# ----------------------------------------------------------------------------- steps
def add_publisher_agents(g: Graph, manifest: dict, report: dict) -> dict[str, URIRef]:
    agents = {}
    n0 = len(g)
    for key, p in manifest["publishers"].items():
        a = URIRef(p["iri"])
        agents[key] = a
        if (a, RDF.type, None) not in g:
            g.add((a, RDF.type, SCHEMA.GovernmentOrganization))
            g.add((a, RDF.type, PROV.Agent))
            g.add((a, RDFS.label, en(p["name"])))
            g.add((a, SCHEMA.name, Literal(p["name"])))
            g.add((a, SCHEMA.url, URIRef(p["url"])))
            if p.get("country"):
                addr = BNode()
                g.add((a, SCHEMA.address, addr))
                g.add((addr, RDF.type, SCHEMA.PostalAddress))
                g.add((addr, SCHEMA.addressCountry, Literal(p["country"])))
    for key, p in manifest["publishers"].items():
        if p.get("parent"):
            g.add((agents[key], SCHEMA.parentOrganization, agents[p["parent"]]))
    report["publisher_agents_added"] = len(g) - n0
    return agents


def coverage_for_dataset(g: Graph, ds: URIRef) -> tuple[str | None, str | None, set[str]]:
    """Temporal and spatial coverage computed from the observations that cite ds."""
    starts, ends, nations = [], [], set()
    for obs in g.subjects(DCTERMS.source, ds):
        m = re.search(r"_([EW])\d{8}_", str(obs))
        if m:
            nations.add("England" if m.group(1) == "E" else "Wales")
        d = g.value(obs, DCTERMS.date)
        if d is not None:
            starts.append(str(d)); ends.append(str(d)); continue
        t = g.value(obs, CLEETS.forTime)
        if t is None:
            continue
        y, q = g.value(t, CLEETS.year), g.value(t, CLEETS.quarter)
        if y is not None and q is not None:
            s, e = quarter_bounds(int(y), int(q)); starts.append(s); ends.append(e)
        elif y is not None:
            starts.append(f"{int(y)}-01-01"); ends.append(f"{int(y)}-12-31")
        else:
            m2 = re.search(r"Year(\d{4})$", str(t))
            if m2:
                starts.append(f"{m2.group(1)}-01-01"); ends.append(f"{m2.group(1)}-12-31")
    return (min(starts) if starts else None, max(ends) if ends else None, nations)


def enrich_datasets(g: Graph, manifest: dict, agents: dict, report: dict) -> None:
    lic = manifest["licence"]
    changes = []
    n0 = len(g)
    for key, d in manifest["datasets"].items():
        ds = URIRef(d["iri"])
        is_new = (ds, RDF.type, None) not in g
        if is_new:
            g.add((ds, RDF.type, DCAT.Dataset))
            g.add((ds, RDF.type, PROV.Entity))
            g.add((ds, RDFS.label, Literal(d["identifier"])))
            if d.get("description"):
                g.add((ds, DCTERMS.description, en(d["description"])))
        prev_title = str(g.value(ds, DCTERMS.title) or "")
        title = d.get("title") or prev_title
        if d.get("title") and d["title"] != prev_title:
            if d.get("keep_previous_title_as_alternative") and prev_title:
                g.add((ds, DCTERMS.alternative, en(prev_title)))
            set_single(g, ds, DCTERMS.title, en(title))
            changes.append({"dataset": key, "field": "dcterms:title", "before": prev_title, "after": title})
        if (ds, DCTERMS.publisher, None) not in g:
            g.add((ds, DCTERMS.publisher, en(d["publisher_string"])))
        g.add((ds, DCTERMS.identifier, Literal(d["identifier"])))
        set_single(g, ds, DCAT.landingPage, URIRef(d["landing_page"]))
        licence = lic[d["licence"]]
        set_single(g, ds, DCTERMS.license, URIRef(licence["iri"]))
        for pk in d["publishers"]:
            g.add((ds, PROV.wasAttributedTo, agents[pk]))
        if d.get("source_note"):
            g.add((ds, DCTERMS.provenance, en(d["source_note"])))
        if d.get("series"):
            series = URIRef(f"{CDATA}series/{re.sub(r'[^A-Za-z0-9]+', '', d['series'].title())}")
            g.add((series, RDF.type, URIRef(str(DCAT) + "DatasetSeries")))
            g.add((series, DCTERMS.title, en(d["series"])))
            for pk in d["publishers"]:
                g.add((series, PROV.wasAttributedTo, agents[pk]))
            g.add((ds, URIRef(str(DCAT) + "inSeries"), series))
        if d.get("edition"):
            set_single(g, ds, URIRef(str(DCAT) + "version"), Literal(d["edition"]))
        if d.get("issued"):
            set_single(g, ds, DCTERMS.issued, Literal(d["issued"], datatype=XSD.date))
        if d.get("doi"):
            g.add((ds, DCTERMS.identifier, Literal(f"https://doi.org/{d['doi']}")))
        if d.get("access_url"):
            dist = URIRef(f"{d['iri']}/distribution")
            g.add((ds, DCAT.distribution, dist))
            g.add((dist, RDF.type, DCAT.Distribution))
            g.add((dist, DCAT.accessURL, URIRef(d["access_url"])))
            g.add((dist, DCTERMS.license, URIRef(licence["iri"])))
            g.add((dist, DCTERMS.title, en(f"{d['identifier']}: official access page")))
        if d.get("accessed"):
            act = URIRef(f"{CDATA}Ingestion_{d['identifier']}")
            g.add((act, RDF.type, PROV.Activity))
            g.add((act, RDFS.label, en(f"Ingestion of {d['identifier']} into CLEETS-KG")))
            g.add((act, PROV.used, ds))
            g.add((act, PROV.endedAtTime, Literal(f"{d['accessed']}T00:00:00Z", datatype=XSD.dateTime)))
            g.add((act, PROV.wasAssociatedWith, CAG.CLEETSDataScienceGroup))
            g.add((KG_IRI, PROV.wasGeneratedBy, act))
        # coverage computed from the graph itself
        start, end, nations = coverage_for_dataset(g, ds)
        if key == "ONSOpenGeography":
            nations = {"England", "Wales"}
        if start and end:
            per = BNode()
            g.remove((ds, DCTERMS.temporal, None))
            g.add((ds, DCTERMS.temporal, per))
            g.add((per, RDF.type, DCTERMS.PeriodOfTime))
            g.add((per, DCAT.startDate, Literal(start, datatype=XSD.date)))
            g.add((per, DCAT.endDate, Literal(end, datatype=XSD.date)))
        if nations:
            label = "England and Wales" if nations == {"England", "Wales"} else next(iter(nations))
            set_single(g, ds, DCTERMS.spatial, en(label))
        # the citation string
        cite = harvard_dataset(d, title, licence["label"])
        set_single(g, ds, DCTERMS.bibliographicCitation, en(cite))
        d["_rendered"] = cite
        d["_coverage"] = {"start": start, "end": end, "spatial": sorted(nations)}
    report["dataset_title_changes"] = changes
    report["dataset_triples_added"] = len(g) - n0
    report["rendered_citations"] = {k: v["_rendered"] for k, v in manifest["datasets"].items()}


def enrich_kg_record(g: Graph, manifest: dict, version: str | None, report: dict) -> None:
    kg = manifest["kg"]
    old = str(g.value(KG_IRI, DCTERMS.bibliographicCitation) or "")
    new = old
    if version:
        set_single(g, KG_IRI, DCTERMS.hasVersion, Literal(version))
        new = re.sub(r"v\d+\.\d+\.\d+", f"v{version}", new)
        t = str(g.value(KG_IRI, DCTERMS.title))
        set_single(g, KG_IRI, DCTERMS.title, en(re.sub(r"v\d+\.\d+\.\d+", f"v{version}", t)))
    if kg.get("doi"):
        new = re.sub(r"https://doi\.org/10\.5281/zenodo\.X+\s*\(DOI to be minted on deposit\)",
                     f"https://doi.org/{kg['doi']}", new)
        g.add((KG_IRI, DCTERMS.identifier, Literal(f"https://doi.org/{kg['doi']}")))
        set_single(g, KG_IRI, DCAT.landingPage, URIRef(f"https://doi.org/{kg['doi']}"))
    else:
        set_single(g, KG_IRI, DCAT.landingPage, URIRef(kg["landing_page"]))
    issued = g.value(KG_IRI, DCTERMS.issued)
    if issued is not None and not re.search(r"\(\d{4}\)", new):
        new = new.replace(" CLEETS-KG", f" ({str(issued)[:4]}) CLEETS-KG", 1)
    if kg.get("accessed"):
        new = new.rstrip(".") + f" (Accessed: {fmt_date(kg['accessed'])})."
    if (KG_IRI, RDFS.label, None) not in g:
        g.add((KG_IRI, RDFS.label, Literal(f"CLEETS-KG v{g.value(KG_IRI, DCTERMS.hasVersion)}")))
    g.add((KG_IRI, DCTERMS.identifier, Literal(str(KG_IRI))))
    if new != old:
        set_single(g, KG_IRI, DCTERMS.bibliographicCitation, en(new))
    report["kg_citation"] = {"before": old, "after": new}


def enrich_ontology_record(g: Graph, report: dict) -> None:
    old = str(g.value(ONT_IRI, DCTERMS.bibliographicCitation) or "")
    names = [str(g.value(c, SCHEMA.name) or g.value(c, RDFS.label)) for c in g.objects(ONT_IRI, DCTERMS.creator)]
    names = ordered_names_from_citation(old, names)
    created = g.value(ONT_IRI, DCTERMS.created)
    year = str(created)[:4] if created else "no date"
    version = str(g.value(ONT_IRI, OWL.versionInfo) or "")
    title = str(g.value(ONT_IRI, DCTERMS.title))
    pub = g.value(ONT_IRI, DCTERMS.publisher)
    pub_label = str(g.value(pub, RDFS.label) or pub) if pub else ""
    parent = g.value(pub, SCHEMA.parentOrganization) if pub else None
    if parent is not None:
        pub_label = f"{pub_label}, {g.value(parent, RDFS.label)}"
    new = (f"{harvard_authors(names)} ({year}) {title}"
           + (f", version {version}" if version else "")
           + f" [Ontology]. {pub_label}. Available at: {ONT_IRI}")
    set_single(g, ONT_IRI, DCTERMS.bibliographicCitation, en(new))
    if (ONT_IRI, DCAT.landingPage, None) not in g:
        g.add((ONT_IRI, DCAT.landingPage, ONT_IRI))
    report["ontology_citation"] = {"before": old, "after": new}


def verify_and_add_derivations(g: Graph, report: dict) -> None:
    """Describe how each derived indicator is computed, verifying the formula against the data."""
    n0 = len(g)
    ds = lambda k: URIRef(f"{CDATA}dataset/{k}")

    pop, charger, keep = {}, {}, {}
    for s in g.subjects(RDF.type, CLEETS.Population):
        m = re.search(r"Population_(\w+)_(\d{4})$", str(s)); pop[(m.group(1), int(m.group(2)))] = float(g.value(s, CLEETS.populationValue))
    for s in g.subjects(RDF.type, CLEETS.EVChargerCount):
        m = re.search(r"_(\w\d{8})_(\d{4})Q(\d)$", str(s)); charger[(m.group(1), int(m.group(2)), int(m.group(3)))] = float(g.value(s, CLEETS.chargerCountValue))
    for s in g.subjects(RDF.type, CLEETS.EVKeepership):
        m = re.search(r"_(\w\d{8})_(\d{4})Q(\d)$", str(s)); keep[(m.group(1), int(m.group(2)), int(m.group(3)))] = float(g.value(s, CLEETS.keepershipValue))

    def pop_for(lad, yr):
        if (lad, yr) in pop:
            return pop[(lad, yr)]
        ys = [y for (l, y) in pop if l == lad and y <= yr]
        return pop[(lad, max(ys))] if ys else None

    def value_of(s):
        v = g.value(s, CLEETS.hasSimpleResult)
        if v is None:
            v = g.value(s, CLEETS.keeperChargerRatio)
        return float(v) if v is not None else None

    specs = [
        ("ChargersPer100kResidents", CDATA.ChargersPer100kResidentsProperty, ["EVCI9001", "StatsWalesPopulation"],
         "public charge points per 100,000 residents",
         "cleets:hasSimpleResult = cleets:chargerCountValue(LAD, quarter) / cleets:populationValue(LAD, mid-year estimate for the quarter's calendar year, or the latest earlier mid-year estimate where that year is not yet published) x 100,000.",
         lambda l, y, q: (charger[(l, y, q)] / pop_for(l, y) * 1e5) if (l, y, q) in charger and pop_for(l, y) else None),
        ("EVsPerThousandResidents", CDATA.EVsPerThousandResidentsProperty, ["VEH0132", "StatsWalesPopulation"],
         "private BEV keeperships per 1,000 residents",
         "cleets:hasSimpleResult = cleets:keepershipValue(LAD, quarter) / cleets:populationValue(LAD, mid-year estimate for the quarter's calendar year, or the latest earlier mid-year estimate where that year is not yet published) x 1,000.",
         lambda l, y, q: (keep[(l, y, q)] / pop_for(l, y) * 1e3) if (l, y, q) in keep and pop_for(l, y) else None),
        ("KeepersPerCharger", CLEETS.KeeperChargerRatioProperty, ["VEH0132", "EVCI9001"],
         "keepers per charger",
         "cleets:keeperChargerRatio = cleets:keepershipValue(LAD, quarter) / cleets:chargerCountValue(LAD, quarter).",
         lambda l, y, q: (keep[(l, y, q)] / charger[(l, y, q)]) if (l, y, q) in keep and charger.get((l, y, q)) else None),
    ]
    summary = {}
    for name, prop, inputs, label, formula, fn in specs:
        act = URIRef(f"{CDATA}Derivation_{name}")
        ok = bad = missing = 0
        for obs in g.subjects(CLEETS.observesProperty, prop):
            m = re.search(r"_(\w\d{8})_(\d{4})Q(\d)$", str(obs))
            exp = fn(m.group(1), int(m.group(2)), int(m.group(3))) if m else None
            got = value_of(obs)
            if exp is None or got is None:
                missing += 1
            elif abs(got - exp) <= max(1e-3, abs(exp) * 1e-4):
                ok += 1
            else:
                bad += 1
            g.add((obs, PROV.wasGeneratedBy, act))
        verdict = (f"Verified on {dt.date.today().isoformat()}: the formula reproduces {ok} of {ok + bad + missing} values in this graph"
                   + (f" ({bad} mismatches, {missing} with missing inputs)" if bad or missing else "")
                   + " to a relative tolerance of 1e-4.")
        g.add((act, RDF.type, PROV.Activity))
        g.add((act, RDFS.label, en(f"Derivation of {label}")))
        g.add((act, RDFS.comment, en(f"{formula} {verdict}")))
        for k in inputs:
            g.add((act, PROV.used, ds(k)))
        g.add((act, PROV.wasAssociatedWith, CAG.CLEETSDataScienceGroup))
        g.add((act, RDFS.seeAlso, prop))
        g.add((act, DCTERMS.source, KG_IRI))
        summary[name] = {"ok": ok, "mismatch": bad, "missing": missing}

    # Income deprivation: LSOA-to-LAD aggregation described by the instances' own comments.
    act = URIRef(f"{CDATA}Derivation_IncomeDeprivationLADMean")
    n_inc = 0
    for obs in g.subjects(RDF.type, CLEETS.IncomeDeprivation):
        g.add((obs, PROV.wasGeneratedBy, act)); n_inc += 1
    g.add((act, RDF.type, PROV.Activity))
    g.add((act, RDFS.label, en("Aggregation of WIMD 2025 income-domain LSOA deciles to local authority district")))
    g.add((act, RDFS.comment, en("cleets:incomeDeprivationValue = mean of the WIMD 2025 income-domain deciles of the LSOAs within the district (1 = most deprived), LSOAs assigned to districts with the ONS LSOA-to-LAD lookup; cleets:deprivationDecile = that mean rounded to the nearest integer. As stated in the rdfs:comment of each cleets:IncomeDeprivation individual; LSOA-level inputs are not redistributed in this graph, so the aggregation is documented rather than re-verified here.")))
    g.add((act, PROV.used, ds("WIMD2025")))
    g.add((act, PROV.used, ds("ONSGeoLookup")))
    g.add((act, PROV.wasAssociatedWith, CAG.CLEETSDataScienceGroup))
    g.add((act, RDFS.seeAlso, CLEETS.IncomeDeprivationProperty))
    g.add((act, DCTERMS.source, KG_IRI))
    summary["IncomeDeprivationLADMean"] = {"linked": n_inc}

    # data-namespace observable properties are defined by the KG, not the ontology
    for p in (CDATA.ChargersPer100kResidentsProperty, CDATA.EVsPerThousandResidentsProperty, CDATA.PrivateVehicleStockProperty):
        g.add((p, RDFS.isDefinedBy, KG_IRI))
    report["derivations"] = summary
    report["derivation_triples_added"] = len(g) - n0


def cite_lads(g: Graph, report: dict) -> None:
    n0 = len(g)
    geo = URIRef(f"{CDATA}dataset/ONSOpenGeography")
    n = 0
    for lad in set(g.subjects(RDF.type, CLEETS.WelshLAD)) | set(g.subjects(RDF.type, CLEETS.EnglishLAD)):
        g.add((lad, DCTERMS.source, geo)); n += 1
    report["lads_cited"] = n
    report["lad_triples_added"] = len(g) - n0


def type_fingerprints(g: Graph, report: dict) -> None:
    """prov:wasDerivedFrom targets under .../observation/<kind>/<hash> are source-row
    fingerprints that were never described. Type them so that nothing dangles."""
    n0 = len(g)
    kinds = Counter()
    for o in set(g.objects(None, PROV.wasDerivedFrom)):
        if "/observation/" in str(o) and (o, None, None) not in g:
            g.add((o, RDF.type, PROV.Entity))
            kinds[str(o).split("/observation/")[1].split("/")[0]] += 1
    report["fingerprints_typed"] = dict(kinds)
    report["fingerprint_triples_added"] = len(g) - n0


def add_shapes(g: Graph, report: dict) -> None:
    n0 = len(g)
    s = CSH.CitableDatasetShape
    g.add((s, RDF.type, SH.NodeShape))
    g.add((s, SH.targetClass, DCAT.Dataset))
    g.add((s, RDFS.comment, en("Every dataset record must carry the fields CLEETS-CHAT needs to render a citation.")))
    for path, minc, maxc, msg in [
        (DCTERMS.title, 1, None, "A citable dataset needs a title."),
        (DCTERMS.publisher, 1, None, "A citable dataset needs a publisher."),
        (DCTERMS.license, 1, None, "A citable dataset needs a licence."),
        (DCAT.landingPage, 1, None, "A citable dataset needs a landing page or DOI landing page."),
        (DCTERMS.bibliographicCitation, 1, 1, "A citable dataset needs exactly one rendered bibliographic citation."),
    ]:
        b = BNode()
        g.add((s, SH.property, b)); g.add((b, SH.path, path)); g.add((b, SH.minCount, Literal(minc)))
        if maxc:
            g.add((b, SH.maxCount, Literal(maxc)))
        g.add((b, SH.message, en(msg)))
    s2 = CSH.CitedNodeShape
    g.add((s2, RDF.type, SH.NodeShape))
    for tc in (CLEETS.Observation, CLEETS.Population, CLEETS.PopulationDensity, CLEETS.LAD):
        g.add((s2, SH.targetClass, tc))
    g.add((s2, RDFS.comment, en("Every observation, population figure and district must cite at least one dataset record.")))
    b = BNode()
    g.add((s2, SH.property, b)); g.add((b, SH.path, DCTERMS.source)); g.add((b, SH.minCount, Literal(1)))
    g.add((b, SH["class"], DCAT.Dataset))
    g.add((b, SH.message, en("Every retrievable individual must cite a dcat:Dataset via dcterms:source.")))
    report["shape_triples_added"] = len(g) - n0


def strip_label_whitespace(g: Graph, report: dict) -> None:
    n = 0
    for p in (RDFS.label, SKOS.prefLabel):
        for s, o in list(g.subject_objects(p)):
            if isinstance(o, Literal) and str(o) != str(o).strip():
                g.remove((s, p, o)); g.add((s, p, Literal(str(o).strip(), lang=o.language, datatype=o.datatype))); n += 1
    report["labels_stripped"] = n


def record_enrichment(g: Graph, args, report: dict) -> None:
    today = dt.date.today().isoformat()
    act = URIRef(f"{CDATA}CitationEnrichment_{today.replace('-', '')}")
    g.add((act, RDF.type, PROV.Activity))
    g.add((act, RDFS.label, en(f"Citation enrichment of CLEETS-KG, {today}")))
    g.add((act, RDFS.comment, en("Added rendered Harvard citations, licence, publisher agents, coverage and access records to every dataset record; described derivation methods as prov:Activity individuals; cited ONS Open Geography for district individuals; typed source-row fingerprints as prov:Entity; added SHACL shapes that keep future records citable. Script: enrich_citations.py with manifest cleets_sources.json.")))
    g.add((act, PROV.endedAtTime, Literal(dt.datetime.now(dt.timezone.utc).replace(microsecond=0).isoformat(), datatype=XSD.dateTime)))
    g.add((act, PROV.wasAssociatedWith, CAG.CLEETSDataScienceGroup))
    g.add((KG_IRI, PROV.wasGeneratedBy, act))
    set_single(g, KG_IRI, DCTERMS.modified, Literal(today, datatype=XSD.date))


# ----------------------------------------------------------------------------- main
def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--in", dest="inp", required=True)
    ap.add_argument("--out", dest="out", required=True)
    ap.add_argument("--manifest", default="cleets_sources.json")
    ap.add_argument("--version", help="new dcterms:hasVersion for the KG record (e.g. 1.3.1); default: unchanged")
    ap.add_argument("--strip-label-whitespace", action="store_true", help="trim leading/trailing spaces in rdfs:label and skos:prefLabel")
    ap.add_argument("--no-fingerprints", action="store_true")
    ap.add_argument("--no-derivations", action="store_true")
    ap.add_argument("--no-lads", action="store_true")
    ap.add_argument("--no-shapes", action="store_true")
    ap.add_argument("--report", default=None, help="write a JSON report of what changed")
    args = ap.parse_args(argv)

    manifest = json.loads(Path(args.manifest).read_text(encoding="utf-8"))
    g = Graph()
    g.parse(args.inp, format="turtle")
    report = {"input": args.inp, "triples_before": len(g)}

    agents = add_publisher_agents(g, manifest, report)
    enrich_datasets(g, manifest, agents, report)
    enrich_kg_record(g, manifest, args.version, report)
    enrich_ontology_record(g, report)
    if not args.no_derivations:
        verify_and_add_derivations(g, report)
    if not args.no_lads:
        cite_lads(g, report)
    if not args.no_fingerprints:
        type_fingerprints(g, report)
    if not args.no_shapes:
        add_shapes(g, report)
    if args.strip_label_whitespace:
        strip_label_whitespace(g, report)
    record_enrichment(g, args, report)
    set_single(g, KG_IRI, VOID.triples, Literal(len(g), datatype=XSD.integer))

    g.serialize(destination=args.out, format="turtle")
    report["triples_after"] = len(g)
    report["output"] = args.out
    if args.report:
        Path(args.report).write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({k: v for k, v in report.items() if k not in ("rendered_citations",)}, indent=2, ensure_ascii=False))
    print("\nRendered citations:")
    for k, v in report["rendered_citations"].items():
        print(f"  {k}: {v}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
