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
    assert {f["key"] for f in kg.prediction_families()} >= {"diffusion", "hierarchical", "turnover", "neural", "charging", "covariates"}
    assert kg.observation_years() == (2009, 2026)


def test_every_help_question_answers(kg, question_groups):
    for mode, groups in question_groups.items():
        for heading, questions in groups.items():
            for q in questions:
                r = qa.answer_question_rich(kg, q, mode=mode)
                assert r["markdown"].strip(), (mode, q)
                assert not r["markdown"].startswith("### Query error"), (mode, q, r["markdown"][:200])
                assert not r["markdown"].startswith(("I could not", "### Not found", "### Not modelled")), (mode, q)
                assert r["kind"] not in ("scope", "meta"), (mode, q, r["markdown"][:200])


def test_prediction_answers_cite_sources_and_type(kg):
    md = qa.answer_question(kg, "How many private battery-electric cars are predicted for Cardiff in 2045 under the central scenario?", mode="prediction")
    assert "121,443" in md and "26,372" in md and "**Sources:**" in md and "Prediction type:" in md
    assert all(t in md for t in ("VEH0105", "VEH0142", "VEH9901", "VEH1111"))


def test_quarter_and_cars_remaining_answers(kg):
    """Every district and quarter of the capped predictions is retrievable, with the petrol and diesel cars that remain."""
    r = kg.prediction_quarter(2045, 4, "central", "Cardiff")
    assert r["keepership"] == 121443 and r["non_bev_stock"] == 26372 and r["private_stock"] == 147815 and r["on_path"] is True
    assert round(r["path_share"], 4) == 0.8216 and r["fitted_share"] > r["path_share"]
    r = kg.prediction_quarter(2030, 4, "central", "Cardiff")           # the value compared with the Cardiff road map in the paper
    assert r["keepership"] == 18768 and round(r["adoption_share"], 3) == 0.127
    w = kg.area_prediction_quarter(2045, 4, "central")
    assert abs(w["keepership"] - 1274581) <= 5 and abs(w["non_bev_stock"] - 296246) <= 5 and round(w["adoption_share"], 4) == 0.8114
    assert round(kg.area_prediction_quarter(2045, 4, "low")["adoption_share"], 4) == 0.7532
    assert round(kg.area_prediction_quarter(2045, 4, "high")["adoption_share"], 4) == 0.8835
    table = kg.prediction_table("central")
    assert len(table) == 22 * 80 and all(r["non_bev_stock"] is not None for r in table)
    assert all(abs(r["keepership"] + r["non_bev_stock"] - r["private_stock"]) <= 1 for r in table)
    assert all(r["adoption_share"] <= min(r["fitted_share"], r["path_share"]) + 1e-6 for r in table)
    assert sum(1 for r in table if r["on_path"]) == 1621               # district-quarters in which the path is the lower of the two
    assert {m["period"] for m in kg.milestones("Bridgend", "central") if m["family"] == "diffusion" and m["threshold_share"] == 0.5} == {"2037-Q1"}
    assert {m["period"] for m in kg.milestones("Ceredigion", "central") if m["family"] == "diffusion" and m["threshold_share"] == 0.5} == {"2040-Q1"}
    assert qa.extract_quarter("Cardiff in 2031 Q2") == qa.extract_quarter("Q2 2031") == qa.extract_quarter("second quarter of 2031") == (2031, 2)
    md = qa.answer_question(kg, "How many private battery-electric cars are predicted for Cardiff in 2031 Q2?", mode="prediction")
    assert "21,862" in md and "125,953" in md and "turnover path" in md and "**Sources:**" in md
    md = qa.answer_question(kg, "How many petrol and diesel cars remain in Wales in 2040 Q4?", mode="prediction")
    assert md.startswith("### Wales: 2040 Q4") and "petrol and diesel cars remaining" in md
    full = qa.answer_question_rich(kg, "Give me a table of the quarterly predictions and cars remaining for all districts.", mode="prediction")
    assert full["kind"] == "table" and len(full["table"]) == 23 * 80 and "Petrol and diesel cars remaining" in full["table"][0]
    one = qa.answer_question_rich(kg, "Give me a table of all districts in 2035 Q1 with the cars remaining.", mode="prediction")
    assert one["kind"] == "table" and len(one["table"]) == 23
    assert qa.detect_family("How many petrol and diesel cars remain in Powys in 2038 Q3?") == "diffusion"
    assert qa.detect_family("How many petrol and diesel cars remain in Cardiff at 2053 on the turnover path?") == "turnover"


def test_turnover_path_family(kg):
    """District inputs and results of the turnover path, and the Wales path by scrappage period, as in the paper."""
    rows = {r["lad_name"]: r for r in kg.turnover_rows()}
    assert len(rows) == 22
    assert rows["Bridgend"]["arrival_rank"] == 1 and rows["Bridgend"]["reaches_0.5"] == "2037-Q1" and round(rows["Bridgend"]["bev_share_2045"], 4) == 0.8615
    assert rows["Ceredigion"]["arrival_rank"] == 22 and rows["Ceredigion"]["reaches_0.5"] == "2040-Q1" and round(rows["Ceredigion"]["bev_share_2045"], 4) == 0.7441
    assert rows["Cardiff"]["private_cars"] == 147815 and rows["Cardiff"]["bev_cars_start"] == 3972 and rows["Cardiff"]["residual_non_bev"] == 26372
    assert round(rows["Blaenau Gwent"]["first_year_entry_share"], 3) == 0.227 and round(rows["Ceredigion"]["mean_age_years"], 1) == 12.0
    assert sum(1 for r in rows.values() if "reaches_0.9" not in r) == 2            # two districts are below 90% at 2053 Q4
    paths = {c["scrappage_period"]: c for c in kg.turnover_ceilings() if c["model"] == "turnover path"}
    assert round(paths["2021 to 2025"]["bev_share_2045"], 4) == 0.8114 and paths["2021 to 2025"]["residual_non_bev"] == 296246
    assert round(paths["2014 to 2019"]["bev_share_2045"], 4) == 0.8835
    weibull = {c["median_scrappage_years"]: c for c in kg.turnover_ceilings() if c["model"] == "Weibull ceiling"}
    assert round(weibull[14.0]["bev_share_2045"], 4) == 0.9619
    md = qa.answer_question(kg, "What is the turnover path for Ceredigion?", mode="prediction")
    assert "74.4%" in md and "2040 Q1" in md and "A path, not a ceiling" in md and "VEH9901" in md
    md = qa.answer_question(kg, "What is the Wales turnover path at 2045 under different scrappage rates?", mode="prediction")
    assert "81.14%" in md and "88.35%" in md and "96.19%" in md


def test_family_routing(kg):
    assert qa.detect_family("What is the turnover path for Powys?") == "turnover"
    assert qa.detect_family("How old are the private cars in Blaenau Gwent?") == "turnover"
    assert qa.detect_family("Which LADs diffuse most slowly?") == "hierarchical"
    assert qa.detect_family("Where may charging provision be the principal constraint?") == "charging"
    assert qa.detect_family("How well does the turnover-constrained neural network perform?") == "neural"
    assert qa.detect_family("How does income deprivation relate to EV adoption?") == "covariates"
    assert qa.detect_family("Compare Cardiff across all three scenarios in 2045.") == "diffusion"
    assert qa.detect_family("When does Bridgend reach 50%?") == "diffusion"       # 'ridge' in Bridgend is not the Ridge model


def test_dataset_table_and_sources(kg):
    cols = ["bev_cars", "keepership", "chargers", "deprivation", "population", "density", "pred_keepership_central", "turnover_reaches_50", "car_age"]
    rows = kg.dataset_table(cols)
    assert len(rows) == 22 and rows[0]["LAD"] == "Blaenau Gwent"
    cardiff = next(r for r in rows if r["LAD"] == "Cardiff")
    assert cardiff["Private battery-electric cars (latest)"] == 3972 and cardiff["Private battery-electric cars (latest) period"] == "2026-Q2"
    assert cardiff["Private BEV keepership, all body types (latest)"] == 3214
    assert cardiff["Turnover path: first quarter at 50% battery-electric share"] == "2038-Q2"
    assert cardiff["Predicted private battery-electric cars, central scenario (2045-Q4)"] == 121443
    assert {s["label"] for s in kg.dataset_sources(cols)} >= {"VEH0142", "VEH0132", "VEH0105", "VEH9901", "VEH1111", "EVCI9001", "WIMD2025LocalAuthority"}
    # Income deprivation is the published local authority percentage; the mean LSOA decile stays available by name.
    assert cardiff["People in income deprivation (%), WIMD 2025"] == 25.8 and rows[0]["People in income deprivation (%), WIMD 2025"] == 33.7
    both = kg.dataset_table(["deprivation", "deprivation_decile"])
    merthyr = next(r for r in both if r["LAD"] == "Merthyr Tydfil")
    assert merthyr["People in income deprivation (%), WIMD 2025"] == 30.5 and merthyr["Income deprivation, mean WIMD 2025 decile of LSOAs"] == 4.36
    assert {s["label"] for s in kg.dataset_sources(["deprivation_decile"])} >= {"WIMD2025"}
    r = qa.answer_question_rich(kg, "Give me a table of battery-electric cars, chargers, deprivation, population and density for Cardiff and Swansea", mode="actual")
    assert r["kind"] == "table" and len(r["table"]) == 2 and r["table"][0]["Private battery-electric cars (latest)"] == 3972
    # the car series are observed measures in their own right
    assert kg.latest_observation("Cardiff", "car_stock")["value"] == 146700 and kg.latest_observation("Cardiff", "car_stock")["period"] == "2025-Q4"
    assert len(kg.observations("Cardiff", "bev_cars")) == 67 and len(kg.observations("Cardiff", "car_stock")) == 65
    md = qa.answer_question(kg, "How many private battery-electric cars does Cardiff have?", mode="actual")
    assert "3,972" in md and "VEH0142" in md


def test_methods_panels_have_no_unfilled_placeholders(kg):
    for fam in ("diffusion", "hierarchical", "turnover", "charging", "neural", "covariates"):
        text = qa.methods_text(kg, fam)
        assert len(text) > 500, fam
        assert not re.findall(r"\{\w+\}", text), fam


def test_model_ranking_matches_the_paper(kg):
    """The paper's model comparison: one-step-ahead MAE in cars, and the multi-horizon rows behind the choice of the logistic."""
    ranking = kg.model_ranking()
    assert set(ranking) == {"Private battery-electric cars"}
    cars = [(r["model"], r["mae"]) for r in ranking["Private battery-electric cars"]]
    assert cars[:3] == [("Persistence + drift", 17.62), ("Turnover-constrained neural network", 18.89), ("Turnover-constrained graph neural network", 28.05)]
    assert cars[3][1] == 28.51 and cars[4][1] == 260.41
    assert all(r["n"] == 352 and r["pooled_r2"] is not None for rows in ranking.values() for r in rows)
    horizons = {(r["model"], int(r["horizon"])): r["mae"] for r in kg.horizon_metrics()}
    assert len(horizons) == 25 and horizons[("Persistence + drift", 8)] == 190.85
    assert horizons[("Bounded logistic, full history from 2011 Q4 (the model behind the predictions)", 8)] == 169.68
    md = qa.answer_question(kg, "Which model is most accurate?", mode="prediction")
    assert "Persistence + drift" in md and "17.62" in md and "from 4 quarters ahead" in md and "**Sources:**" in md
    md = qa.answer_question(kg, "Which model is most accurate for EV chargers?", mode="prediction")
    assert "charger counts are not predicted" in md
    assert qa.wants_accuracy("What is the keepership in Maesteg?") is False


def test_every_resource_is_cited(kg):
    """Every observation, cube observation, prediction, family resource and activity reaches a complete dataset record."""
    audit = kg.citation_audit()
    assert audit["complete"], audit
    assert audit["datasets_complete"] == audit["datasets_total"] >= 13
    assert audit["resources_uncited"] == 0 and audit["resources_total"] > 25000
    cube = next(r for r in audit["resources"] if r["class"] == "qb:Observation")
    assert cube["total"] == 5170 and cube["uncited"] == 0
    assert audit["activities_uncited"] == 0 and len(audit["activities"]) == 6
    md = qa.answer_question(kg, "Are all resources properly cited?", mode="actual")
    assert md.startswith("### Are all resources cited?") and "**Yes.**" in md and "VEH9901" in md


def test_about_description(kg):
    """The About text is filled from the graphs: datasets, counts and the scalability section."""
    from about import about_content, about_markdown
    c = about_content(kg)
    assert c["facts"]["lads"] == 22 and c["facts"]["sources"] == 10 and c["facts"]["cube_observations"] == 5170
    by_id = {r["Dataset"]: r for r in c["datasets"]}
    assert set(by_id) >= {"VEH0105", "VEH0132", "VEH0142", "VEH9901", "VEH1111", "EVCI9001", "StatsWalesPopulation", "ONSDensity", "WIMD2025",
                          "WIMD2025LocalAuthority"}
    assert all(by_id[k]["Role"] == "Source dataset" and by_id[k]["Licence"] == "OGL v3.0" for k in ("VEH0142", "VEH9901", "VEH1111"))
    assert by_id["VEH0142"]["Measures supplied"] == "private battery-electric cars" and by_id["VEH0142"]["Observations"] == 1474
    assert by_id["VEH0142"]["Coverage"] == "2009-Q4 to 2026-Q2"
    assert "year of first registration" in by_id["VEH9901"]["Measures supplied"] and by_id["VEH9901"]["Observations"] == 1723
    assert by_id["VEH9901"]["Coverage"] == "2026-Q2"
    assert "year of first use" in by_id["VEH1111"]["Measures supplied"] and "Great Britain" in by_id["VEH1111"]["Measures supplied"]
    assert by_id["VEH1111"]["Observations"] == 3447 and by_id["VEH1111"]["Coverage"] == "2009-Q4 to 2025-Q4"
    assert "private cars (all fuels)" in by_id["VEH0105"]["Measures supplied"] and by_id["VEH0105"]["Observations"] == 4136
    assert "private BEV keepership" in by_id["VEH0132"]["Measures supplied"]
    md = about_markdown(kg)
    assert "ontology-based knowledge graph" in md and "Scalable to more datasets" in md and "VEH9901" in md
