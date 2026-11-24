# CLEETS-CHAT: prediction types and custom datasets

CLEETS-CHAT serves the prediction types of the paper *Predicting electric vehicle adoption in Wales from open data integrated in semantic knowledge graphs* side by side, with two analyses of an earlier (September 2026) notebook. Each type is a `prov:Activity` in the Prediction KG; every per-LAD resource links to its activity with `prov:wasGeneratedBy`, so the chatbot can say which model produced a number and show how it was generated (the ⓘ button under every prediction answer; wording in `methods.py`).

| Key | Prediction type | Paper | Notebook | Loaded from |
|---|---|---|---|---|
| `diffusion` | Bounded logistic diffusion capped by the fleet turnover path (central / low / high, quarterly to 2045): private battery-electric cars, their share of private cars, the petrol and diesel cars remaining, the fitted curve and the turnover path | Sections 4.2, 4.6, 5.4 to 5.8 | Sections 6, 7, 13 | `cleets_prediction_kg.ttl` |
| `hierarchical` | Hierarchical diffusion, two-stage empirical Bayes (midpoint, rate, shrinkage per LAD; covariate effects) | Sections 4.3, 5.4 | Section 8 | `cleets_prediction_families.ttl` |
| `turnover` | Fleet turnover path from observed scrappage and second-hand entry: per LAD the private cars and their mean age at 2026 Q2, the share of first-year cars among cars entering, the path at 2030 Q1, 2035 Q1, 2040 Q4, 2045 Q4 and 2053 Q4, the petrol and diesel cars left at 2045 Q4 and the 50% and 90% quarters; Wales path by scrappage period; Weibull ceiling as a benchmark | Sections 4.6, 5.6 to 5.8; Supplementary Tables S15 to S18 | Sections 6, 11 | `cleets_prediction_families.ttl` |
| `neural` | Model comparison: turnover-constrained neural and graph neural predictions, bounded logistic, persistence with drift and an unconstrained network (rolling-origin backtest, 2022 Q1 to 2025 Q4, 352 held-out LAD-quarters per model; MAE 1 to 16 quarters ahead). Evaluation only: no network prediction to 2045 | Sections 4.4, 4.5, 5.5; Supplementary Table S8 | Sections 9, 10 | `cleets_prediction_families.ttl` |
| `charging` | Charging-provision constraint classification for 2045 (September 2026 analysis, not in the paper) | none | earlier notebook, Stage 8 | `cleets_prediction_families.ttl` |
| `covariates` | Cross-sectional covariate comparison, Ridge residuals per LAD (September 2026 analysis, not in the paper) | none | earlier notebook, Stages 4a-bis, 5 | `cleets_prediction_families.ttl` |

In Prediction mode the **Prediction type** selector forces a type; **Auto** picks it from the wording of the question (neural, GNN → model comparison; turnover, scrappage, second-hand, age of cars, 2053 → turnover; midpoint, slowest, diffuse → hierarchical; charging provision → charging; relate, covariate, density, deprivation → covariates; otherwise the quarterly predictions). A question that names a quarter, or asks about the cars that remain, is answered from the quarterly predictions, which carry each district's turnover path quarter by quarter. Questions about accuracy (most accurate, best model, which model, backtest, MAE, RMSE, drift, persistence) are answered with the paper's ranking of the five models for private battery-electric cars and the multi-horizon comparison.

## Rebuilding the prediction graphs

Both files are written from the companion notebook's CSV exports, kept in `data/notebook_exports/`:

```bash
python tools/build_prediction_kg.py            # diffusion_scenarios_to_2045.csv -> data/cleets_prediction_kg.ttl
python tools/update_prediction_families.py     # hierarchical, turnover and model-comparison types -> data/cleets_prediction_families.ttl
python build_site.py                           # refresh the GitHub Pages snapshot and the README block
```

Copy the notebook's exports into `data/notebook_exports/` after a new run and re-run the three commands; the values shown in the dashboard are those of the run you supply. `tools/update_prediction_families.py` replaces the three types in place and leaves the charging-constraint and covariate types, which come from the September 2026 notebook (`build_prediction_families.py`), as they are.

`app.py` loads `cleets_prediction_kg.ttl` plus `cleets_prediction_families.ttl` when the file exists (override with `PREDICTION_TTL=a.ttl,b.ttl` in `.env`).

## Custom datasets

Two routes to a per-LAD table, both read from the graphs:

1. **Ask the chatbot**: "Give me a table of battery-electric cars, keepership, charging count, deprivation, population and population density for the 22 LADs", "Extract predicted 2045 battery-electric cars and turnover arrival quarter for Cardiff, Swansea and Newport as CSV". Column keywords: battery-electric cars, private cars, keepership, chargers, keepers per charger, per 100k, per 1,000, vehicle stock, population, density, deprivation, predicted / scenario, midpoint, turnover / arrival / residual, mean age, first-year entries, charging constraint, covariate residual. A year in the question selects that observation year.
2. **Dataset builder panel**: tick columns, choose districts (clicking a district on the map adds or removes it), optional year, **Build table**.

Either way the table appears in the dataset panel with its source datasets, **Download CSV** saves it (with a `... period` column giving the vintage of every observed value), and **Plot on map** colours the map by any numeric column.
