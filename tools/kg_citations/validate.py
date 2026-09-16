"""validate.py: re-parse the enriched KG, run the bundled SHACL shapes, run the SPARQL
coverage audit, check for dangling references, and simulate CLEETS-CHAT retrieval."""
import sys, time, re
from collections import Counter
from rdflib import Graph, URIRef, Literal
from rdflib.namespace import DCAT, DCTERMS, PROV, RDF, RDFS, SH
import pyshacl

path = sys.argv[1]
t0 = time.time()
g = Graph(); g.parse(path, format="turtle")
print(f"parsed {len(g)} triples in {time.time()-t0:.1f}s")

# 1. SPARQL coverage audit (Q3 from citations.sparql)
def block(tag):
    body = open("citations.sparql").read().split(f"# {tag}.")[1].split("# ----")[0]
    return "\n".join(l for l in body.splitlines()[1:] if not l.strip().startswith("#"))
q3 = block("Q3")
prefixes = "\n".join(l for l in open("citations.sparql").read().splitlines() if l.startswith("PREFIX"))
uncited = list(g.query(prefixes + "\n" + q3))
print("Q3 uncited individuals:", len(uncited))

# 2. every dcat:Dataset has a citation, licence, landing page, publisher
for ds in g.subjects(RDF.type, DCAT.Dataset):
    missing = [p for p in (DCTERMS.bibliographicCitation, DCTERMS.license, DCAT.landingPage, DCTERMS.publisher, DCTERMS.title) if (ds, p, None) not in g]
    if missing: print("dataset missing", ds, missing)
print("datasets:", len(set(g.subjects(RDF.type, DCAT.Dataset))))

# 3. dangling object references (URIs in cleets namespaces used as objects but never described)
dangling = Counter()
for s, p, o in g:
    if isinstance(o, URIRef) and str(o).startswith("https://w3id.org/def/cleets") and (o, None, None) not in g:
        dangling[p] += 1
print("dangling in-namespace objects by predicate:", dict(dangling))

# 4. Q1 and Q2 run
q1 = block("Q1")
rows = list(g.query(prefixes + "\n" + q1))
print("Q1 rows for a derived observation:", len(rows))
for r in rows: print("   ", r.kind, r.key, str(r.citation)[:70], "...", ("method: " + str(r.method)[:60]) if r.method else "")
q2 = block("Q2")
for r in g.query(prefixes + "\n" + q2):
    print("Q2:", r.district, r.period, r.value, "| sources:", str(r.sources)[:160], "...")

# 5. SHACL with the shapes bundled in the graph
t0 = time.time()
conforms, results_graph, text = pyshacl.validate(g, shacl_graph=g, inference="none", abort_on_first=False, allow_warnings=True)
print(f"SHACL conforms: {conforms} ({time.time()-t0:.0f}s)")
if not conforms:
    print(text[:3000])

# 6. void:triples matches
print("void:triples =", g.value(URIRef("https://w3id.org/def/cleets/data"), URIRef("http://rdfs.org/ns/void#triples")), "actual", len(g))
