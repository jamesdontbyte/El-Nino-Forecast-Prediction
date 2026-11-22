"""Forecast models for ONI, scored on the validation split only.

One separate model per lead time (1 to 6 months). Every model uses the same lag
features from features.py. The test split is never used here; it stays untouched
until the final comparison.

Run from backend/:  python -m app.layer1_forecast.models   (prints the validation tables)
"""

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression, LogisticRegression
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    mean_absolute_error,
    mean_squared_error,
)
from xgboost import XGBRegressor

from app.data.load_enso import OUTPUT_PATH as ENSO_MONTHLY_PATH
from app.layer1_forecast.features import (
    LAG_COLUMNS,
    LEADS,
    build_features,
    split_by_date,
)
from app.layer1_forecast.labels import month_status

RANDOM_STATE = 42  # same results on every run
STATUS_ORDER = ["La Nina", "Neutral", "El Nino"]

# Models that predict the ONI value. Fixed settings, no tuning.
REGRESSORS = {
    "linear_regression": lambda: LinearRegression(),
    "random_forest": lambda: RandomForestRegressor(
        n_estimators=300, min_samples_leaf=5, random_state=RANDOM_STATE
    ),
    "xgboost": lambda: XGBRegressor(
        n_estimators=300, max_depth=3, learning_rate=0.05, random_state=RANDOM_STATE
    ),
}


def make_status_classifier() -> LogisticRegression:
    return LogisticRegression(max_iter=1000)


def lead_rows(frame: pd.DataFrame, lead: int) -> tuple[pd.DataFrame, pd.Series]:
    """Features and the lead's ONI target, without rows whose target is not observed yet."""
    target = frame[f"target_lead{lead}"]
    observed = target.notna()
    return frame.loc[observed, LAG_COLUMNS], target[observed]


def fit_per_lead(make_model, train: pd.DataFrame, as_status: bool = False) -> dict:
    """Fit one model per lead. With as_status=True the target is the El Nino / Neutral / La Nina label."""
    models = {}
    for lead in LEADS:
        features, target = lead_rows(train, lead)
        if as_status:
            target = month_status(target)
        models[lead] = make_model().fit(features, target)
    return models


def regression_scores(name: str, predict, validation: pd.DataFrame) -> pd.DataFrame:
    """MAE and RMSE per lead. `predict(lead, features)` returns predicted ONI values."""
    rows = []
    for lead in LEADS:
        features, target = lead_rows(validation, lead)
        predicted = predict(lead, features)
        rows.append({
            "model": name,
            "lead": lead,
            "rows": len(target),  # only rows whose target is observed
            "mae": mean_absolute_error(target, predicted),
            "rmse": np.sqrt(mean_squared_error(target, predicted)),
        })
    return pd.DataFrame(rows)


def status_scores(name: str, predict, validation: pd.DataFrame) -> tuple[pd.DataFrame, dict]:
    """Accuracy per lead, plus a confusion matrix per lead (rows = true, columns = predicted)."""
    rows, matrices = [], {}
    for lead in LEADS:
        features, target = lead_rows(validation, lead)
        true_status = month_status(target)
        predicted = predict(lead, features)
        rows.append({
            "model": name,
            "lead": lead,
            "rows": len(target),
            "accuracy": accuracy_score(true_status, predicted),
        })
        matrices[lead] = pd.DataFrame(
            confusion_matrix(true_status, predicted, labels=STATUS_ORDER),
            index=[f"true {s}" for s in STATUS_ORDER],
            columns=[f"pred {s}" for s in STATUS_ORDER],
        )
    return pd.DataFrame(rows), matrices


def most_common_status(train: pd.DataFrame) -> dict[int, str]:
    """The most common status in the training targets at each lead (no model is fitted)."""
    return {lead: month_status(lead_rows(train, lead)[1]).mode()[0] for lead in LEADS}


def run_validation(train: pd.DataFrame, validation: pd.DataFrame) -> dict:
    """Fit on train, score on validation. Returns the regression and status tables."""
    regression = [
        # Reference: no training. The forecast for B+h is the newest ONI, ONI(B).
        regression_scores("persistence", lambda lead, x: x["oni_lag1"], validation)
    ]
    for name, make_model in REGRESSORS.items():
        models = fit_per_lead(make_model, train)
        regression.append(regression_scores(name, lambda lead, x, m=models: m[lead].predict(x), validation))

    classifiers = fit_per_lead(make_status_classifier, train, as_status=True)
    logistic, logistic_matrices = status_scores(
        "logistic_regression", lambda lead, x: classifiers[lead].predict(x), validation
    )
    # Reference: always predict the most common training status.
    common = most_common_status(train)
    baseline, _ = status_scores(
        "most_common_class", lambda lead, x: np.full(len(x), common[lead]), validation
    )

    return {
        "regression": pd.concat(regression, ignore_index=True),
        "status": pd.concat([logistic, baseline], ignore_index=True),
        "confusion": logistic_matrices,
    }


def load_enso_monthly() -> pd.DataFrame:
    return pd.read_csv(ENSO_MONTHLY_PATH, parse_dates=["date"])


def main() -> None:
    splits = split_by_date(build_features(load_enso_monthly()))
    train, validation = splits["train"], splits["validation"]  # the test split is never used here
    results = run_validation(train, validation)

    regression = results["regression"]
    model_order = regression["model"].unique()
    for metric in ["mae", "rmse"]:
        table = regression.pivot(index="model", columns="lead", values=metric).loc[model_order]
        print(f"\nValidation {metric.upper()} by lead (months ahead), lower is better")
        print(table.round(3).to_string())

    status = results["status"]
    print("\nValidation status accuracy by lead, higher is better")
    print(status.pivot(index="model", columns="lead", values="accuracy").round(3).to_string())

    for lead, matrix in results["confusion"].items():
        print(f"\nLogistic regression confusion matrix, lead {lead}")
        print(matrix.to_string())

    print(f"\nTrain rows: {len(train)}, validation rows: {len(validation)}")


if __name__ == "__main__":
    main()
