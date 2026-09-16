# CLEETS-CHAT: prediction types and custom datasets

CLEETS-CHAT serves the prediction types of the paper *Predicting EV adoption in Wales using Semantic Knowledge Graph* side by side. Each type is a `prov:Activity` in the Prediction KG; every per-LAD resource links to its activity with `prov:wasGeneratedBy`, so the chatbot can say which model produced a number and show how it was generated (the ⓘ button under every prediction answer; wording in `methods.py`).

| Key | Prediction type | Paper | Notebook | Loaded from |
|---|---|---|---|---|
| `diffusion` | Bounded logistic diffusion scenarios (low / central / high, quarterly to 2045) | S2.3.6, S3.4.3, S3.5 | Stage 6 | `cleets_prediction_kg.ttl` |
| `hierarchical` | Hierarchical diffusion, two-stage empirical Bayes (midpoint, rate, shrinkage per LAD; covariate effects) | S2.3.6, S3.5, Table 9, Figs 4-5 | Stage 11 | `cleets_prediction_families.ttl` |
| `turnover` | Age-structured fleet turnover under a 2032 new-sales phase-out (BEV share 2045/2053, residual non-BEV stock, 95/99/99.5% arrival quarters, Table 10 ceilings) | S2.3.5, S3.6, S3.8, Table 10, Figs 6-7 | Stages 7-9 | `cleets_prediction_families.ttl` |
| `charging` | Charging-provision constraint classification for 2045 | research question 2 | Stage 8 | `cleets_prediction_families.ttl` |
| `neural` | Scenario-constrained neural / graph neural forecasts (Tables 5-7 metrics from the rolling-origin quarterly backtest, 2022 Q1-2025 Q4, 352 held-out LAD-quarters per configuration; per-LAD forecasts to 2030 Q4 only when the Stage 6e CSV export is supplied) | S2.3.2-S2.3.4, S3.4.1 | Stages 6e, 13, 14 | `cleets_prediction_families.ttl` |
| `covariates` | Cross-sectional covariate comparison (Table 8 metrics, Ridge residuals per LAD) | S3.4.2 | Stages 4a-bis, 5 | `cleets_prediction_families.ttl` |

In Prediction mode the **Prediction type** selector forces a type; **Auto** picks it from the wording of the question (turnover, scrappage, phase-out, 2053 → turnover; midpoint, slowest, diffuse → hierarchical; charging provision → charging; neural, GNN → neural; relate, covariate, density, deprivation → covariates; otherwise diffusion). Questions about accuracy (most accurate, best model, which model, backtest, MAE, RMSE, drift, persistence) are answered with the Table 7 ranking of every approach for EV chargers and/or EV keepership plus the Stage 13 bounded-logistic run; questions such as "Are all resources properly cited?" run the citation audit (every resource must reach a complete dataset record).

## Rebuilding the families file

`cleets_prediction_families.ttl` is generated from the companion notebook's outputs:

```bash
# from the executed notebook (tables printed by Stages 5, 8, 9, 11, 13, 14 and 6e)
python build_prediction_families.py --notebook notebooks/CLEETS_EV_Adoption_Wales_Quarterly.ipynb --output data/cleets_prediction_families.ttl

# from the notebook's CSV exports (adds the full quarterly series and the Stage 6e per-LAD forecasts)
python build_prediction_families.py --csv-dir cleets_out --notebook notebooks/CLEETS_EV_Adoption_Wales_Quarterly.ipynb --output data/cleets_prediction_families.ttl
```

The CSV route reads `hierarchical_diffusion_parameters.csv`, `welsh_lad_electrification_arrival.csv`, `welsh_lad_electrification_to_2053.csv`, `table10_turnover_ceiling.csv`, `table7_best_configuration.csv` and `nn_adoption_ratio_forecast_2030.csv` when present. Re-run after every notebook run; the values shown in the dashboard are those of the run you supply (the notebook's own paper parity check lists where a run differs from the manuscript). The builder also completes the citation records of the released Prediction KG (dataset identifiers and licences, the KG's own dataset record, the diffusion activity's bibliographic citation, the scenario nodes' provenance) so that `CLEETSKG.citation_audit()` finds every resource cited.

`app.py` loads `cleets_prediction_kg.ttl` plus `cleets_prediction_families.ttl` when the file exists (override with `PREDICTION_TTL=a.ttl,b.ttl` in `.env`).

## Custom datasets

Two routes to a per-LAD table, both read from the graphs:

1. **Ask the chatbot**: "Give me a table of keepership, charging count, deprivation, population and population density for the 22 LADs", "Extract predicted 2045 keepership and turnover arrival quarter for Cardiff, Swansea and Newport as CSV". Column keywords: keepership, chargers, keepers per charger, per 100k, per 1,000, vehicle stock, population, density, deprivation, predicted / scenario, midpoint, turnover / arrival / residual, charging constraint, covariate residual. A year in the question selects that observation year.
2. **Dataset builder panel**: tick columns, choose districts (clicking a district on the map adds or removes it), optional year, **Build table**.

Either way the table appears in the dataset panel with its source datasets, **Download CSV** saves it (with a `... period` column giving the vintage of every observed value), and **Plot on map** colours the map by any numeric column.
