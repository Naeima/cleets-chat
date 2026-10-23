"""Scope check: a question outside the knowledge graphs gets a 'not modelled' answer with a short reason,
in both modes and in the browser snapshot, while every in-scope wording still reaches the answerers.

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
from scope import check_scope, stem, tokens, vocabulary  # noqa: E402


@pytest.fixture(scope="module")
def kg():
    return CLEETSKG(find_data_file("cleets_cskg_enriched.ttl"),
                    [find_data_file("cleets_prediction_kg.ttl"), find_data_file("cleets_prediction_families.ttl")])


@pytest.fixture(scope="module")
def snap(kg):
    return CLEETSKG.from_snapshot(json.dumps(kg.to_snapshot()))


# (question, mode, expected verdict, a phrase the reason must contain)
OUT_OF_SCOPE = [
    ("What is the capital of France?", "prediction", "geography", "outside the modelled geography"),
    ("Who is the prime minister?", "prediction", "topic", "political roles"),
    ("Who won the World Cup?", "actual", "unmodelled", "Nothing in the question corresponds to a district, measure"),
    ("Write me a poem about Wales", "actual", "partial", "no observation, prediction or dataset describes"),
    ("What is the weather in Cardiff?", "actual", "topic", "Weather, climate and flood"),
    ("When will it rain in Cardiff?", "prediction", "topic", "Weather, climate and flood"),
    ("How much does an EV charger cost in Swansea?", "actual", "topic", "prices, costs, incentives"),
    ("How many electric buses does Cardiff have?", "actual", "topic", "privately kept road vehicles"),
    ("What are the CO2 emissions of EVs in Cardiff?", "prediction", "topic", "Emissions, air quality"),
    ("How many petrol cars are in Cardiff?", "actual", "topic", "petrol, diesel, hybrid"),
    ("Where is the nearest charger to Cardiff Central station?", "actual", "topic", "finest geography"),
    ("How far is Cardiff from Swansea?", "actual", "topic", "Distances, journeys"),
    ("What is the unemployment rate in Powys?", "actual", "topic", "labour-market"),
    ("Which EV should I buy?", "prediction", "topic", "makes, models and sales"),
    ("How much will Cardiff's EV grid demand be in 2045?", "prediction", "topic", "grid capacity"),
    ("What is Cardiff's predicted EV keepership in 2060?", "prediction", "temporal", "beyond the prediction horizon"),
    ("What was Cardiff's population in 1950?", "actual", "temporal", "predates the graphs"),
    ("What was Cardiff's keepership in 2030?", "actual", "temporal", "switch to Prediction mode"),
    ("How many EVs are there in London?", "actual", "geography", "outside the modelled geography"),
    ("How many EVs are there in England?", "prediction", "geography", "296 English districts"),
    ("How many EVs are in Birmingham?", "actual", "geography", "population density"),
    ("Compare Cardiff and Bristol.", "actual", "geography", "Bristol"),
    ("Tell me about Reading", "actual", "geography", "English local authority district"),
    ("Give me a table of dog ownership by LAD", "actual", "partial", "nearest measure held is private BEV keepership"),
    ("What is the capital of Wales?", "actual", "partial", "Wales is in the graph"),
]

IN_SCOPE = [
    ("How many people live in Cardiff?", "actual"),
    ("Which council has the fewest chargers?", "actual"),
    ("Is Powys rural?", "actual"),
    ("What's the trend in Cardiff?", "actual"),
    ("Tell me about Gwynedd", "actual"),
    ("Does Newport have enough chargers?", "actual"),
    ("Which LAD will electrify first?", "prediction"),
    ("What share of cars in Cardiff are electric?", "actual"),
    ("When will Wales hit 50% EV share?", "prediction"),
    ("Which areas lag behind?", "prediction"),
    ("Is EV adoption fair across Wales?", "actual"),
    ("What is the keeper to charger ratio in Torfaen?", "actual"),
    ("Give me the data for Monmouthshire", "actual"),
    ("Why is Cardiff ahead?", "prediction"),
    ("How accurate are the forecasts?", "prediction"),
    ("What drives EV adoption in Wales?", "prediction"),
    ("Which organisation produced the datasets?", "actual"),
    ("Cardiff", "actual"),
    ("chargers", "actual"),
    ("How many public chargers does Newport have?", "actual"),
    ("Reading the hierarchical table, which LAD is slowest?", "prediction"),
    ("How many non-BEV vehicles remain in Cardiff at 2053 under the turnover scenario?", "prediction"),
    ("Extract a table of predicted 2045 keepership, turnover arrival quarter and charging-constraint class for all LADs.", "actual"),
    ("What was the population density of Cardiff in 2011?", "actual"),
    ("Where did this number come from?", "actual"),
    ("Which prediction types are loaded?", "prediction"),
    ("Is this observed, calculated or predicted?", "prediction"),
    ("Which model is most accurate for EV chargers?", "prediction"),
]


def test_stemming_matches_morphological_variants():
    assert stem("chargers") == stem("charging") == stem("charger")
    assert stem("slowest") == stem("slowly") == stem("slow")
    assert stem("predictions") == stem("predicted") == stem("predict")
    assert stem("populations") == stem("population")
    assert stem("2045") == "2045" and tokens("Cardiff's EV keepership (2045)") == ["cardiff", "ev", "keepership", "2045"]


def test_vocabulary_is_read_from_the_graphs(kg):
    v = vocabulary(kg)
    tag = {w: c for w, c, _ in v.tag(tokens("Powys W06000023 keepership VEH0132 Welsh local authority district population density"))}
    assert tag["powys"] == "place" and tag["w06000023"] == "place"
    assert tag["keepership"] == "measure" and tag["population density"] == "measure"
    assert tag["veh0132"] == "provenance" and tag["welsh local authority district"] in ("provenance", "place")


@pytest.mark.parametrize("question,mode,verdict,phrase", OUT_OF_SCOPE)
def test_questions_outside_the_graphs_are_declined_with_a_reason(kg, question, mode, verdict, phrase):
    r = qa.answer_question_rich(kg, question, mode=mode)
    assert r["kind"] == "scope" and r["scope"]["verdict"] == verdict, (question, r["markdown"][:300])
    md = r["markdown"]
    assert md.startswith("### Not modelled in the knowledge graph"), question
    assert phrase in md, (question, md[:400])
    assert "Answers are composed only from these statements" in md and "**Knowledge graph:**" in md
    assert r["family"] is None and r["table"] is None


@pytest.mark.parametrize("question,mode", IN_SCOPE)
def test_in_scope_wordings_still_reach_the_answerers(kg, question, mode):
    assert check_scope(kg, question, mode) is None, question
    r = qa.answer_question_rich(kg, question, mode=mode)
    assert r["kind"] not in ("scope", "meta"), (question, r["markdown"][:200])


def test_every_help_question_is_in_scope(kg):
    import app
    for mode, groups in app.QUESTION_GROUPS.items():
        for questions in groups.values():
            for q in questions:
                assert check_scope(kg, q, mode) is None, (mode, q)


def test_greetings_and_meta_questions_get_a_description_not_a_retrieval(kg):
    for q in ("hello", "Hi!", "thanks", "What can you do?", "how does this work?"):
        r = qa.answer_question_rich(kg, q, mode="prediction")
        assert r["kind"] == "meta" and "no conversational model" in r["markdown"], q
        assert "Wales prediction summary" not in r["markdown"]


def test_kg_description_is_answered_in_prediction_mode_too(kg):
    md = qa.answer_question(kg, "What is the CLEETS knowledge graph?", mode="prediction")
    assert md.startswith("### CLEETS knowledge graph")
    md = qa.answer_question(kg, "What classes and properties are defined in CLEETS?", mode="prediction")
    assert "definition" in md and "Wales prediction summary" not in md


def test_before_and_after_examples(kg):
    """The questions that previously produced an unrelated answer now get the scope message."""
    for q, mode in (("What is the capital of France?", "prediction"), ("hello", "prediction"),
                    ("What is the weather in Cardiff?", "actual"), ("When will it rain in Cardiff?", "prediction")):
        md = qa.answer_question(kg, q, mode=mode)
        assert "Wales prediction summary" not in md and "Retrieved KG evidence" not in md and "milestones" not in md, (q, md[:200])


def test_other_areas_are_read_from_the_graph_and_survive_the_snapshot(kg, snap):
    areas = kg.other_areas()
    assert len(areas) == 296 and areas["Birmingham"]["measures"] == ["population density (persons per sq km)"]
    assert areas["Bristol, City of"]["aliases"] == ["Bristol"]
    assert snap.other_areas() == areas
    assert [n for n, _ in kg.find_other_areas_in_text("Compare Cardiff with Bristol and Manchester")] == ["Bristol, City of", "Manchester"]
    assert kg.find_other_areas_in_text("Reading the table for Newport") == []
    assert kg.find_other_areas_in_text("Tell me about Reading")[0][0] == "Reading"


def test_scope_answers_identical_in_the_browser_snapshot(kg, snap):
    for q, mode, _, _ in OUT_OF_SCOPE:
        assert qa.answer_question(kg, q, mode=mode) == qa.answer_question(snap, q, mode=mode), q
    for q, mode in IN_SCOPE:
        assert check_scope(snap, q, mode) is None, q
