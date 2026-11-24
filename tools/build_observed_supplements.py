#!/usr/bin/env python3
"""Write the observations added since the v1.3.0 graph release as two supplement graphs.

The companion notebook (EVAdoptionWalesPredictionsModels) builds its knowledge graph from the source
tables and writes it as cleets_kg_built.ttl. Three DfT vehicle licensing tables entered that graph after
the v1.3.0 release, together with two series taken from VEH0105:

    data/cleets_private_cars.ttl   VEH0142: private battery-electric cars by district and quarter
                                   VEH0105: private cars of all fuels (the denominator of the adoption share)
                                            and private petrol hybrid vehicles of all body types
    data/cleets_car_cohorts.ttl    VEH9901: licensed cars by district, keepership, fuel group and year of
                                            first registration (RDF Data Cube observations)
                                   VEH1111: licensed cars at each year end by year of first use, Great
                                            Britain and Wales (RDF Data Cube observations)

Nothing is recomputed here: dataset records, properties and observations are copied from the built graph,
selected by class and property. kg_service.OBSERVED_SUPPLEMENTS loads both files into the observed graph.

    python tools/build_observed_supplements.py path/to/cleets_kg_built.ttl
"""
import sys
from pathlib import Path

from rdflib import Graph, Literal, Namespace, RDF, URIRef
from rdflib.namespace import DCTERMS, PROV, RDFS, SKOS, XSD

ROOT = Path(__file__).resolve().parents[1]
SRC = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "data" / "cleets_kg_built.ttl"
C = Namespace("https://w3id.org/def/cleets#")
D = Namespace("https://w3id.org/def/cleets/data#")
DCAT = Namespace("http://www.w3.org/ns/dcat#")
QB = Namespace("http://purl.org/linked-data/cube#")
SDMX = Namespace("http://purl.org/linked-data/sdmx/2009/dimension#")
PUBLISHER = Literal("Department for Transport / Driver and Vehicle Licensing Agency", lang="en")   # as on the released records
SERIES = {"PrivateCarStockProperty": "VEH0105", "PrivateBatteryElectricCarsProperty": "VEH0142", "PrivateHybridStockProperty": "VEH0105"}
CUBES = ("VEH9901", "VEH1111")

built = Graph()
built.parse(SRC, format="turtle")


def new_graph() -> Graph:
    g = Graph()
    for prefix, ns in dict(cleets=C, cleetsdata=D, dcat=DCAT, dcterms=DCTERMS, prov=PROV, qb=QB, skos=SKOS, xsd=XSD).items():
        g.bind(prefix, ns)
    g.bind("sdmx-dimension", SDMX)
    return g


def copy(g: Graph, node) -> int:
    """Every statement about a node; blank nodes hanging from it are followed."""
    n = 0
    for p, o in built.predicate_objects(node):
        if (node, p, o) not in g:
            g.add((node, p, o))
            n += 1
        if not isinstance(o, (URIRef, Literal)):
            n += copy(g, o)
    return n


def dataset_record(g: Graph, ident: str):
    ds = D[f"dataset/{ident}"]
    assert (ds, RDF.type, DCAT.Dataset) in built, f"no dataset record for {ident} in {SRC}"
    copy(g, ds)
    g.set((ds, DCTERMS.publisher, PUBLISHER))
    return ds


# ------------------------------------------------------------------ private car series
cars = new_graph()
dataset_record(cars, "VEH0142")
counts = {}
for prop_name, ident in SERIES.items():
    prop = D[prop_name]
    assert (prop, RDF.type, C.ObservableProperty) in built, f"{prop_name} is not in {SRC}"
    copy(cars, prop)
    n = 0
    for obs in built.subjects(C.observesProperty, prop):
        assert D[f"dataset/{ident}"] in set(built.objects(obs, DCTERMS.source)), f"{obs} does not cite {ident}"
        copy(cars, obs)
        n += 1
    counts[prop_name] = n
cars.serialize(destination=ROOT / "data" / "cleets_private_cars.ttl", format="turtle")
print(f"cleets_private_cars.ttl: {len(cars):,} triples; " + ", ".join(f"{k.replace('Property', '')} {v:,}" for k, v in counts.items()))

# ------------------------------------------------------------------ cohort tables (RDF Data Cube)
cube = new_graph()
datasets = {ident: dataset_record(cube, ident) for ident in CUBES}
linked = set()
per_table = {ident: 0 for ident in CUBES}
for obs in built.subjects(RDF.type, QB.Observation):
    ds = built.value(obs, QB.dataSet)
    ident = next((i for i, d in datasets.items() if d == ds), None)
    assert ident is not None, f"{obs} belongs to an unexpected data set {ds}"
    copy(cube, obs)
    per_table[ident] += 1
    for p, o in built.predicate_objects(obs):
        if isinstance(o, URIRef) and p not in (RDF.type, QB.dataSet, DCTERMS.source, C.forLAD, SDMX.refPeriod):
            linked.add(o)        # fuel group, keepership, area concepts and the aggregation activity
        if p != RDF.type:
            linked.add(p)        # dimension and measure properties
for node in sorted(linked, key=str):
    if str(node).startswith(str(D)) and not any(True for _ in built.subjects(RDF.type, C.WelshLAD) if _ == node):
        copy(cube, node)
cube.serialize(destination=ROOT / "data" / "cleets_car_cohorts.ttl", format="turtle")
print(f"cleets_car_cohorts.ttl: {len(cube):,} triples; " + ", ".join(f"{k} {v:,} observations" for k, v in per_table.items()))
