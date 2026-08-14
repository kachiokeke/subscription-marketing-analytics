# Decisions Log

This document records the main data-quality findings, analytical definitions, modelling choices, and scope decisions made during the project.

## Exploration findings

### `marketing_spend`

- The source contained daily spend by campaign across the available observation period.
- No null values, exact duplicates, zero spend, or negative spend values were identified.
- All mapped campaigns had regular daily spend observations.
- Spend extended one day beyond the latest recorded user-attribution cohort.

### `marketing_campaigns`

- Campaign metadata was complete and unique for the mapped campaigns.
- Campaign types were consistently represented across the source.
- One campaign identifier appearing in the user data was not present in campaign metadata.

### `dim_user`

- The user dimension contained substantially more rows than distinct users.
- Both exact duplicate rows and user-level conflicts were present.
- Most conflicting attributes involved `gender`.
- Gender values also contained inconsistent formatting and several representations of unknown or missing information.
- Country contained null and invalid placeholder values.
- One campaign identifier, `C999`, appeared in the user data but was not present in the campaign metadata.
- After exact duplicates were removed, some users still contained genuinely conflicting profile information.

Gender conflicts fell into three useful categories:

1. differences resolved purely through normalization;
2. one informative value combined with one or more unknown values;
3. contradictory informative values.

This distinction informed the cleaning strategy rather than using a simple majority vote.

### `user_activity`

- Activity contained onboarding, trial, and sale events.
- Every user had exactly one onboarding event.
- Trial and sale events occurred only after onboarding.
- Some users recorded a sale without a recorded trial event.
- Some users had multiple sale events.
- Sale events contained valid positive revenue, while null revenue on onboarding and most trial events was contextually expected.
- No exact duplicate activity rows were identified.
- Campaign ID and attribution date were internally consistent within users.
- Some users had no known onboarding experience.
- The unmapped campaign `C999` was consistently represented across the user and activity data.
- User-attribution dates ended before the final spend date, while subsequent activity continued long enough for all included users to have a complete 14-day outcome window.
- Repeated sale events were distinct transactions rather than exact duplicate rows.

## Data quality decisions

- Raw source files remain unchanged. Cleaning occurs in dbt staging and core models.
- Exact duplicate rows are removed from `dim_user` before resolving user-level conflicts.
- Gender values are trimmed, normalized to lowercase, and invalid or uninformative representations are standardized as `unknown`.
- `prefer_not_to_say` remains a separate explicit response rather than being treated as missing.
- When a user has one informative gender value and one or more unknown values, the informative value is retained.
- When a user has contradictory informative gender values, gender is set to `unknown`.
- Invalid or missing country values are standardized as `unknown`.
- Campaign `C999` is preserved as an unmapped campaign category.
- `C999` remains in user-level and predictive analysis but is excluded from spend-based efficiency metrics because no corresponding campaign metadata or spend is available.
- Missing onboarding names are standardized as `unknown` where no alternative known value exists.
- Users with a recorded sale but no trial remain in the analysis. The sale is an observed outcome, while the missing funnel stage remains explicitly visible.
- All positive, distinct sale events are retained as observed transactions.
- Initial-sale revenue and total observed sale revenue are calculated separately.
- Multiple sale events do not create multiple positive observations for the predictive sale target.
- `attribution_date` is treated as the canonical acquisition date because it matches the recorded event date throughout the activity data.
- High spend and revenue values are not removed or capped without evidence that they are invalid.
- All users are retained in outcome analysis because each attribution cohort has a complete 14-day observation window.
- Where duplicated profile records contain conflicting campaign values, downstream attribution uses the stable campaign ID recorded on the onboarding activity.

## Metric decisions

- The user journey has one row per user.
- `started_trial` equals one when at least one `start_trial` event exists.
- `made_sale` equals one when at least one `sale` event exists.
- `sale_without_trial` identifies users with a sale but no recorded trial.
- Initial-sale revenue is the sum of revenue recorded at the earliest sale timestamp.
- Total-sale revenue is the sum of revenue from all recorded sale events.
- Multiple sale events do not create multiple positive observations in the predictive target.
- Campaign attribution is based on the user's onboarding event.
- Campaign performance has one row per mapped campaign.
- User outcomes and campaign spend are first aggregated independently to `campaign_id + date` before being joined.
- Campaign-efficiency metrics use the aligned campaign-date window where both spend and attributed user cohorts are available.
- Spend outside that matched attribution window remains valid source data but is not included in the cohort-efficiency mart.
- Trial rate equals trial users divided by attributed users.
- Sale rate equals sale users divided by attributed users.
- Cost per trial equals campaign spend divided by trial users.
- Cost per sale equals campaign spend divided by sale users.
- Initial-revenue ROAS equals initial-sale revenue divided by campaign spend.
- Total-revenue ROAS equals all observed sale revenue divided by campaign spend.
- Campaign `C999` is excluded from spend-based efficiency metrics because no corresponding spend or campaign metadata exists.

## Modeling decisions

- Two separate binary models predict `started_trial` and `made_sale`.
- Predictions are made from information available at onboarding.
- Predictors are:
  - gender;
  - country;
  - campaign;
  - onboarding experience;
  - attribution weekday.
- Acquisition month is retained in the feature table for exploration but excluded from model training because the observation period is short and the final chronological test period contains a month not represented in training.
- Trial timestamps, sale timestamps, event counts, revenue, and other post-onboarding information are excluded to prevent target leakage.
- `started_trial` is not used as a predictor for `made_sale`. Both models use the same onboarding-time predictor set.
- Campaign `C999` remains in predictive analysis as an unmapped campaign category.
- Logistic regression is used as an interpretable baseline for both binary outcomes.
- Categorical variables are one-hot encoded, with one category per predictor serving as the reference group.
- Data is split chronologically:
  - earlier users form the training set;
  - the middle period forms the validation set;
  - the latest period forms the test set.
- Prediction thresholds are selected using validation data by maximizing F1.
- The final test period does not influence model fitting or threshold selection.
- The trial model selected a threshold of `0.24` and achieved a test ROC AUC of approximately `0.53`.
- The sale model selected a threshold of `0.18` and also achieved a test ROC AUC of approximately `0.53`.
- Both models achieve high recall partly because they classify a large proportion of test users as positive.
- The models therefore do not provide sufficient discrimination for narrow individual targeting.
- Onboarding experience shows the strongest observed association with both outcomes.
- Logistic-regression coefficients are interpreted relative to reference categories and describe associations rather than causal effects.

## Model limitations

- The feature set contains only a small number of categorical variables available at onboarding.
- It does not include potentially stronger signals such as:
  - device;
  - creative;
  - advertising placement;
  - pricing;
  - onboarding responses;
  - early in-app behaviour.
- The available history covers a relatively short period.
- Logistic regression assumes additive, linear effects on the log odds and may miss nonlinear relationships or interactions.
- The model results should therefore be treated as interpretable exploratory baselines rather than production-ready targeting systems.

## Scope decisions

- The analysis prioritizes campaign performance, user journeys, and interpretable onboarding-time prediction.
- A more complex predictive model was not added because the available predictors provide weak signal, and additional complexity would reduce interpretability without guaranteeing useful improvement.
- Post-onboarding behaviour and outcome variables are deliberately excluded from the predictors because they would introduce target leakage.
- Campaign `C999` remains in user-level and predictive analysis but is excluded from spend-based efficiency metrics.
- Predictive relationships are treated as associations rather than causal effects.
- No recommendation assumes that a campaign or onboarding experience caused the observed outcome.

With more time, I would:

- compare logistic regression with a tree-based model;
- examine probability calibration;
- test selected interaction effects;
- evaluate model performance across campaigns and countries;
- incorporate richer acquisition and behavioural features where available.

## Productionization

In a production environment, fresh source data would load into a managed warehouse on a regular schedule.

An orchestrated workflow would:

1. validate source freshness and schema expectations;
2. run the dbt staging, core, and feature models;
3. stop downstream publication and alert if a critical test fails;
4. refresh campaign-performance and user-level analytical tables;
5. score newly eligible users where required;
6. refresh the model-output tables consumed by the presentation layer.

The data pipeline and user scoring could run daily.

The predictive models would not need to retrain every day. Retraining could occur monthly or when monitoring detects material changes in conversion rates, feature distributions, calibration, or model performance.

Production monitoring would cover:

- source freshness;
- row counts;
- duplicate and conflict rates;
- unmapped campaign volume;
- dbt test results;
- campaign-performance metrics;
- feature distributions;
- model discrimination and calibration.