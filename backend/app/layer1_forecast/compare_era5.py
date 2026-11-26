"""Compare the ONI models with and without ERA5 features (spec section 13). Saves nothing.

Order, so the test years cannot influence the choice:
1. Validation scores (fitted on train years) for every version below, on the same validation rows.
2. The fixed decision rule, on validation only (decide).
3. Only then the test scores (fitted on 1950 to 2016). train.py already scored the test
   years once, so this is a second look at them.

Run from backend/:  python -m app.layer1_forecast.compare_era5
The era5_tp_central check (validation only, no test scores):
                    python -m app.layer1_forecast.compare_era5 tp_check
"""

import sys

import pandas as pd

from app.data.load_era5 import add_anomalies
from app.layer1_forecast import models
from app.layer1_forecast.features import (
    ERA5_LAG_COLUMNS,
    LAG_COLUMNS,
    add_era5_lags,
    build_features,
    rows_before_test,
    split_by_date,
)

CHECK_FIRST_YEAR = 1979
EARLY_LEADS = [1, 2, 3]  # ERA5 must not be worse at these leads


def feature_versions(table: pd.DataFrame, era5: pd.DataFrame) -> dict[str, tuple[pd.DataFrame, list[str]]]:
    """Version name -> (rows, feature columns).

    oni_only uses the rows of the ERA5 version, so both are scored on the same rows.
    The 1979 versions are a check: ERA5 anomalies against 1979 to 2008 normals, and
    training anchors from 1979 on. oni_only_1979 shows how much the shorter training alone changes.
    """
    frame = build_features(table)
    with_era5 = add_era5_lags(frame, era5)
    era5_1979 = add_anomalies(
        era5[era5["date"].dt.year >= CHECK_FIRST_YEAR].reset_index(drop=True), base_first_year=CHECK_FIRST_YEAR
    )
    from_1979 = add_era5_lags(frame, era5_1979)
    era5_columns = LAG_COLUMNS + ERA5_LAG_COLUMNS
    return {
        "oni_only": (with_era5, LAG_COLUMNS),
        "oni_era5": (with_era5, era5_columns),
        "oni_only_1979": (from_1979, LAG_COLUMNS),
        "oni_era5_1979": (from_1979, era5_columns),
    }


def score_versions(versions: dict, test: bool = False) -> pd.DataFrame:
    """MAE and RMSE per lead for every version and regressor, plus persistence once.

    test=False: fit on train, score validation. test=True: fit on 1950 to 2016, score test.
    """
    parts, scored_dates = [], []
    for name, (frame, columns) in versions.items():
        splits = split_by_date(frame)
        if test:
            fit_rows, score_rows = rows_before_test(frame), splits["test"]
        else:
            fit_rows, score_rows = splits["train"], splits["validation"]
        scored_dates.append(list(score_rows["date"]))
        scores = models.run_validation(fit_rows, score_rows, columns)["regression"]
        if parts:
            scores = scores[scores["model"] != "persistence"]  # the same in every version
        parts.append(scores.assign(version=name))

    if any(dates != scored_dates[0] for dates in scored_dates):
        raise ValueError("The versions are not scored on the same rows.")
    return pd.concat(parts, ignore_index=True)


def decide(validation: pd.DataFrame) -> dict:
    """Fixed rule: keep ERA5 only if the best oni_era5 model has a lower mean validation RMSE
    than the best oni_only model and is not worse at leads 1 to 3. The 1979 versions are a check only.
    """
    regressors = validation[validation["model"].isin(models.REGRESSORS)]
    rmse = regressors.pivot_table(index=["version", "model"], columns="lead", values="rmse")
    mean = rmse.mean(axis=1)

    oni_best = mean["oni_only"].idxmin()
    era5_best = mean["oni_era5"].idxmin()
    lower_mean = mean[("oni_era5", era5_best)] < mean[("oni_only", oni_best)]
    early_ok = (rmse.loc[("oni_era5", era5_best), EARLY_LEADS] <= rmse.loc[("oni_only", oni_best), EARLY_LEADS]).all()
    return {
        "oni_best": oni_best,
        "oni_best_mean_rmse": float(mean[("oni_only", oni_best)]),
        "era5_best": era5_best,
        "era5_best_mean_rmse": float(mean[("oni_era5", era5_best)]),
        "lower_mean": bool(lower_mean),
        "not_worse_at_leads_1_to_3": bool(early_ok),
        "keep_era5": bool(lower_mean and early_ok),
    }


def tp_check(table: pd.DataFrame, era5: pd.DataFrame) -> dict:
    """Spec section 13: keep era5_tp_central only if it lowers the mean validation RMSE.

    Compares the best regressor with and without the tp lags. Validation only.
    """
    frame = add_era5_lags(build_features(table), era5)
    with_tp = LAG_COLUMNS + ERA5_LAG_COLUMNS
    without_tp = [column for column in with_tp if not column.startswith("era5_tp_central")]
    validation = score_versions({"with_tp": (frame, with_tp), "without_tp": (frame, without_tp)})
    regressors = validation[validation["model"].isin(models.REGRESSORS)]
    mean = regressors.groupby(["version", "model"])["rmse"].mean()
    best_with, best_without = mean["with_tp"].min(), mean["without_tp"].min()
    return {
        "validation": validation,
        "best_with_tp": (mean["with_tp"].idxmin(), float(best_with)),
        "best_without_tp": (mean["without_tp"].idxmin(), float(best_without)),
        "keep_tp": bool(best_with < best_without),
    }


def score_table(scores: pd.DataFrame, metric: str) -> pd.DataFrame:
    """Rows: version / model. Columns: leads 1 to 6 and their mean."""
    table = scores.pivot_table(index=["version", "model"], columns="lead", values=metric, sort=False)
    table["mean"] = table.mean(axis=1)
    return table


def main() -> None:
    table = models.load_enso_monthly()
    era5 = models.load_era5_monthly()
    if era5 is None:
        raise FileNotFoundError("No era5_monthly.csv. Run python -m app.data.load_era5 from backend/ first.")
    if sys.argv[1:] == ["tp_check"]:
        check = tp_check(table, era5)
        for metric in ["mae", "rmse"]:
            print(f"\nValidation {metric.upper()} by lead, with and without era5_tp_central")
            print(score_table(check["validation"], metric).round(3).to_string())
        print({key: value for key, value in check.items() if key != "validation"})
        return

    versions = feature_versions(table, era5)

    validation = score_versions(versions)
    print(f"Validation rows per lead: {validation.query('model == \"persistence\"')['rows'].tolist()}")
    for metric in ["mae", "rmse"]:
        print(f"\nValidation {metric.upper()} by lead (lower is better)")
        print(score_table(validation, metric).round(3).to_string())

    rmse = score_table(validation, "rmse")
    print("\nERA5 minus ONI-only validation RMSE (negative = ERA5 helps)")
    for model in models.REGRESSORS:
        print(f"  {model:18s}", (rmse.loc[("oni_era5", model)] - rmse.loc[("oni_only", model)]).round(3).to_dict())

    decision = decide(validation)  # fixed before any test score below exists
    print("\nDecision (validation only):", decision)

    test = score_versions({name: versions[name] for name in ("oni_only", "oni_era5")}, test=True)
    print("\nTest RMSE by lead, fitted on 1950 to 2016. Second look at the test years (first in train.py).")
    print(score_table(test, "rmse").round(3).to_string())
    print("\nTest MAE by lead")
    print(score_table(test, "mae").round(3).to_string())


if __name__ == "__main__":
    main()
