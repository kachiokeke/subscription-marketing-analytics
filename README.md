# Subscription Marketing Analytics

An end-to-end analytics project that transforms raw subscription marketing and user-event data into tested campaign-performance metrics, interpretable conversion models, and a decision-focused Streamlit application.

> **Data availability:** The original raw data was provided as part of a private technical exercise and is intentionally excluded from this public repository. The transformation, testing, modelling, and application logic are included in full.

## Business Problem

The project was built around two marketing questions:

1. **Which acquisition campaigns are generating the strongest returns and therefore deserve more investment?**
2. **Can information available when a user first onboards help identify who is likely to start a trial or eventually make a sale?**

Answering those questions required more than calculating a few campaign metrics. The source data contained duplicate and conflicting user records, an unmapped campaign, unusual customer journeys, repeated sale events, and different grains across user activity and marketing spend.

The analysis therefore focused first on creating reliable analytical foundations before producing recommendations.

## What I Built

The project implements a complete local analytics workflow:

```text
Raw marketing + user data
        ↓
Data profiling
        ↓
dbt staging models
        ↓
Trusted user journey
        ↓
Campaign performance mart
        ↓
User-level ML feature table
        ↓
Logistic regression models
        ↓
Streamlit decision application
```

### Technology

* **dbt** — transformation, documentation, and testing
* **DuckDB** — local analytical warehouse
* **Python / pandas** — data profiling and modelling workflow
* **scikit-learn** — preprocessing and logistic regression
* **Streamlit** — business-facing analytics application

## Key Data Decisions

### Resolving duplicate and conflicting users

The raw user dimension contained more rows than unique users because of both exact duplicates and conflicting profile records.

The cleaning strategy was intentionally conservative:

* exact duplicates were removed first;
* formatting and categorical inconsistencies were normalised;
* one known value paired with an unknown value retained the known value;
* genuinely contradictory known values were classified as `unknown` rather than resolved through majority voting.

This avoids treating repeated duplicate rows as independent evidence.

### Preserving unusual customer journeys

Observed behaviour was not discarded simply because it did not match an assumed ideal funnel.

The final user journey therefore preserves:

* users who made a sale without a recorded trial;
* users with multiple sale events;
* missing values that are contextually valid for certain event types.

A user can only count once as a converter, while all valid sale events can still contribute to observed revenue.

### Campaign attribution

Campaign attribution is taken from the user's onboarding event.

The resulting `fct_user_journey` model contains one row per user and provides consistent acquisition, trial, sale, and revenue measures for downstream analysis.

### Preventing spend multiplication

User outcomes and campaign spend originate at different grains.

Rather than joining daily spend directly to individual users, each side is first aggregated independently to:

```text
campaign_id + date
```

The aligned daily records are then joined before being rolled up to campaign level.

This prevents the same daily campaign spend from being repeated once for every acquired user.

## Analytical Models

### User Journey

`fct_user_journey` converts event-level activity into one analytical observation per user.

It includes:

* campaign attribution;
* onboarding experience;
* onboarding, trial, and first-sale timestamps;
* binary trial and sale outcomes;
* sale-without-trial indicators;
* number of sale events;
* initial sale revenue;
* total observed sale revenue.

This table becomes the common foundation for both campaign analysis and predictive modelling.

### Campaign Performance

`mart_campaign_performance` produces one row per mapped campaign with metrics including:

* attributed users;
* trial users;
* sale users;
* trial rate;
* sale rate;
* total campaign spend;
* cost per trial;
* cost per sale;
* initial-revenue ROAS;
* total-revenue ROAS.

The model separates **scale** from **efficiency** rather than treating a single metric as sufficient for campaign allocation.

## Predictive Modelling

Two logistic-regression models explore whether onboarding-time information is associated with:

1. starting a trial;
2. making a sale.

Only information available at onboarding is used as predictors:

* gender;
* country;
* campaign;
* onboarding experience;
* acquisition weekday.

Trial status is **not** used to predict sale, and revenue, sale timestamps, event counts, and other post-onboarding information are excluded to prevent target leakage.

### Evaluation Strategy

Users are split chronologically:

```text
Earlier users → Training
Middle period → Validation
Latest users → Test
```

The training data learns the model coefficients.

Validation data is used to select the classification threshold that maximises F1.

The selected model and threshold are then evaluated once on the untouched test period.

### Model Interpretation

Onboarding experience showed the strongest observed association with both trial and sale outcomes.

However, both models achieved test ROC AUC values of only approximately **0.53**.

The models also achieved high recall partly by classifying a large proportion of users as positive.

For that reason, the predictive outputs are treated as **interpretable exploratory baselines**, not as production-ready individual targeting systems.

This is an important conclusion of the project: a useful analysis does not always end with recommending that a model be deployed.

## Business Findings

The campaign analysis identified three different performance stories:

* **TikTok Creators** showed the strongest observed campaign efficiency.
* **TikTok** generated the largest amount of total observed revenue while maintaining strong efficiency.
* **IG Creators** showed the weakest observed return and was the clearest candidate for review.

The resulting recommendation was to:

* test a controlled increase in TikTok Creators spend;
* protect TikTok as the main scale and revenue campaign;
* review IG Creators targeting, creative, and placement before allocating additional budget;
* use onboarding-model associations to prioritise controlled experiments rather than automate individual targeting.

These findings describe the supplied observation period and should not be interpreted as causal effects.

## Streamlit Application

The Streamlit application is intentionally kept as a thin presentation layer.

It reads prepared analytical tables rather than performing raw-data cleaning, joins, or model training inside the application.

The interface is organised around three questions:

### Campaign decisions

Which campaigns are producing the strongest combination of efficiency and scale?

### What influences conversion?

Which onboarding-time factors show the strongest associations with trial and sale outcomes, and how reliable are those models?

### How the analysis works

What attribution rules, metric definitions, modelling assumptions, and limitations sit behind the recommendations?

## Testing

The dbt project combines standard schema tests with custom business-rule tests.

Tests cover areas such as:

* uniqueness and required fields;
* accepted categorical values;
* event-date consistency;
* sale revenue rules;
* user-journey logic;
* feature-table consistency;
* campaign-performance calculations.

The objective is not simply to confirm that the SQL runs, but to protect the assumptions behind the business metrics.

## Project Structure

```text
.
├── app/
│   └── streamlit_app.py
├── data/
│   └── raw/
│       └── README.md
├── ml/
│   └── train.py
├── models/
│   ├── core/
│   │   ├── fct_user_journey.sql
│   │   └── mart_campaign_performance.sql
│   ├── features/
│   │   └── user_features.sql
│   ├── staging/
│   │   ├── stg_dim_user.sql
│   │   ├── stg_marketing_campaigns.sql
│   │   ├── stg_marketing_spend.sql
│   │   └── stg_user_activity.sql
│   └── sources.yml
├── tests/
├── DECISIONS.md
├── REPORT.md
├── explore.py
├── Makefile
└── requirements.txt
```

## Running the Project

The original source CSVs are not included in this public repository.

With compatible source data placed in `data/raw/`, the project can be set up with:

```bash
make setup
```

Profile the raw data:

```bash
make explore
```

Build the transformation layer and run tests:

```bash
make build
```

Train the predictive models:

```bash
make train
```

Launch the Streamlit application:

```bash
make app
```

The complete analytical workflow can also be executed with:

```bash
make all
```

## Productionisation

In a production environment, source data would be loaded into a managed cloud warehouse on a schedule.

An orchestrated workflow would:

1. ingest and validate fresh source data;
2. run the dbt transformation pipeline;
3. stop downstream publication if critical tests fail;
4. refresh campaign and user-level analytical tables;
5. score eligible users when required;
6. publish refreshed analytical outputs;
7. monitor data freshness, campaign quality, unmapped attribution, and model performance.

Data refresh and scoring could run daily, while model retraining would occur less frequently or when monitoring detected meaningful drift.

## Limitations

The analysis should be interpreted within several constraints:

* the available observation period is relatively short;
* one campaign identifier has no corresponding metadata or spend;
* the predictive feature set contains limited onboarding-time information;
* the models do not establish causal relationships;
* repeated sale events are retained as observed transactions, but their underlying business meaning is not known;
* campaign performance may change as spend scales.

## Note

This repository is a sanitized portfolio version of a technical analytics exercise.

The original raw data is intentionally excluded. All transformation logic, analytical models, tests, modelling code, and application code shown here were developed as part of the project.
