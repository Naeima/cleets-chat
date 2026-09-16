"""
methods.py: the 'how was this predicted?' explanations shown behind the ⓘ
button next to every prediction in CLEETS-CHAT.

Each entry is Markdown. The wording follows the companion notebook
(CLEETS_EV_Adoption_Wales_Quarterly, the 2026-09 quarterly revision of
Final_Modelling_CLEETS_all_body_types_private_keepership: stage headings and
in-cell documentation) and the provenance recorded in the Prediction KG
(prov:Activity comments, cleets:Scenario constraints). Numbers that are read
from the KG at run time are filled in by qa_with_humanization.methods_text()
({metrics_table7}, {metrics_stage13}, {best_line}, ...); nothing here is estimated.

Edit freely: this file is plain text and the app reloads it on restart.
"""

# Map from family key (prov:Activity local-name prefix) to explanation.
METHODS = {
    "diffusion": {
        "title": "Bounded logistic diffusion, scenario-constrained (paper S2.3.6, S3.4.3, S3.5; notebook Stage 6)",
        "body": """
**What is predicted.** For each of the 22 Welsh LADs, the quarterly matched-scope
private-fleet penetration: private battery-electric vehicles (VEH0132, keepership =
Private, body type = All, cars and vans aggregated) divided by private licensed
vehicles across all body types and fuels (VEH0105, keepership = Private). Counts are
the predicted share multiplied by the LAD's latest VEH0105 private stock, which is
held fixed as the ceiling.

**How.** A separate bounded logistic curve (rate, midpoint) is fitted to each LAD's
quarterly observations, recency-weighted and shrunk toward the Wales anchor. The
three scenarios do not come from the historical series: one shared midpoint shift
per scenario moves every curve so that the capacity-weighted Wales-wide share at
2045 Q4 equals the scenario target. {scenario_lines}

**Example, in plain terms.** {example}

**How to read it.** The terminal value is an explicit scenario assumption, not an
official forecast and not a quantity inferred from the data. Rolling-origin
backtests assess withheld historical quarters; they do not validate the 2045
assumption. Every observation so far sits on the early limb of the S-curve, so the
per-LAD midpoints of this independent fit are weakly identified and should not be
compared with each other; the hierarchical model (below) is the tool for that.
Milestones stored in the KG give the first quarter at which each LAD's curve
crosses 50%, 90% and 95% share under each scenario.

**Backtest (notebook Stage 13, quarterly revision).** The same bounded logistic is
re-fitted off the released KG under a rolling-origin one-step-ahead protocol: every
quarter from 2022 Q1 to 2025 Q4 is held out in turn, the curve is fitted to the
quarters before it (at least eight per LAD), and the capacity follows the revised
Equation 2, K = alpha x the last *training* observation with alpha = 6 (low), 10
(central) and 15 (high), so nothing after the training window enters any fit.
The same folds score the networks and the persistence-plus-drift baseline of
Stage 14, which is what makes Table 7 comparable. {metrics_stage13}

**Provenance.** {activity}
""",
    },
    "hierarchical": {
        "title": "Hierarchical diffusion by two-stage empirical Bayes (paper S2.3.6, S3.5, Table 9, Figures 4-5; notebook Stage 11)",
        "body": """
**Why a second diffusion model.** The independent fits above let covariates enter
nowhere, and because adoption shares are still a few per cent, rate and midpoint
are weakly identified: many (rate, midpoint) pairs fit almost equally well. The
research question is about curve *parameters* ("which LADs diffuse slowly"), so
covariates are regressed on the parameters rather than on the share.

**How.** Stage 1 fits each LAD alone and keeps the estimate with its sampling
variance. Stage 2 meta-regresses those estimates on standardised covariates
(population density and population) with a DerSimonian-Laird between-LAD variance.
Stage 3 shrinks each LAD toward its covariate prediction with weight
tau^2 / (tau^2 + V_i), so noisily estimated LADs move furthest. A single joint
penalised fit was tried first and collapsed every LAD onto one curve; the two-stage
design avoids that because the between-LAD variance is estimated before shrinkage.
The model is evaluated on first differences of the share (trend removed) at 1, 4
and 8 quarters against persistence and linear-drift baselines.

**Outputs stored in the KG.** Per LAD: midpoint quarter, rate per quarter, 95%
interval width, shrinkage weight and lag in years against the Welsh median
midpoint; plus the covariate effects on the midpoint in quarters per standard
deviation (positive = slower). {effects}

**Example, in plain terms.** {example}

**How to read it.** Every observation lies far below a quarter of the ceiling, so
the midpoint is extrapolated, never observed; wide intervals are the correct
answer rather than a fitting failure. The coefficients answer "what makes an LAD
diffuse late", not "what predicts its current share". Values come from the
notebook run supplied with the dashboard; the manuscript's Table 9 may differ
slightly (see the notebook's paper parity check).

**Provenance.** {activity}
""",
    },
    "turnover": {
        "title": "Age-structured fleet turnover under a 2032 new-sales phase-out (paper S2.3.5, S3.6, S3.8, Table 10, Figures 6-7; notebook Stages 7-9)",
        "body": """
**What is predicted.** The share of each LAD's private parc that is battery-electric
if the flow of new registrations changes as a policy scenario prescribes, rather
than if the historical curve is extrapolated. This is the "structural" or
age-structured route to 2045 and 2053.

**Scenario.** New non-BEV private registrations decline linearly to zero by 2032 Q4;
from 2033 Q1 every replacement registration is a BEV; each LAD's total private
stock is held at its latest VEH0105 value. (The 2032 date is a requested
counterfactual; current UK policy is a 2030 phase-out of new cars relying solely
on internal combustion and zero-emission new sales by 2035.)

**How.** Stage 7 retires vehicles at a constant hazard. Stage 8 replaces that with
a Weibull survival curve (shape 4.5) calibrated on median scrappage age, tested at
12, 14 and 16 years with 14 as the central case, because a constant hazard scraps
the last pre-ban cohorts far too quickly. The observed BEV vintages are read off
the quarterly stock increments and the whole age structure is carried forward
cohort by cohort to 2053 Q4 (Stage 9).

**Outputs stored in the KG.** Per LAD: BEV share at 2045 Q4 and at 2053 Q4,
residual non-BEV vehicles at the horizon end, and the first quarter at which 95%,
99% and 99.5% BEV share is reached; Wales-wide ceilings by scrappage age
(Table 10). {ceilings}

**Example, in plain terms.** {example}

**How to read it.** A ceiling, not a forecast: it assumes every new private vehicle
from the ban onward is a BEV and that no LAD lags in purchasing, so observed
differences can only push outcomes below it. After the ban all LADs receive the
same inflow, so arrival quarters converge; the residual non-BEV stock separates
LADs far more sharply than the BEV share does. Moving the ban date by two years
shifts the 2045 residual by a few tenths of a point; moving the median scrappage
age by two years shifts it by several points. Stage 11d reconciles this ceiling
against the diffusion curves: a diffusion projection above the ceiling describes a
transformation faster than vehicle retirement permits.

**Provenance.** {activity}
""",
    },
    "charging": {
        "title": "Charging-provision constraint by 2045 (research question 2; notebook Stage 8)",
        "body": """
**Question.** Where may public charging provision be the principal constraint on
adoption?

**How.** Each LAD's 2045 BEV count from the turnover trajectory is compared with
its public charging devices (EVCI9001) grown at 5% a year for 20 years (the
'slow' scenario) against a benchmark of 20 BEVs per public device. LADs that
diffuse slowly *and* fall short of the benchmark are classed as "charging
plausibly binding"; the others as "provision will bind later". The flagged set is
re-tested under frozen (0%/yr) and sustained (12%/yr) charger growth.

**Example, in plain terms.** {example}

**How to read it.** Under all three growth scenarios every LAD sits below the
benchmark, so the classification separates timing rather than whether provision
binds. The benchmark and growth rates are assumptions, not observations; the
class is only as good as those assumptions. Charger counts are deliberately kept
out of the adoption models themselves because installation follows uptake.

**Provenance.** {activity}
""",
    },
    "neural": {
        "title": "Scenario-constrained neural and graph neural forecasts (paper S2.3.2-S2.3.4, S3.4.1, Tables 5-7; notebook Stages 6e, 13, 14)",
        "body": """
**Rolling-origin comparison (Stages 13-14, quarterly revision).** One SPARQL query
(Listing 1) extracts the quarterly LAD panel from the released KG, for two targets:
private BEV keepership (VEH0132) and public charging devices (EVCI9001). Six
predictors are scored on identical folds: a multilayer perceptron (quarter index
to level), a scenario-constrained perceptron (quarter index and capacity K as
inputs), a two-layer graph convolutional network over a 22-node LAD similarity
graph, its scenario-constrained variant, a persistence-plus-drift baseline (last
value plus the mean quarterly change over the preceding four quarters) and the
bounded logistic of Stage 13. For each test quarter from 2022 Q1 to 2025 Q4 the
model trains on every observation before it and the observation at that quarter is
held out; only LADs with at least eight training quarters enter a fold, giving 352
held-out LAD-quarters per configuration. The scenario capacity follows the revised
Equation 2, K = alpha x the last *training* observation (alpha = 6, 10, 15 for
low, central, high), so no post-training value enters any fit. Mean R2 is the mean
of per-LAD R2 over each district's held-out quarters; pooled R2 over all held-out
LAD-quarters is reported alongside because the two answer different questions
(within-district tracking against cross-sectional fit). Because alpha multiplies a
per-LAD constant that input standardisation removes, the scenario-constrained NN
returns identical metrics under every scenario (Table 6 collapses its scenario
rows). {metrics_table7}

**Example, in plain terms.** {example}

**Which is most accurate.** {best_line} Persistence + drift is the strongest
one-quarter-ahead predictor and the scenario-constrained network the best neural
model, but neither can carry a scenario, saturate, or hold up over multi-quarter
horizons, so the bounded logistic remains the forecasting instrument for the 2045
scenarios; the plain NN and GNN degrade sharply without the per-LAD capacity input,
which is the informative comparison rather than a defect. {forecast_note}

**Quarterly neural adoption-ratio model (Stage 6e).** The matched-scope adoption
ratio is computed inside a single SPARQL query, a small feed-forward network with
a learned LAD embedding is trained on lagged logit shares and scored on first
differences against persistence and linear-drift baselines over the last eight
quarters. The network does not beat linear drift on first differences; the
notebook reports this as a negative result, and the SPARQL-to-model pipeline stands
regardless of which predictor wins. Charger counts are excluded as adoption
features because installation follows uptake. {metrics_6e}

**Provenance.** {activity}
""",
    },
    "covariates": {
        "title": "Covariate analysis: cross-sectional comparison and covariate effects (paper S3.4.2, Table 8; notebook Stages 4a-bis, 5, 11)",
        "body": """
**Covariates.** For each LAD the notebook extracts population, population density,
land area, EV keepership, public charge points, EVs per 1,000 residents, chargers
per 100k residents and EVs per charge point from the KG (Stage 4a-bis), with the
pooling scope fixed to the 22 Welsh LADs. Charger-derived variables are excluded
as predictors because installation follows uptake.

**Cross-sectional comparison (Stage 5).** Population, density and area are used to
predict EVs per 1,000 residents at the target quarter with a mean baseline,
Ridge (Hoerl and Kennard 1970), Random Forest, Extra Trees, and three GNNs (GCN,
GAT, GraphSAGE) over ONS boundary contiguity, under leave-one-out evaluation with
scaling refit inside each fold and stochastic models refit under five seeds.
{metrics_table8}

**Example, in plain terms.** {example}

**How to read it.** The seed-to-seed spread is at least as large as the gap between
the best model and predicting the mean, so no single winning architecture is
reported; Ridge selects the largest penalty and shrinks to its intercept, meaning
the features carry little linear signal about the current share. The Ridge
residuals are still informative as a ranking of LADs that adopt above or below
what population, density and area would predict. {residuals}

**Covariate effects on diffusion timing (Stage 11).** In the hierarchical model the
same covariates are regressed on the curve *midpoint* rather than on the share:
{effects}

**Provenance.** {activity}
""",
    },
}

FAMILY_SHORT = {
    "diffusion": "Diffusion curve (bounded logistic scenarios)",
    "hierarchical": "Hierarchical diffusion (empirical Bayes)",
    "turnover": "Age-structured turnover (2032 phase-out)",
    "charging": "Charging-constraint classification",
    "neural": "Scenario-constrained neural / GNN",
    "covariates": "Covariate analysis",
}
