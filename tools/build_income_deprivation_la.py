#!/usr/bin/env python3
"""Write data/cleets_income_deprivation_la.ttl: people in income deprivation by Welsh local authority.

The values are the local authority estimates of the WIMD 2025 income indicator ("People in income
deprivation (percentage)") as published by the Welsh Government on StatsWales, table "Welsh Index of
Multiple Deprivation (WIMD) 2025 indicator data for local authorities and Wales". They are entered as
published; nothing is averaged or ranked. Each district gets one generic cleets:Observation of
cleetsdata:PeopleInIncomeDeprivationProperty that cites the table as its source. The district mean of
LSOA income deciles held in the released observation graph is left as it is.

    python tools/build_income_deprivation_la.py
"""
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, RDFS, URIRef
from rdflib.namespace import DCTERMS, PROV, XSD

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "data" / "cleets_income_deprivation_la.ttl"
C = Namespace("https://w3id.org/def/cleets#"); D = Namespace("https://w3id.org/def/cleets/data#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
LANDING = "https://stats.gov.wales/en-GB/c28ab0ec-5893-46c2-a372-98d4058ba415"
TITLE = "Welsh Index of Multiple Deprivation (WIMD) 2025 indicator data for local authorities and Wales"
WALES = 25.0
PEOPLE_IN_INCOME_DEPRIVATION = {   # district code: (name, percentage of people in income deprivation)
    "W06000001": ("Isle of Anglesey", 23.9), "W06000002": ("Gwynedd", 21.7), "W06000003": ("Conwy", 24.6),
    "W06000004": ("Denbighshire", 27.8), "W06000005": ("Flintshire", 20.8), "W06000006": ("Wrexham", 25.3),
    "W06000008": ("Ceredigion", 19.8), "W06000009": ("Pembrokeshire", 24.0), "W06000010": ("Carmarthenshire", 24.0),
    "W06000011": ("Swansea", 26.1), "W06000012": ("Neath Port Talbot", 28.7), "W06000013": ("Bridgend", 24.3),
    "W06000014": ("Vale of Glamorgan", 20.1), "W06000015": ("Cardiff", 25.8), "W06000016": ("Rhondda Cynon Taf", 26.9),
    "W06000018": ("Caerphilly", 28.2), "W06000019": ("Blaenau Gwent", 33.7), "W06000020": ("Torfaen", 28.8),
    "W06000021": ("Monmouthshire", 15.9), "W06000022": ("Newport", 28.1), "W06000023": ("Powys", 19.4),
    "W06000024": ("Merthyr Tydfil", 30.5)}

g = Graph()
for prefix, ns in dict(cleets=C, cleetsdata=D, dcat=DCAT, dcterms=DCTERMS, prov=PROV).items(): g.bind(prefix, ns)
ds = URIRef(str(D) + "dataset/WIMD2025LocalAuthority")
g.add((ds, RDF.type, DCAT.Dataset)); g.add((ds, RDF.type, PROV.Entity)); g.add((ds, RDFS.label, Literal("WIMD2025LocalAuthority")))
g.add((ds, DCTERMS.identifier, Literal("WIMD2025LocalAuthority"))); g.add((ds, DCTERMS.title, Literal(TITLE, lang="en")))
g.add((ds, DCTERMS.publisher, Literal("Welsh Government", lang="en"))); g.add((ds, DCTERMS.spatial, Literal("Wales", lang="en")))
g.add((ds, DCTERMS.license, URIRef("https://www.nationalarchives.gov.uk/doc/open-government-licence/version/3/")))
g.add((ds, DCAT.landingPage, URIRef(LANDING))); g.add((ds, DCAT.version, Literal("2025")))
g.add((ds, DCTERMS.bibliographicCitation, Literal(f"Welsh Government. {TITLE} [Data set]. StatsWales. {LANDING}", lang="en")))
g.add((ds, RDFS.comment, Literal(f"Source of the published percentage of people in income deprivation by local authority (Wales: {WALES:.1f}%).", lang="en")))
prop = D["PeopleInIncomeDeprivationProperty"]
g.add((prop, RDF.type, C.ObservableProperty))
g.add((prop, RDFS.label, Literal("people in income deprivation, percentage of residents (WIMD 2025 indicator, local authority estimate)", lang="en")))
year = D["Year2025"]
g.add((year, RDF.type, C.Time)); g.add((year, C.year, Literal(2025, datatype=XSD.integer))); g.add((year, RDFS.label, Literal("2025")))
for code, (name, pct) in PEOPLE_IN_INCOME_DEPRIVATION.items():
    node = D[f"PeopleInIncomeDeprivation_{code}_2025"]
    g.add((node, RDF.type, C.Observation)); g.add((node, C.forLAD, D[code])); g.add((node, C.forTime, year))
    g.add((node, C.hasSimpleResult, Literal(f"{pct:.1f}", datatype=XSD.decimal))); g.add((node, C.observesProperty, prop))
    g.add((node, RDFS.label, Literal(f"{name} people in income deprivation (percentage), WIMD 2025", lang="en")))
    g.add((node, RDFS.comment, Literal(f"Published local authority estimate; the Wales value is {WALES:.1f}%.", lang="en")))
    g.add((node, DCTERMS.source, ds)); g.add((node, PROV.wasDerivedFrom, ds))
g.serialize(destination=OUT, format="turtle")
print(f"{len(PEOPLE_IN_INCOME_DEPRIVATION)} observations, {len(g)} triples -> {OUT}")
