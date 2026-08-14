"""Train trial and sale prediction models.

The script:
1. Reads the user feature table from DuckDB.
2. Uses earlier users for training.
3. Uses a middle period to select a prediction threshold.
4. Uses the latest users for final testing.
5. Writes model metrics and coefficients to DuckDB.
"""

from pathlib import Path

import duckdb
import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder


# -------------------------------------------------------------------
# Project configuration
# -------------------------------------------------------------------

WAREHOUSE = (
    Path(__file__).resolve().parents[1]
    / "warehouse.duckdb"
)

FEATURE_TABLE = "main.user_features"

# These are the fields that the model can use.
# All of them are available when the user completes onboarding.
PREDICTOR_COLUMNS = [
    "gender",
    "country",
    "campaign_label",
    "onboarding_name",
    "attribution_weekday",
]

# Train one model for each outcome.
TARGET_COLUMNS = [
    "started_trial",
    "made_sale",
]

# Split the available dates into:
# 60% training, 20% validation, and 20% testing.
TRAIN_DATE_SHARE = 0.60
VALIDATION_DATE_SHARE = 0.20

# Test probability thresholds from 5% through 50%.
THRESHOLD_GRID = np.arange(
    0.05,
    0.51,
    0.01,
)


# -------------------------------------------------------------------
# Load and validate the feature table
# -------------------------------------------------------------------

def load_features() -> pd.DataFrame:
    """Read the feature table and check its basic quality."""

    connection = duckdb.connect(
        str(WAREHOUSE),
        read_only=True,
    )

    try:
        dataframe = connection.execute(
            f"""
            select *
            from {FEATURE_TABLE}
            """
        ).fetchdf()
    finally:
        connection.close()

    required_columns = {
        "user_id",
        "attribution_date",
        *PREDICTOR_COLUMNS,
        *TARGET_COLUMNS,
    }

    missing_columns = (
        required_columns - set(dataframe.columns)
    )

    if missing_columns:
        missing_text = ", ".join(
            sorted(missing_columns)
        )

        raise ValueError(
            "The feature table is missing these columns: "
            f"{missing_text}"
        )

    if dataframe.empty:
        raise ValueError(
            "The feature table contains no rows."
        )

    if dataframe["user_id"].duplicated().any():
        raise ValueError(
            "The feature table contains duplicate users."
        )

    dataframe["attribution_date"] = pd.to_datetime(
        dataframe["attribution_date"]
    )

    # Convert all model predictors to consistent text values.
    for column in PREDICTOR_COLUMNS:
        dataframe[column] = (
            dataframe[column]
            .astype("string")
            .fillna("unknown")
            .astype(str)
        )

    # Each target must contain only zero and one.
    for target in TARGET_COLUMNS:
        if dataframe[target].isna().any():
            raise ValueError(
                f"{target} contains null values."
            )

        observed_values = set(
            dataframe[target].unique()
        )

        invalid_values = observed_values - {0, 1}

        if invalid_values:
            raise ValueError(
                f"{target} contains invalid values: "
                f"{sorted(invalid_values)}"
            )

    return dataframe


# -------------------------------------------------------------------
# Divide users into historical periods
# -------------------------------------------------------------------

def split_chronologically(
    dataframe: pd.DataFrame,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.Timestamp,
    pd.Timestamp,
]:
    """Create training, validation, and test periods."""

    unique_dates = np.sort(
        dataframe[
            "attribution_date"
        ].dt.normalize().unique()
    )

    train_end_index = int(
        len(unique_dates)
        * TRAIN_DATE_SHARE
    )

    validation_end_index = int(
        len(unique_dates)
        * (
            TRAIN_DATE_SHARE
            + VALIDATION_DATE_SHARE
        )
    )

    if (
        train_end_index <= 0
        or validation_end_index
        <= train_end_index
        or validation_end_index
        >= len(unique_dates)
    ):
        raise ValueError(
            "There are not enough dates to create "
            "training, validation, and test periods."
        )

    validation_start_date = pd.Timestamp(
        unique_dates[train_end_index]
    )

    test_start_date = pd.Timestamp(
        unique_dates[validation_end_index]
    )

    training_data = dataframe[
        dataframe["attribution_date"]
        < validation_start_date
    ].copy()

    validation_data = dataframe[
        (
            dataframe["attribution_date"]
            >= validation_start_date
        )
        & (
            dataframe["attribution_date"]
            < test_start_date
        )
    ].copy()

    test_data = dataframe[
        dataframe["attribution_date"]
        >= test_start_date
    ].copy()

    datasets = {
        "training": training_data,
        "validation": validation_data,
        "test": test_data,
    }

    for dataset_name, dataset in datasets.items():
        if dataset.empty:
            raise ValueError(
                f"The {dataset_name} dataset is empty."
            )

        for target in TARGET_COLUMNS:
            if dataset[target].nunique() < 2:
                raise ValueError(
                    f"The {dataset_name} dataset for "
                    f"{target} contains only one class."
                )

    return (
        training_data,
        validation_data,
        test_data,
        validation_start_date,
        test_start_date,
    )


# -------------------------------------------------------------------
# Create the machine-learning pipeline
# -------------------------------------------------------------------

def build_pipeline() -> Pipeline:
    """Create category encoding and logistic regression."""

    category_encoder = OneHotEncoder(
        drop="first",
        handle_unknown="ignore",
    )

    preprocessor = ColumnTransformer(
        transformers=[
            (
                "categorical",
                category_encoder,
                PREDICTOR_COLUMNS,
            )
        ],
        remainder="drop",
    )

    classifier = LogisticRegression(
        max_iter=1000,
        solver="lbfgs",
    )

    return Pipeline(
        steps=[
            ("preprocessor", preprocessor),
            ("classifier", classifier),
        ]
    )


# -------------------------------------------------------------------
# Select a prediction threshold
# -------------------------------------------------------------------

def select_threshold(
    actual_values: pd.Series,
    probabilities: np.ndarray,
    target: str,
) -> tuple[float, pd.DataFrame]:
    """Select the validation threshold with the best F1 score."""

    threshold_results = []

    for threshold in THRESHOLD_GRID:
        predictions = (
            probabilities >= threshold
        ).astype(int)

        threshold_results.append(
            {
                "target": target,
                "threshold": float(threshold),
                "precision": float(
                    precision_score(
                        actual_values,
                        predictions,
                        zero_division=0,
                    )
                ),
                "recall": float(
                    recall_score(
                        actual_values,
                        predictions,
                        zero_division=0,
                    )
                ),
                "f1_score": float(
                    f1_score(
                        actual_values,
                        predictions,
                        zero_division=0,
                    )
                ),
                "predicted_positive_rate": float(
                    predictions.mean()
                ),
            }
        )

    threshold_dataframe = pd.DataFrame(
        threshold_results
    )

    best_result = (
        threshold_dataframe
        .sort_values(
            by=[
                "f1_score",
                "precision",
                "recall",
                "threshold",
            ],
            ascending=[
                False,
                False,
                False,
                False,
            ],
        )
        .iloc[0]
    )

    selected_threshold = float(
        best_result["threshold"]
    )

    return (
        selected_threshold,
        threshold_dataframe,
    )


# -------------------------------------------------------------------
# Extract model coefficients
# -------------------------------------------------------------------

def extract_coefficients(
    pipeline: Pipeline,
    target: str,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Convert model coefficients into readable tables."""

    encoder = (
        pipeline
        .named_steps["preprocessor"]
        .named_transformers_["categorical"]
    )

    coefficients = (
        pipeline
        .named_steps["classifier"]
        .coef_[0]
    )

    coefficient_rows = []
    reference_rows = []

    coefficient_position = 0

    for (
        predictor,
        categories,
        dropped_category_index,
    ) in zip(
        PREDICTOR_COLUMNS,
        encoder.categories_,
        encoder.drop_idx_,
    ):
        reference_category = str(
            categories[
                int(dropped_category_index)
            ]
        )

        reference_rows.append(
            {
                "target": target,
                "predictor": predictor,
                "reference_category": (
                    reference_category
                ),
            }
        )

        for category_index, category in enumerate(
            categories
        ):
            if (
                category_index
                == int(dropped_category_index)
            ):
                continue

            coefficient = float(
                coefficients[
                    coefficient_position
                ]
            )

            coefficient_rows.append(
                {
                    "target": target,
                    "predictor": predictor,
                    "category": str(category),
                    "feature": (
                        f"{predictor}={category}"
                    ),
                    "coefficient": coefficient,
                    "absolute_importance": abs(
                        coefficient
                    ),
                    "direction": (
                        "positive"
                        if coefficient > 0
                        else "negative"
                        if coefficient < 0
                        else "neutral"
                    ),
                    "odds_ratio": float(
                        np.exp(coefficient)
                    ),
                }
            )

            coefficient_position += 1

    coefficient_dataframe = pd.DataFrame(
        coefficient_rows
    ).sort_values(
        by="absolute_importance",
        ascending=False,
    )

    reference_dataframe = pd.DataFrame(
        reference_rows
    )

    return (
        coefficient_dataframe,
        reference_dataframe,
    )


# -------------------------------------------------------------------
# Train and evaluate one target
# -------------------------------------------------------------------

def train_target(
    training_data: pd.DataFrame,
    validation_data: pd.DataFrame,
    test_data: pd.DataFrame,
    target: str,
    validation_start_date: pd.Timestamp,
    test_start_date: pd.Timestamp,
) -> tuple[
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
    pd.DataFrame,
]:
    """Train and evaluate one binary prediction model."""

    pipeline = build_pipeline()

    training_features = training_data[
        PREDICTOR_COLUMNS
    ]

    training_target = training_data[
        target
    ].astype(int)

    validation_features = validation_data[
        PREDICTOR_COLUMNS
    ]

    validation_target = validation_data[
        target
    ].astype(int)

    test_features = test_data[
        PREDICTOR_COLUMNS
    ]

    test_target = test_data[
        target
    ].astype(int)

    # Learn model coefficients from historical users.
    pipeline.fit(
        training_features,
        training_target,
    )

    # Generate probabilities for the validation period.
    validation_probabilities = (
        pipeline.predict_proba(
            validation_features
        )[:, 1]
    )

    # Choose a threshold using validation data only.
    (
        selected_threshold,
        threshold_dataframe,
    ) = select_threshold(
        validation_target,
        validation_probabilities,
        target,
    )

    validation_predictions = (
        validation_probabilities
        >= selected_threshold
    ).astype(int)

    # Evaluate the selected approach on the latest users.
    test_probabilities = (
        pipeline.predict_proba(
            test_features
        )[:, 1]
    )

    test_predictions = (
        test_probabilities
        >= selected_threshold
    ).astype(int)

    (
        true_negative,
        false_positive,
        false_negative,
        true_positive,
    ) = confusion_matrix(
        test_target,
        test_predictions,
        labels=[0, 1],
    ).ravel()

    metric_record = {
        "target": target,
        "model_name": "logistic_regression",
        "prediction_threshold": (
            selected_threshold
        ),
        "validation_start_date": (
            validation_start_date.date()
        ),
        "test_start_date": (
            test_start_date.date()
        ),
        "train_rows": len(training_data),
        "validation_rows": len(
            validation_data
        ),
        "test_rows": len(test_data),
        "train_positive_rate": float(
            training_target.mean()
        ),
        "validation_positive_rate": float(
            validation_target.mean()
        ),
        "test_positive_rate": float(
            test_target.mean()
        ),
        "validation_roc_auc": float(
            roc_auc_score(
                validation_target,
                validation_probabilities,
            )
        ),
        "validation_f1": float(
            f1_score(
                validation_target,
                validation_predictions,
                zero_division=0,
            )
        ),
        "roc_auc": float(
            roc_auc_score(
                test_target,
                test_probabilities,
            )
        ),
        "precision": float(
            precision_score(
                test_target,
                test_predictions,
                zero_division=0,
            )
        ),
        "recall": float(
            recall_score(
                test_target,
                test_predictions,
                zero_division=0,
            )
        ),
        "f1_score": float(
            f1_score(
                test_target,
                test_predictions,
                zero_division=0,
            )
        ),
        "predicted_positive_rate": float(
            test_predictions.mean()
        ),
        "minimum_probability": float(
            test_probabilities.min()
        ),
        "median_probability": float(
            np.median(
                test_probabilities
            )
        ),
        "maximum_probability": float(
            test_probabilities.max()
        ),
        "true_negative": int(
            true_negative
        ),
        "false_positive": int(
            false_positive
        ),
        "false_negative": int(
            false_negative
        ),
        "true_positive": int(
            true_positive
        ),
    }

    metrics_dataframe = pd.DataFrame(
        [metric_record]
    )

    (
        coefficient_dataframe,
        reference_dataframe,
    ) = extract_coefficients(
        pipeline,
        target,
    )

    return (
        metrics_dataframe,
        coefficient_dataframe,
        reference_dataframe,
        threshold_dataframe,
    )


# -------------------------------------------------------------------
# Write model outputs to DuckDB
# -------------------------------------------------------------------

def write_outputs(
    metrics: pd.DataFrame,
    coefficients: pd.DataFrame,
    references: pd.DataFrame,
    threshold_metrics: pd.DataFrame,
) -> None:
    """Write all model outputs to the warehouse."""

    connection = duckdb.connect(
        str(WAREHOUSE)
    )

    try:
        connection.execute(
            """
            create schema
            if not exists model_output
            """
        )

        connection.register(
            "metrics_dataframe",
            metrics,
        )

        connection.register(
            "coefficients_dataframe",
            coefficients,
        )

        connection.register(
            "references_dataframe",
            references,
        )

        connection.register(
            "threshold_dataframe",
            threshold_metrics,
        )

        connection.execute(
            """
            create or replace table
                model_output.model_metrics
            as
            select *
            from metrics_dataframe
            """
        )

        connection.execute(
            """
            create or replace table
                model_output.feature_importance
            as
            select *
            from coefficients_dataframe
            """
        )

        connection.execute(
            """
            create or replace table
                model_output.reference_categories
            as
            select *
            from references_dataframe
            """
        )

        connection.execute(
            """
            create or replace table
                model_output.threshold_metrics
            as
            select *
            from threshold_dataframe
            """
        )

    finally:
        connection.close()

    print(
        "Wrote model outputs to the "
        "model_output schema."
    )


# -------------------------------------------------------------------
# Run the complete workflow
# -------------------------------------------------------------------

def main() -> None:
    """Train both prediction models."""

    feature_data = load_features()

    (
        training_data,
        validation_data,
        test_data,
        validation_start_date,
        test_start_date,
    ) = split_chronologically(
        feature_data
    )

    print(
        f"Feature rows: "
        f"{len(feature_data):,}"
    )

    print(
        f"Training rows: "
        f"{len(training_data):,}"
    )

    print(
        f"Validation rows: "
        f"{len(validation_data):,}"
    )

    print(
        f"Test rows: "
        f"{len(test_data):,}"
    )

    print(
        "Validation period starts: "
        f"{validation_start_date.date()}"
    )

    print(
        "Test period starts: "
        f"{test_start_date.date()}"
    )

    metric_results = []
    coefficient_results = []
    reference_results = []
    threshold_results = []

    for target in TARGET_COLUMNS:
        (
            metrics,
            coefficients,
            references,
            thresholds,
        ) = train_target(
            training_data,
            validation_data,
            test_data,
            target,
            validation_start_date,
            test_start_date,
        )

        metric_results.append(metrics)
        coefficient_results.append(
            coefficients
        )
        reference_results.append(
            references
        )
        threshold_results.append(
            thresholds
        )

        result = metrics.iloc[0]

        print(f"\nTarget: {target}")

        print(
            "Selected threshold: "
            f"{result['prediction_threshold']:.2f}"
        )

        print(
            "Test ROC AUC: "
            f"{result['roc_auc']:.3f}"
        )

        print(
            "Test precision: "
            f"{result['precision']:.3f}"
        )

        print(
            "Test recall: "
            f"{result['recall']:.3f}"
        )

        print(
            "Test F1 score: "
            f"{result['f1_score']:.3f}"
        )

    write_outputs(
        metrics=pd.concat(
            metric_results,
            ignore_index=True,
        ),
        coefficients=pd.concat(
            coefficient_results,
            ignore_index=True,
        ),
        references=pd.concat(
            reference_results,
            ignore_index=True,
        ),
        threshold_metrics=pd.concat(
            threshold_results,
            ignore_index=True,
        ),
    )


if __name__ == "__main__":
    main()