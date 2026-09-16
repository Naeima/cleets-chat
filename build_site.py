#!/usr/bin/env python3
"""
build_site.py: build the static GitHub Pages version of CLEETS-CHAT into docs/.

GitHub Pages serves static files only, so the Dash server cannot run there.
Instead the same Python question-answering code (kg_service.py, qa.py, methods.py)
runs *in the browser* through Pyodide, against a JSON snapshot of the knowledge
graph indexes exported here. Answers are therefore identical to the Dash app's
(the snapshot round-trip is checked by tests/test_snapshot.py); only the optional
Claude humanisation and the server-side feedback database are absent.

    python build_site.py            # writes docs/data/kg_snapshot.json, docs/data/site_meta.json, docs/py/*.py

Then commit docs/ and enable Pages: Settings -> Pages -> Deploy from a branch -> main, /docs.
"""

from __future__ import annotations

import json
import shutil
import sys
from pathlib import Path

HERE = Path(__file__).parent
DOCS = HERE / "docs"


def find_data(name: str) -> Path:
    for cand in (HERE / name, HERE / "data" / name):
        if cand.exists():
            return cand
    raise FileNotFoundError(name)


def main():
    sys.path.insert(0, str(HERE))
    from kg_service import CLEETSKG
    import app  # noqa: E402  (loads the graphs once; constants reused below)
    from about import about_content  # noqa: E402

    kg: CLEETSKG = app.kg
    (DOCS / "data").mkdir(parents=True, exist_ok=True)
    (DOCS / "py").mkdir(parents=True, exist_ok=True)

    # 1. knowledge-graph snapshot (all indexes, JSON only)
    snap = kg.to_snapshot()
    (DOCS / "data" / "kg_snapshot.json").write_text(json.dumps(snap, separators=(",", ":")), encoding="utf-8")

    # 2. UI metadata so the page renders before Pyodide has loaded
    metrics = {}
    for key, (label, kind, arg, unit, scale) in app.MAP_METRICS.items():
        if kind == "custom":
            continue
        vals = app.metric_values(key)
        if not vals:
            continue
        metrics[key] = {"label": label, "unit": unit, "scale": scale, "kind": kind,
                        "values": {lad: [v, p] for lad, v, p in vals}}
    fams = kg.prediction_families()
    meta = {
        "title": app.TITLE,
        "forecast_year": app.FORECAST_YEAR,
        "counts": {
            "lads": len(kg.lad_names()),
            "observed_triples": kg._counts["observed_triples"],
            "prediction_triples": kg._counts["prediction_triples"],
            "observations": sum(len(kg.observations(n)) for n in kg.lad_names()),
            "forecasts": kg.prediction_inventory()["prediction_count"],
            "families": len(fams),
            "scenarios": kg.prediction_inventory()["scenarios"],
            "years": list(kg.prediction_inventory()["years"]),
        },
        "families": [{"key": f["key"], "label": app.family_label(kg, f["key"])} for f in fams],
        "question_groups": app.QUESTION_GROUPS,
        "mode_description": app.MODE_DESCRIPTION,
        "map_metrics": metrics,
        "centroids": app.LAD_CENTROIDS,
        "lads": kg.lad_names(),
        "dataset_columns": kg.dataset_columns(),
        "default_columns": ["keepership", "chargers", "deprivation", "population", "density"],
        "about": about_content(kg),
    }
    (DOCS / "data" / "site_meta.json").write_text(json.dumps(meta, separators=(",", ":")), encoding="utf-8")

    # 3. Python modules executed by Pyodide in the browser (copies of the root modules)
    for name in ("kg_service.py", "qa_with_humanization.py", "qa.py", "methods.py", "about.py"):
        shutil.copy(HERE / name, DOCS / "py" / name)

    # 4. README: the "About CLEETS-CHAT" block between the markers is regenerated from the graphs
    readme = HERE / "README.md"
    if readme.exists():
        from about import about_markdown
        text = readme.read_text(encoding="utf-8")
        start, end = "<!-- about:start -->", "<!-- about:end -->"
        if start in text and end in text:
            head, rest = text.split(start, 1)
            _, tail = rest.split(end, 1)
            text = head + start + "\n" + about_markdown(kg) + "\n" + end + tail
            readme.write_text(text, encoding="utf-8")
            print("README.md                   About block refreshed")

    print(f"docs/data/kg_snapshot.json  {(DOCS / 'data' / 'kg_snapshot.json').stat().st_size / 1e6:.1f} MB")
    print(f"docs/data/site_meta.json    {(DOCS / 'data' / 'site_meta.json').stat().st_size / 1e3:.0f} kB")
    print("docs/py/                    kg_service.py qa_with_humanization.py qa.py methods.py about.py")
    print("Prediction types:", ", ".join(f["key"] for f in fams))


if __name__ == "__main__":
    main()
