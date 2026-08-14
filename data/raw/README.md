# Raw Data

The original raw CSV files are intentionally excluded from this public repository because they were provided as part of a private technical exercise.

The pipeline expects four source files in this directory:

- `marketing_spend.csv`
- `marketing_campaigns.csv`
- `dim_user.csv`
- `user_activity.csv`

These filenames are referenced by the dbt source definitions and profiling workflow.

All source files are treated as immutable inputs. Data cleaning, normalization, deduplication, and business-rule handling occur downstream in the dbt staging and core models.

To run the project locally, provide compatible source files using the filenames above before running:

```bash
make explore
make build
make train
make app