"""Smoke tests: the knowledge graphs load, every example question in the help panel
answers without error, the dataset builder works and the methods panels are complete.

Run:  pytest -q
"""
import re
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

import qa  # noqa: E402
from kg_service import CLEETSKG, find_data_file  # noqa: E402


@pytest.fixture(scope="session")
def kg():
    return CLEETSKG(find_data_file("cleets_cskg_enriched.ttl"),
                    [find_data_file("cleets_prediction_kg.ttl"), find_data_file("cleets_prediction_families.ttl")])


@pytest.fixture(scope="session")
def question_groups():
    import app  # loads the graphs once more; keeps the test independent of the fixture above
    return app.QUESTION_GROUPS


def test_graphs_loaded(kg):
    assert len(kg.lad_names()) == 22
    inv = kg.prediction_inventory()
    assert inv["prediction_count"] > 5000 and inv["scenarios"] == ["central", "high", "low"]
    assert {f["key"] for f in kg.prediction_families()} >= {"diffusion", "hierarchical", "turnover", "charging", "covariates"}


def test_every_help_question_answers(kg, question_groups):
    for mode, groups in question_groups.items():
        for heading, questions in groups.items():
            for q in questions:
                r = qa.answer_question_rich(kg, q, mode=mode)
                assert r["markdown"].strip(), (mode, q)
                assert not r["markdown"].startswith("### Query error"), (mode, q, r["markdown"][:200])
                assert not r["markdown"].startswith("I could not"), (mode, q)


def test_prediction_answers_cite_sources_and_type(kg):
    md = qa.answer_question(kg, "What is Cardiff's predicted EV keepership in 2045 under the central scenario?", mode="prediction")
    assert "159,451" in md and "**Sources:**" in md and "Prediction type:" in md


def test_family_routing(kg):
    assert qa.detect_family("When does Powys reach 99% BEV share under the 2032 phase-out?") == "turnover"
    assert qa.detect_family("Which LADs diffuse most slowly?") == "hierarchical"
    assert qa.detect_family("Where may charging provision be the principal constraint?") == "charging"
    assert qa.detect_family("How well does the scenario-constrained neural network perform?") == "neural"
    assert qa.detect_family("How does income deprivation relate to EV adoption?") == "covariates"
    assert qa.detect_family("Compare Cardiff across all three scenarios in 2045.") == "diffusion"


def test_dataset_table_and_sources(kg):
    cols = ["keepership", "chargers", "deprivation", "population", "density", "pred_keepership_central", "turnover_reaches_99"]
    rows = kg.dataset_table(cols)
    assert len(rows) == 22 and rows[0]["LAD"] == "Blaenau Gwent"
    cardiff = next(r for r in rows if r["LAD"] == "Cardiff")
    assert cardiff["Private BEV keepership (latest)"] == 3214 and cardiff["Turnover: first quarter at 99% BEV share"] == "2048-Q3"
    assert {s["label"] for s in kg.dataset_sources(cols)} >= {"VEH0132", "EVCI9001", "WIMD2025"}
    r = qa.answer_question_rich(kg, "Give me a table of keepership, chargers, deprivation, population and density for Cardiff and Swansea", mode="actual")
    assert r["kind"] == "table" and len(r["table"]) == 2


def test_methods_panels_have_no_unfilled_placeholders(kg):
    for fam in ("diffusion", "hierarchical", "turnover", "charging", "neural", "covariates"):
        text = qa.methods_text(kg, fam)
        assert len(text) > 500, fam
        assert not re.findall(r"\{\w+\}", text), fam


def test_model_ranking_matches_table7(kg):
    """Table 7 of the quarterly revision: lowest one-step-ahead MAE per target, Stage 13 logistic alongside."""
    ranking = kg.model_ranking()
    assert set(ranking) == {"EV chargers", "EV keepership"}
    chargers = [(r["model"], r["mae"]) for r in ranking["EV chargers"]]
    assert chargers[:3] == [("Persistence + drift", 9.344), ("Scenario-constrained NN", 9.784), ("Bounded logistic", 12.587)]
    keep = [(r["model"], r["mae"]) for r in ranking["EV keepership"]]
    assert keep[:3] == [("Persistence + drift", 17.879), ("Bounded logistic", 25.146), ("Scenario-constrained NN", 35.988)]
    assert all(r["n"] == 352 and r["pooled_r2"] is not None for rows in ranking.values() for r in rows)
    s13 = kg.logistic_backtest("chargers")
    assert [r["scenario"] for r in s13["EV chargers"]] == ["Low", "Central", "High"]
    md = qa.answer_question(kg, "Which model is most accurate for EV chargers?", mode="prediction")
    assert "Persistence + drift" in md and "9.34" in md and "no charger forecast to 2045" in md and "**Sources:**" in md
    assert qa.wants_accuracy("What is the keepership in Maesteg?") is False


def test_every_resource_is_cited(kg):
    """Every observation, prediction, family resource and activity reaches a complete dataset record."""
    audit = kg.citation_audit()
    assert audit["complete"], audit
    assert audit["datasets_complete"] == audit["datasets_total"] >= 10
    assert audit["resources_uncited"] == 0 and audit["resources_total"] > 16000
    assert audit["activities_uncited"] == 0 and len(audit["activities"]) == 6
    md = qa.answer_question(kg, "Are all resources properly cited?", mode="actual")
    assert md.startswith("### Are all resources cited?") and "**Yes.**" in md


def test_about_description(kg):
    """The About text is filled from the graphs: datasets, counts and the scalability section."""
    from about import about_content, about_markdown
    c = about_content(kg)
    assert c["facts"]["lads"] == 22 and c["facts"]["sources"] >= 6
    assert {r["Dataset"] for r in c["datasets"]} >= {"VEH0132", "VEH0105", "EVCI9001", "StatsWalesPopulation", "ONSDensity", "WIMD2025"}
    veh = next(r for r in c["datasets"] if r["Dataset"] == "VEH0132")
    assert "private BEV keepership" in veh["Measures supplied"] and veh["Licence"] == "OGL v3.0"
    md = about_markdown(kg)
    assert "ontology-based knowledge graph" in md and "Scalable to more datasets" in md
