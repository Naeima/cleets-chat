"""
about.py: the "About CLEETS-CHAT" description shown under the header of the
dashboard and of the GitHub Pages site (and reproduced in the README).

The wording is fixed here; every figure and the dataset table are read from the
loaded knowledge graphs at run time (kg_service.dataset_catalogue,
observation_years, actual_inventory, prediction_inventory), so the description
stays correct when a dataset or a prediction type is added.
"""

from __future__ import annotations

ONTOLOGY_URL = "https://w3id.org/def/cleets"
PAPER_TITLE = "Predicting EV adoption in Wales using Semantic Knowledge Graph"

ROLE_LABELS = {
    "source": "Source dataset",
    "reference": "Reference (geography)",
    "graph": "Knowledge graph release",
    "prediction": "Prediction outputs",
}


def _licence(url: str) -> str:
    u = (url or "").lower()
    if "open-government-licence" in u:
        return "OGL v3.0"
    if "creativecommons.org/licenses/by/4.0" in u:
        return "CC BY 4.0"
    return url or ""


def about_content(kg) -> dict:
    """{'lead', 'sections': [(title, text)], 'datasets': [rows], 'facts': {...}}"""
    inv = kg.actual_inventory()
    pred = kg.prediction_inventory()
    fams = kg.prediction_families() if hasattr(kg, "prediction_families") else []
    y0, y1 = kg.observation_years() if hasattr(kg, "observation_years") else (None, None)
    cat = kg.dataset_catalogue() if hasattr(kg, "dataset_catalogue") else []
    sources = [d for d in cat if d["role"] == "source"]
    n_obs = sum(len(kg.observations(n)) for n in kg.lad_names())
    measures = inv.get("measures", [])
    years = f"{y0} to {y1}" if y0 and y1 else "the observed period"
    horizon = pred.get("years", (None, None))

    facts = {
        "lads": len(kg.lad_names()), "observations": n_obs, "measures": len(measures),
        "observed_triples": inv["triples"], "sources": len(sources), "forecasts": pred["prediction_count"],
        "families": len(fams), "years": years, "horizon": horizon,
    }

    lead = (
        "CLEETS-CHAT is a question-answering assistant for electric-vehicle (EV) adoption in Wales. It answers free-text "
        "questions from two knowledge graphs rather than from a language model's memory: the observed graph CLEETS-KG-Enriched "
        f"({facts['observations']:,} observations of {facts['measures']} measures for the {facts['lads']} Welsh local authority "
        f"districts, {years}) and the CLEETS Prediction KG ({facts['forecasts']:,} quarterly scenario forecasts to "
        f"{horizon[1] if horizon and horizon[1] else 2045} and the {facts['families']} prediction types of the companion paper). "
        "Every answer is assembled from retrieved statements or from calculations the system performs on them, names the dataset "
        "behind each value, states whether a value is observed, calculated or predicted, and explains how each prediction was "
        "generated. Stakeholders can extract custom district tables, plot them on the map, download them as CSV and score every answer."
    )

    graph = (
        f"Both graphs conform to the CLEETS ontology (OWL 2 DL, published at {ONTOLOGY_URL}), which defines the districts, measures, "
        "time periods, observations and predictions and reuses DCAT and PROV for dataset records and provenance. Each observation "
        "links to its dataset record with dcterms:source; each record carries a bibliographic citation, publisher, licence and landing "
        "page; each prediction links to the prov:Activity that generated it and to the datasets that activity used. The release "
        "bundles SHACL shapes for validation. Because the assistant reads only the graph, it cannot state a value the graph does not hold, "
        "and the citation audit (ask \"Are all resources properly cited?\") checks that every resource reaches a complete dataset record."
    )

    datasets_intro = (
        f"The observed graph currently integrates {facts['sources']} open datasets under the Open Government Licence, all at "
        "local-authority level, listed below with the measures each one supplies (read from the dataset records in the graph)."
    )

    scale = (
        "The design is built to grow. A new dataset is added by describing it once as a dcat:Dataset record and loading its values "
        "as observations typed with the ontology (the enrichment scripts in tools/kg_citations do this from a source manifest); the "
        "assistant indexes every observation it finds, so the new values become answerable and cited immediately, and adding them to "
        "the dataset builder and the map is one line in the column catalogue. New prediction types are added in the same way as "
        "prov:Activity nodes with their outputs (build_prediction_families.py), and further regions only need their district nodes. "
        "The graphs are plain Turtle files, so the same content serves the desktop dashboard, the browser build on GitHub Pages and "
        "any SPARQL tool."
    )

    paper = (f"Companion paper: {PAPER_TITLE} (CLEETS, Cardiff University, 2026). Data set: CLEETS-KG v1.3.0 "
             f"(CC BY 4.0), knowledge graph and ontology at {ONTOLOGY_URL}.")

    rows = []
    for d in cat:
        ident = d["identifier"]
        if ident.startswith("http"):  # the graph's own record is identified by its URI; show the short title instead
            ident = d["title"].split(":")[0].strip() or ident
        coverage = ""
        if d.get("first") and d.get("last"):
            coverage = d["first"] if d["first"] == d["last"] else f"{d['first']} to {d['last']}"
        rows.append({
            "Dataset": ident, "Title": d["title"], "Publisher": d["publisher"], "Licence": _licence(d["license"]),
            "Role": ROLE_LABELS.get(d["role"], d["role"]),
            "Measures supplied": ", ".join(d["measures"]) if d["measures"] else "",
            "Observations": d["observations"] or "",
            "Coverage": coverage,
            # the knowledge-graph release links to the CLEETS ontology, which defines it
            "Landing page": ONTOLOGY_URL if d["role"] == "graph" else d["landing_page"],
        })

    return {
        "lead": lead,
        "sections": [
            ("Built on an ontology-based knowledge graph", graph),
            ("Datasets in the current graphs", datasets_intro),
            ("Scalable to more datasets", scale),
            ("References", paper),
        ],
        "datasets": rows,
        "facts": facts,
    }


def about_markdown(kg) -> str:
    """Markdown version (used for the README and by the site build)."""
    c = about_content(kg)
    out = ["## About CLEETS-CHAT", "", c["lead"], ""]
    for title, text in c["sections"]:
        out += [f"### {title}", "", text, ""]
        if title.startswith("Datasets"):
            cols = ["Dataset", "Publisher", "Licence", "Role", "Measures supplied", "Coverage"]
            out.append("| " + " | ".join(cols) + " |")
            out.append("|" + "|".join("---" for _ in cols) + "|")
            for r in c["datasets"]:
                cells = [str(r[k]) for k in cols]
                if r["Landing page"]:
                    cells[0] = f"[{cells[0]}]({r['Landing page']})"
                out.append("| " + " | ".join(cells) + " |")
            out.append("")
    return "\n".join(out).strip()
