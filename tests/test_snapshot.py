"""The GitHub Pages build (docs/) runs the same Python code in the browser against a JSON
snapshot of the graph indexes. This test checks that the snapshot round-trip gives
identical answers to the rdflib-backed service, and that the committed docs/data files
are consistent with the code.

Run:  pytest -q
"""
import json
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import qa  # noqa: E402
from kg_service import CLEETSKG, find_data_file  # noqa: E402

QUESTIONS = [
    ("prediction", "What is Cardiff's predicted EV keepership in 2045 under the central scenario?"),
    ("prediction", "Compare Cardiff across all three scenarios in 2045."),
    ("prediction", "When does Powys reach 99% BEV share under the 2032 phase-out?"),
    ("prediction", "Which LADs diffuse most slowly?"),
    ("prediction", "Where may charging provision be the principal constraint?"),
    ("prediction", "How does population density relate to EV uptake?"),
    ("prediction", "How well does the scenario-constrained neural network perform?"),
    ("prediction", "Show me the data you have"),
    ("actual", "What do you know about Cardiff?"),
    ("actual", "Which LAD has the most public EV chargers?"),
    ("actual", "Which dataset supports this answer?"),
    ("actual", "What classes and properties are defined in CLEETS?"),
    ("actual", "Give me a table of keepership, chargers, deprivation, population and density for the 22 LADs"),
]


@pytest.fixture(scope="module")
def pair():
    kg = CLEETSKG(find_data_file("cleets_cskg_enriched.ttl"),
                  [find_data_file("cleets_prediction_kg.ttl"), find_data_file("cleets_prediction_families.ttl")])
    snap = CLEETSKG.from_snapshot(json.dumps(kg.to_snapshot()))
    return kg, snap


def test_snapshot_answers_identical(pair):
    kg, snap = pair
    for mode, q in QUESTIONS:
        a = qa.answer_question(kg, q, mode=mode)
        b = qa.answer_question(snap, q, mode=mode)
        assert a == b, (mode, q)


def test_snapshot_methods_and_tables_identical(pair):
    kg, snap = pair
    for fam in ("diffusion", "hierarchical", "turnover", "charging", "neural", "covariates"):
        assert qa.methods_text(kg, fam) == qa.methods_text(snap, fam), fam
    cols = ["keepership", "chargers", "pred_keepership_central", "turnover_reaches_99", "hier_midpoint"]
    assert kg.dataset_table(cols) == snap.dataset_table(cols)
    assert kg.dataset_sources(cols) == snap.dataset_sources(cols)
    assert kg.dataset_catalogue() == snap.dataset_catalogue()


def test_committed_site_snapshot_is_current(pair):
    """docs/data/kg_snapshot.json must be rebuilt (python build_site.py) whenever the graphs change."""
    kg, _ = pair
    path = ROOT / "docs" / "data" / "kg_snapshot.json"
    if not path.exists():
        pytest.skip("docs/data/kg_snapshot.json not built")
    committed = json.loads(path.read_text(encoding="utf-8"))
    fresh = kg.to_snapshot()
    assert committed["counts"] == fresh["counts"]
    assert committed["lads"] == fresh["lads"]
    assert len(committed["pred"]) == len(fresh["pred"]) and len(committed["obs_by_lad"]) == len(fresh["obs_by_lad"])
    assert sorted(committed["families"]) == sorted(fresh["families"])
