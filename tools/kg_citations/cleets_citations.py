"""cleets_citations.py: resolve citations for CLEETS-CHAT results.

Drop this next to the CLEETSKG access layer. Every subject that actual_search() can
return is mapped to one or more references through the citation layer added by
enrich_citations.py:

    subject --dcterms:source------> dcat:Dataset  --dcterms:bibliographicCitation--> reference
    subject --prov:wasGeneratedBy-> prov:Activity  (derived indicator: cite the KG plus the method)
    subject --rdfs:isDefinedBy----> owl:Ontology   (definitional answers: cite the ontology)
    dataset record itself --------> its own reference
    anything else in the graph ---> the KG's own reference (fallback)

Typical use:

    resolver = CitationResolver(kg.base_graph())
    rows, references = resolver.annotate(kg.actual_search("Cardiff chargers 2024"))
    print(resolver.format_references(references))

Each row gains a "refs" field ("[1, 3]") and `references` is the numbered reference list
for the answer footer. No LLM is involved; the references are read from the graph.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from functools import lru_cache
from typing import Any, Iterable

from rdflib import Graph, URIRef
from rdflib.namespace import DCAT, DCTERMS, OWL, PROV, RDF, RDFS

KG_IRI = URIRef("https://w3id.org/def/cleets/data")
ONT_IRI = URIRef("https://w3id.org/def/cleets")
ONT_NS = "https://w3id.org/def/cleets#"


@dataclass(frozen=True)
class Reference:
    iri: str
    kind: str                 # dataset | derivation | ontology | knowledge-graph
    key: str                  # short in-text key, e.g. VEH0132
    citation: str             # rendered Harvard string from the graph
    title: str = ""
    publisher: str = ""
    url: str = ""
    licence: str = ""
    note: str = ""            # derivation formula / verification statement, when relevant

    def as_dict(self) -> dict[str, str]:
        return {k: str(v) for k, v in self.__dict__.items()}


class CitationResolver:
    def __init__(self, graph: Graph):
        self.g = graph
        self._datasets: dict[str, Reference] = {}
        for ds in set(graph.subjects(RDF.type, DCAT.Dataset)):
            self._datasets[str(ds)] = self._dataset_reference(ds)
        self.kg_reference = self._datasets.get(str(KG_IRI)) or self._dataset_reference(KG_IRI, kind="knowledge-graph")
        self.kg_reference = Reference(**{**self.kg_reference.__dict__, "kind": "knowledge-graph", "key": "CLEETS-KG"})
        self.ontology_reference = Reference(
            iri=str(ONT_IRI), kind="ontology", key="CLEETS ontology",
            citation=self._str(ONT_IRI, DCTERMS.bibliographicCitation),
            title=self._str(ONT_IRI, DCTERMS.title), url=str(ONT_IRI),
            licence=self._str(ONT_IRI, DCTERMS.license),
        )

    # ------------------------------------------------------------------ helpers
    def _str(self, s, p) -> str:
        v = self.g.value(s, p)
        return str(v) if v is not None else ""

    def _dataset_reference(self, ds: URIRef, kind: str = "dataset") -> Reference:
        url = self._str(ds, DCAT.landingPage)
        for dist in self.g.objects(ds, DCAT.distribution):
            access = self._str(dist, DCAT.accessURL)
            if access:
                url = access
        return Reference(
            iri=str(ds), kind=kind,
            key=self._str(ds, DCTERMS.identifier) or self._str(ds, RDFS.label) or str(ds).rsplit("/", 1)[-1],
            citation=self._str(ds, DCTERMS.bibliographicCitation) or self._str(ds, DCTERMS.title),
            title=self._str(ds, DCTERMS.title), publisher=self._str(ds, DCTERMS.publisher),
            url=url, licence=self._str(ds, DCTERMS.license),
        )

    def _derivation_reference(self, act: URIRef) -> Reference:
        base = self.kg_reference
        return Reference(**{**base.__dict__, "kind": "derivation",
                            "note": f"{self._str(act, RDFS.label)}: {self._str(act, RDFS.comment)}"})

    # ------------------------------------------------------------------ public API
    @lru_cache(maxsize=4096)
    def cite(self, subject: str) -> tuple[Reference, ...]:
        """Ordered, de-duplicated references for one subject IRI."""
        s = URIRef(subject)
        refs: list[Reference] = []

        if subject in self._datasets:
            refs.append(self._datasets[subject])
        for src in self.g.objects(s, DCTERMS.source):
            if str(src) in self._datasets:
                refs.append(self._datasets[str(src)])
        for act in self.g.objects(s, PROV.wasGeneratedBy):
            if (act, RDFS.comment, None) in self.g and (act, PROV.used, None) in self.g:
                refs.append(self._derivation_reference(act))
        for defined_by in self.g.objects(s, RDFS.isDefinedBy):
            if defined_by == ONT_IRI:
                refs.append(self.ontology_reference)
            elif defined_by == KG_IRI:
                refs.append(self.kg_reference)
        if not refs and (subject.startswith(ONT_NS) or subject == str(ONT_IRI)):
            refs.append(self.ontology_reference)
        if not refs:
            refs.append(self.kg_reference)

        seen, out = set(), []
        for r in refs:
            k = (r.iri, r.kind, r.note)
            if k not in seen:
                seen.add(k); out.append(r)
        return tuple(out)

    def annotate(self, rows: Iterable[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        """Add a 'refs' field to each result row and return the numbered reference list."""
        numbering: dict[tuple[str, str, str], int] = {}
        references: list[dict[str, Any]] = []
        annotated: list[dict[str, Any]] = []
        for row in rows:
            nums = []
            for ref in self.cite(str(row["subject"])):
                k = (ref.iri, ref.kind, ref.note)
                if k not in numbering:
                    numbering[k] = len(numbering) + 1
                    references.append({"n": numbering[k], **ref.as_dict()})
                nums.append(numbering[k])
            annotated.append({**row, "refs": str(nums)})
        return annotated, references

    @staticmethod
    def format_references(references: list[dict[str, Any]]) -> str:
        lines = []
        for r in references:
            line = f"[{r['n']}] {r['citation']}"
            if r.get("note"):
                line += f"\n    Method: {r['note']}"
            lines.append(line)
        return "\n".join(lines)


def cited_search(kg, resolver: CitationResolver, query: str, limit: int = 40) -> dict[str, Any]:
    """Convenience wrapper around CLEETSKG.actual_search()."""
    rows, references = resolver.annotate(kg.actual_search(query, limit))
    return {"query": query, "rows": rows, "references": references,
            "reference_text": resolver.format_references(references)}


if __name__ == "__main__":  # smoke test: python cleets_citations.py cleets_kg_v1301_cited.ttl
    import sys
    g = Graph(); g.parse(sys.argv[1], format="turtle")
    r = CitationResolver(g)
    for subj in [
        "https://w3id.org/def/cleets/data#EVChargerCount_W06000015_2024Q4",
        "https://w3id.org/def/cleets/data#ChargersPer100kResidents_W06000015_2024Q4",
        "https://w3id.org/def/cleets/data#KeepersPerCharger_W06000015_2024Q4",
        "https://w3id.org/def/cleets/data#IncomeDeprivation_W06000015_2025",
        "https://w3id.org/def/cleets/data#PopulationDensity_E09000001_2022",
        "https://w3id.org/def/cleets/data#W06000015",
        "https://w3id.org/def/cleets#KeeperChargerRatioProperty",
        "https://w3id.org/def/cleets/data#Period2024Q4",
        "https://w3id.org/def/cleets/data#dataset/WIMD2025",
    ]:
        print(subj)
        for ref in r.cite(subj):
            print(f"   [{ref.kind}] {ref.key}: {ref.citation[:110]}...")
