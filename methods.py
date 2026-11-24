"""
methods.py: the 'how was this predicted?' explanations shown behind the ⓘ
button next to every prediction in CLEETS-CHAT.

Each entry is Markdown. The wording follows the companion notebook
(EVAdoptionWalesPredictionsModels, 24 November 2026) and the provenance recorded
in the Prediction KG (prov:Activity comments, cleets:Scenario definitions).
Numbers that are read from the KG at run time are filled in by
qa_with_humanization.methods_text() ({scenario_lines}, {cap_line}, {ceilings},
{metrics_comparison}, {best_line}, ...); nothing here is estimated.

The charging-constraint and covariate entries describe analyses of the September
2026 notebook that are no longer part of the paper; each says so in its first line.

Edit freely: this file is plain text and the app reloads it on restart.
"""

# Map from family key (prov:Activity local-name prefix) to explanation.
METHODS = {
    "diffusion": {
        "title": "Quarterly predictions to 2045: logistic diffusion capped by the fleet turnover path (paper Sections 4.2, 4.6 and 5.4 to 5.8; Supplementary Tables S9 to S14)",
        "body": """
**What is predicted.** For each of the 22 Welsh districts and every quarter from
2026 Q1 to 2045 Q4: the share of private cars that are battery electric, that is
private battery-electric cars (VEH0142) divided by private cars of all fuels
(VEH0105); the number of private battery-electric cars, which is that share
multiplied by the district's private cars at 2026 Q2 (VEH9901); and the petrol and
diesel cars that remain, hybrids included, which is the same stock less the
battery-electric cars. A Wales total is stored for every quarter.

**How.** A separate logistic curve (rate, midpoint) is fitted to each district's
quarterly observations from 2011 Q4 to 2025 Q4, recency-weighted. The curve alone
would let the stock change faster than cars leave and enter private keepership, so
in every predicted quarter the reported share is the lower of the fitted curve and
the district's own turnover path. The path is a stock-flow model started from the
cars licensed at 2026 Q2 by fuel and year of first registration: cars leave at the
scrappage rates observed for British cohorts (VEH1111), cars enter at the ages at
which they do so in each district, new and second hand, and the battery-electric
share of new cars rises from 24.7% in 2026 to 80% in 2030 and 100% in 2035.
{scenario_lines}

**Example, in plain terms.** {example}

**How to read it.** Each row records the fitted curve, the turnover path and which
of the two is reported. {cap_line} The path is an estimate and not a bound: faster
scrappage, a growing stock or a faster second-hand market would lift it. The
private car stock is held at its 2026 Q2 level, and hybrids are counted with petrol
and diesel cars. Every observation so far sits on the early limb of the S-curve, so
the fitted midpoints are extrapolated; the hierarchical model (below) is the tool
for comparing the districts' fitted curves. Milestones stored in the KG give the
first quarter at which each district reaches 10%, 25%, 50% and 75% under each
scenario, where that falls before 2045 Q4.

**Backtest.** {backtest_line}

**Provenance.** {activity}
""",
    },
    "hierarchical": {
        "title": "Hierarchical diffusion by two-stage empirical Bayes (paper Sections 4.3 and 5.4; notebook Section 8)",
        "body": """
**Why a second diffusion model.** The independent fits above let covariates enter
nowhere, and because adoption shares are still a few per cent, rate and midpoint
are weakly identified: many (rate, midpoint) pairs fit almost equally well. The
research question is about curve *parameters* ("which districts diffuse slowly"),
so covariates are regressed on the parameters and not on the share.

**How.** Stage 1 fits each district alone, on its share of private cars that are
battery electric, and keeps the estimate with its sampling variance. Stage 2
meta-regresses those estimates on standardised covariates (population density and
population) with a DerSimonian-Laird between-district variance. Stage 3 shrinks
each district toward its covariate prediction with weight tau^2 / (tau^2 + V_i), so
noisily estimated districts move furthest. A single joint penalised fit was tried
first and collapsed every district onto one curve; the two-stage design avoids that
because the between-district variance is estimated before shrinkage. The model is
evaluated on first differences of the share (trend removed) at 1, 4 and 8 quarters
against a linear-drift baseline.

**Outputs stored in the KG.** Per district: midpoint quarter, rate per quarter, 95%
interval width, shrinkage weight and lag in years against the Welsh median
midpoint; plus the covariate effects on the midpoint in quarters per standard
deviation (positive = slower). {effects}

**Example, in plain terms.** {example}

**How to read it.** Every observed share is below 3%, so the midpoint is
extrapolated, never observed; wide intervals are the correct answer and not a
fitting failure. The coefficients answer "what makes a district diffuse late", not
"what predicts its current share". These midpoints describe the fitted curves
before the turnover path is applied: under the path every district reaches 50%
later, and the order follows the age of its cars (see the turnover path).

**Provenance.** {activity}
""",
    },
    "turnover": {
        "title": "Fleet turnover path from observed scrappage and second-hand entry (paper Sections 4.6 and 5.6 to 5.8; Supplementary Tables S15 to S18; notebook Sections 6 and 11)",
        "body": """
**What is predicted.** The share of each district's private cars that is battery
electric if new cars follow the sales rule and cars keep leaving and entering
private keepership as the licensing tables show they do. It is the path that caps
the diffusion curves.

**How.** The model follows private cars by district, fuel and year of first
registration from the stock licensed at 2026 Q2 (VEH9901). Scrappage is measured,
not assumed: following a cohort of British cars from one year end to the next
(VEH1111) gives the share still licensed at each age. Second-hand entry is measured
too: the age structure of each district's stock shows at which ages cars reach its
private keepers, so cars enter at every age and not only when new. The
battery-electric share of new cars rises from 24.7% in 2026 to 80% in 2030 (the
zero emission vehicle mandate) and 100% in 2035, and Welsh private keepers move from
their present, lower uptake to the national mix by 2030. Cars that leave are
replaced one for one, so each district's private car stock stays at its 2026 Q2
level.

**Outputs stored in the KG.** Per district: private cars and battery-electric cars
at 2026 Q2, the mean age of private cars and the share aged 15 years or more, the
share of entering cars that are in their first year, the battery-electric share on
the central path at 2030 Q1, 2035 Q1, 2040 Q4, 2045 Q4 and 2053 Q4, the petrol and
diesel cars left at 2045 Q4, and the first quarter at 50% and at 90%. Wales-wide:
the path at 2045 Q4 under the scrappage rates of three periods, and the Weibull
ceiling as a benchmark. {ceilings}

**Example, in plain terms.** {example}

**How to read it.** A path, not a ceiling: it estimates what the sales rule
delivers, and faster scrappage, a growing stock or a faster second-hand market would
lift it. Districts differ in level as well as in timing, and their order follows
the age of their cars more than their present adoption. The Weibull ceiling assumes
a median life and replaces every scrapped car with a new one; most of the gap
between it and the path comes from cars lasting longer than it assumes. The
second-hand profile is inferred from the age structure of the stock at one date,
not from records of transfers, and hybrids are counted with petrol and diesel cars.

**Provenance.** {activity}
""",
    },
    "charging": {
        "title": "Charging-provision constraint by 2045 (research question 2; notebook Stage 8)",
        "body": """
**Status.** This analysis is from the September 2026 notebook and is not part of
the current paper. Its vehicle counts are private battery-electric vehicles of all
body types (VEH0132), and its 2045 counts come from that notebook's turnover run
(a 2032 phase-out), not from the turnover path described above.

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
        "title": "Model comparison: turnover-constrained neural and graph neural predictions (paper Sections 4.4, 4.5 and 5.5; Supplementary Table S8; notebook Sections 9 and 10)",
        "body": """
**What is compared.** Five models predict private battery-electric cars in each
district under one protocol: a persistence-with-drift baseline (last value plus the
mean quarterly change over the preceding four quarters), a bounded logistic, a
multilayer perceptron and a two-layer graph convolutional network that are both
constrained by fleet turnover, and an unconstrained perceptron kept as a reference.
The constrained networks predict the battery-electric share of the cars that enter
private keepership in a quarter, so a prediction cannot grow faster than the
entering cars permit.

**Protocol.** For each test quarter from 2022 Q1 to 2025 Q4 a model trains on every
observation before it and the observation at that quarter is held out; only
districts with at least eight training quarters enter a fold, giving 352 held-out
district-quarters per model. Mean R2 is the mean of per-district R2 over each
district's held-out quarters; pooled R2 is computed over all held-out
district-quarters. The same origins are then rolled forward 1, 4, 8, 12 and 16
quarters without later data. {metrics_comparison}

**Example, in plain terms.** {example}

**Which is most accurate.** {best_line} Persistence with drift is the strongest
predictor one quarter ahead and the constrained network is close to it, but neither
can carry a scenario or saturate. {horizons} {forecast_note}

**Provenance.** {activity}
""",
    },
    "covariates": {
        "title": "Covariate analysis: cross-sectional comparison and covariate effects (paper S3.4.2, Table 8; notebook Stages 4a-bis, 5, 11)",
        "body": """
**Status.** The cross-sectional comparison is from the September 2026 notebook and
is not part of the current paper; it uses private battery-electric vehicles of all
body types (VEH0132). The covariate effects on diffusion timing at the end are those
of the current hierarchical model.

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
    "diffusion": "Diffusion curve capped by the turnover path",
    "hierarchical": "Hierarchical diffusion (empirical Bayes)",
    "turnover": "Fleet turnover path (scrappage and second-hand entry)",
    "charging": "Charging-constraint classification (September 2026 analysis)",
    "neural": "Model comparison (turnover-constrained neural / GNN)",
    "covariates": "Covariate analysis (September 2026 analysis)",
}
