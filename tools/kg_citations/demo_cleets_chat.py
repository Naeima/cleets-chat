"""demo_cleets_chat.py: run the CLEETSKG.actual_search() logic (verbatim from the access layer)
over the enriched graph and attach citations with CitationResolver."""
import sys, time
from urllib.parse import unquote
from rdflib import Graph, RDFS
from cleets_citations import CitationResolver

def local_name(value):
    text = unquote(str(value)); return text.rsplit("#", 1)[-1].rsplit("/", 1)[-1]

def actual_search(graph, query, limit=40):          # copied from CLEETSKG.actual_search
    stop = {"show", "list", "tell", "give", "what", "which", "the", "me", "data", "have", "actual", "observed", "for", "in", "of", "and"}
    tokens = [t for t in query.casefold().replace("-", " ").split() if len(t) > 2 and t not in stop]
    results, seen = [], set()
    for s, p, o in graph:
        text = f"{local_name(s)} {local_name(p)} {o}".casefold()
        score = sum(token in text for token in tokens)
        if score == 0: continue
        key = (str(s), str(p), str(o))
        if key in seen: continue
        seen.add(key)
        label = next(graph.objects(s, RDFS.label), None)
        results.append({"subject": str(s), "subject_label": str(label) if label else local_name(s),
                        "predicate": str(p), "predicate_label": local_name(p), "object": str(o), "score": str(score)})
        if len(results) >= limit * 4: break
    results.sort(key=lambda r: (-int(r["score"]), r["subject_label"].casefold(), r["predicate_label"].casefold()))
    return tuple(results[:limit])

g = Graph(); g.parse(sys.argv[1], format="turtle")
resolver = CitationResolver(g)
for query in sys.argv[2:]:
    t0 = time.time()
    rows, refs = resolver.annotate(actual_search(g, query, limit=8))
    print(f"\n=== {query!r}  ({len(rows)} rows, {time.time()-t0:.2f}s)")
    for r in rows:
        print(f"  {r['subject_label'].strip():40.40s} {r['predicate_label']:22s} {r['object'][:38]:38s} refs={r['refs']}")
    print("References:")
    print("  " + resolver.format_references(refs).replace("\n", "\n  ")[:1800])
