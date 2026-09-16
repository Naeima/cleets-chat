# CLEETS-KG citation layer for CLEETS-CHAT

Every subject that `CLEETSKG.actual_search()` can return now reaches a rendered citation in one hop, using vocabulary the graph already uses:

```
subject  --dcterms:source------>  dcat:Dataset   --dcterms:bibliographicCitation-->  "Harvard string"
subject  --prov:wasGeneratedBy->  prov:Activity  (derived indicator: method text + cite the KG)
subject  --rdfs:isDefinedBy---->  owl:Ontology   (definitions: cite the ontology)
anything else in the graph      ->  the KG's own citation (fallback in the resolver)
```

## Files

| File | Purpose |
|---|---|
| `cleets_kg_v1301_cited.ttl` | Enriched graph (96,479 triples; input had 87,824). SHACL-valid against the bundled shapes. |
| `enrich_citations.py` | Reproducible enrichment. Re-run whenever the manifest or the KG changes. |
| `cleets_sources.json` | Source manifest: titles, publishers, licence, URLs, year, edition, access date, DOI, plus a verification note per record. `null` fields are omitted from the citation; nothing is ever filled with placeholder text. |
| `cleets_citations.py` | `CitationResolver` for CLEETS-CHAT: `cite(subject)`, `annotate(rows)`, `format_references()`. |
| `citations.sparql` | The same logic as SPARQL (Q1 per subject, Q2 answer-and-cite, Q3 coverage audit, Q4 reference list for a result set). |
| `validate.py` | Re-parse, coverage audit, dangling-reference check, SHACL. |
| `demo_cleets_chat.py` | Runs your `actual_search()` logic over the enriched graph and prints answers with numbered references. |
| `enrichment_report.json` | Exactly what changed, including before/after for every altered title and citation. |

## Run

```bash
pip install rdflib pyshacl
python enrich_citations.py --in cleets_kg_v1301.ttl --out cleets_kg_v1301_cited.ttl \
    --manifest cleets_sources.json --report enrichment_report.json
python validate.py cleets_kg_v1301_cited.ttl
python demo_cleets_chat.py cleets_kg_v1301_cited.ttl "chargers per 100k residents 2024 Q4"
```

Options: `--version 1.3.1` bumps `dcterms:hasVersion` and the self-citation; `--strip-label-whitespace` trims the leading space present in 6,336 labels (" Cardiff"); `--no-fingerprints`, `--no-derivations`, `--no-lads`, `--no-shapes` switch individual steps off.

## Integrate

```python
from cleets_citations import CitationResolver

resolver = CitationResolver(kg.base_graph())          # once, after the observed graph loads
rows, references = resolver.annotate(kg.actual_search(query, limit))
footer = resolver.format_references(references)       # "[1] Department for Transport (2026) EVCI9001: ..."
```

Each row gains `refs` (e.g. `"[1, 3]"`); `references` is the numbered list with `citation`, `url`, `licence`, `kind` and, for derived indicators, the `note` holding the formula and its verification statement.

## What the manifest still needs from you

Per dataset: `edition` (release used), `accessed` (download date), and where noted the exact table (`title`, `access_url`). For the KG: `kg.doi` once Zenodo mints it. Re-run the script; citations regenerate.
