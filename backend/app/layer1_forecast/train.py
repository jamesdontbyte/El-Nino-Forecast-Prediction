"""Choose, test, and save the ONI forecast model.

Order (so the test years cannot influence the choice):
1. Score every model on validation (fitted on 1950 to 2008).
2. Choose the model with the lowest mean validation RMSE across leads 1 to 6.
3. Score every model once on the test years (fitted on 1950 to 2016).
4. Refit the chosen model on all rows with known targets and save it.
5. Fit the chosen model once per hindcast year, on ONI up to March of that year, and save those too.
6. ERA5 (spec section 13): score ONI + ERA5 on validation and apply the fixed rule
   (compare_era5.decide). If kept, save the best ERA5 model as the live model, with its own
   hindcast models, and keep the ONI-only model in the bundle as the fallback. ERA5 test
   scores are not computed here (they were recorded once, in section 7).
   Needs data/processed/era5_monthly.csv (python -m app.data.load_era5); without it only ONI is saved.

Run from backend/:  python -m app.layer1_forecast.train
"""

import json
from datetime import date
from pathlib import Path

import joblib
import numpy as np
import pandas as pd

from app.data.load_era5 import FIRST_YEAR as ERA5_FIRST_YEAR
from app.data.load_era5 import add_anomalies
from app.layer1_forecast import compare_era5, models
from app.layer1_forecast.features import (
    LAG_AND_ERA5_COLUMNS,
    LAG_COLUMNS,
    LEADS,
    add_era5_lags,
    build_features,
    rows_before_test,
    split_by_date,
)
from app.layer1_forecast.labels import find_events

SAVED_MODELS_DIR = Path(__file__).resolve().parents[1] / "saved_models"
MODEL_FILE = "oni_forecast.joblib"
METADATA_FILE = "oni_forecast.json"
HINDCAST_FIRST_YEAR = 1960
HINDCAST_ANCHOR_MONTH = 3  # March


def hindcast_anchor(year: int) -> pd.Timestamp:
    return pd.Timestamp(year=year, month=HINDCAST_ANCHOR_MONTH, day=1)


def hindcast_era5(era5: pd.DataFrame, year: int) -> pd.DataFrame:
    """ERA5 anomalies for a hindcast year: normals from the years before it only (1950 to year - 1).

    The live 1950 to 2008 normals would use years after early hindcast years, a leak.
    """
    return add_anomalies(era5, base_first_year=ERA5_FIRST_YEAR, base_last_year=year - 1)


def fit_hindcast_models(table: pd.DataFrame, model_name: str, era5: pd.DataFrame | None = None) -> dict[int, dict]:
    """One set of per-lead models per hindcast year, fitted only on data up to that year's anchor.

    With `era5`, the models also use the ERA5 lags, with that year's own normals (hindcast_era5).
    """
    columns = LAG_COLUMNS if era5 is None else LAG_AND_ERA5_COLUMNS
    last_year = table["date"].max().year - 1
    hindcast_models = {}
    for year in range(HINDCAST_FIRST_YEAR, last_year + 1):
        anchor = hindcast_anchor(year)
        # Cutting the table at the anchor makes every target after it unknown, and fit_per_lead drops those rows.
        frame = build_features(table[table["date"] <= anchor])
        if frame[f"target_lead{max(LEADS)}"].isna().all():
            continue  # too little data before the anchor to fit every lead
        if era5 is not None:
            frame = add_era5_lags(frame, hindcast_era5(era5[era5["date"] <= anchor], year))
        hindcast_models[year] = models.fit_per_lead(models.REGRESSORS[model_name], frame, columns=columns)
    return hindcast_models


def fit_era5_version(table: pd.DataFrame, era5: pd.DataFrame) -> tuple[dict, dict | None]:
    """Apply the fixed ERA5 rule on validation. Returns (decision, ERA5 version or None if not kept).

    The ERA5 version is refitted on every row with known targets, like the ONI-only model,
    and its confidence band uses its own validation RMSE.
    """
    frame = add_era5_lags(build_features(table), era5)
    validation = compare_era5.score_versions(
        {"oni_only": (frame, LAG_COLUMNS), "oni_era5": (frame, LAG_AND_ERA5_COLUMNS)}
    )
    decision = compare_era5.decide(validation)
    if not decision["keep_era5"]:
        return decision, None

    name = decision["era5_best"]
    scores = validation[(validation["version"] == "oni_era5") & (validation["model"] == name)]
    return decision, {
        "model_name": name,
        "models": models.fit_per_lead(models.REGRESSORS[name], frame, columns=LAG_AND_ERA5_COLUMNS),
        "rmse_by_lead": dict(zip(scores["lead"], scores["rmse"], strict=True)),
        "lag_columns": LAG_AND_ERA5_COLUMNS,
        "hindcast_models": fit_hindcast_models(table, name, era5),
    }


def choose_best(validation_regression: pd.DataFrame) -> str:
    """Lowest mean validation RMSE across all leads. Reference rows (persistence) cannot win."""
    candidates = validation_regression[validation_regression["model"].isin(models.REGRESSORS)]
    return candidates.groupby("model")["rmse"].mean().idxmin()


def predictions_by_lead(models_by_lead: dict, frame: pd.DataFrame) -> pd.DataFrame:
    """One row per (lead, target month) with the predicted and actual ONI."""
    parts = []
    for lead in LEADS:
        parts.append(pd.DataFrame({
            "lead": lead,
            "target_month": frame["date"] + pd.DateOffset(months=lead),
            "predicted": models_by_lead[lead].predict(frame[LAG_COLUMNS]),
            "actual": frame[f"target_lead{lead}"].to_numpy(),
        }))
    return pd.concat(parts, ignore_index=True)


def month_difference(later: pd.Timestamp, earlier: pd.Timestamp) -> int:
    return (later.year - earlier.year) * 12 + later.month - earlier.month


def event_scores(observed: pd.DataFrame, predictions: pd.DataFrame, first_test_month) -> pd.DataFrame:
    """For each lead, which true test-period events the forecast series also shows as events.

    The lead-h forecast series is the prediction for every month, made h months earlier.
    A true event counts as detected when a predicted event overlaps it in time.
    Duration error is left empty for the ongoing event, whose final length is unknown.
    The series is not cut at the newest observed month: forecasts past it are real forecasts,
    and cutting them would hide the ongoing event at longer leads.
    """
    last_observed = observed["date"].max()
    true_events = find_events(observed)
    true_events = true_events[true_events["start_month"] >= pd.Timestamp(first_test_month)]

    rows = []
    for lead in sorted(predictions["lead"].unique()):
        series = predictions[predictions["lead"] == lead]
        series = series.rename(columns={"target_month": "date", "predicted": "oni"})[["date", "oni"]]
        predicted_events = find_events(series)
        predicted_end = predicted_events["end_month"].fillna(series["date"].max())

        for _, true in true_events.iterrows():
            true_end = last_observed if pd.isna(true["end_month"]) else true["end_month"]
            overlapping = predicted_events[
                (predicted_events["start_month"] <= true_end) & (predicted_end >= true["start_month"])
            ]
            row = {
                "lead": lead,
                "event_start": true["start_month"].strftime("%Y-%m"),
                "ongoing": bool(true["ongoing"]),
                "true_duration": int(true["duration_months"]),
                "detected": len(overlapping) > 0,
                "predicted_start": None,
                "start_error_months": np.nan,
                "duration_error_months": np.nan,
            }
            if row["detected"]:
                match = overlapping.iloc[0]
                row["predicted_start"] = match["start_month"].strftime("%Y-%m")
                row["start_error_months"] = month_difference(match["start_month"], true["start_month"])
                if not true["ongoing"]:
                    row["duration_error_months"] = int(match["duration_months"]) - row["true_duration"]
            rows.append(row)
    return pd.DataFrame(rows)


def event_summary(events: pd.DataFrame) -> pd.DataFrame:
    """Per lead: events detected, mean absolute start and duration error (months)."""
    return events.groupby("lead").agg(
        detected=("detected", "sum"),
        events=("detected", "size"),
        mean_abs_start_error=("start_error_months", lambda s: s.abs().mean()),
        mean_abs_duration_error=("duration_error_months", lambda s: s.abs().mean()),
    )


def run_comparison(table: pd.DataFrame) -> dict:
    """Validation scores, the chosen model, and the one-time test scores. Saves nothing."""
    frame = build_features(table)
    splits = split_by_date(frame)

    validation = models.run_validation(splits["train"], splits["validation"])
    best = choose_best(validation["regression"])  # decided before any test score exists
    best_scores = validation["regression"].query("model == @best")
    rmse_by_lead = dict(zip(best_scores["lead"], best_scores["rmse"], strict=True))

    fit_rows = rows_before_test(frame)  # 1950 to 2016
    test = models.run_validation(fit_rows, splits["test"])

    test_models = models.fit_per_lead(models.REGRESSORS[best], fit_rows)
    predictions = predictions_by_lead(test_models, splits["test"])
    first_test_month = splits["test"]["date"].min()
    events = event_scores(table, predictions, first_test_month)

    return {
        "frame": frame,
        "validation": validation,
        "best": best,
        "rmse_by_lead": rmse_by_lead,
        "test": test,
        "test_predictions": predictions,
        "events": events,
    }


def save_model(bundle: dict, metadata: dict, directory: Path = SAVED_MODELS_DIR) -> None:
    directory.mkdir(parents=True, exist_ok=True)
    joblib.dump(bundle, directory / MODEL_FILE)
    (directory / METADATA_FILE).write_text(json.dumps(metadata, indent=2), encoding="utf-8")


def load_model(directory: Path = SAVED_MODELS_DIR) -> dict:
    """Load the saved bundle. Only load files this project created (joblib can run code)."""
    return joblib.load(directory / MODEL_FILE)


def _rounded(by_lead: dict) -> dict:
    return {str(lead): round(float(value), 4) for lead, value in by_lead.items()}


def _per_lead(scores: pd.DataFrame, model: str, column: str) -> dict:
    part = scores[scores["model"] == model]
    return {str(lead): round(float(value), 4) for lead, value in zip(part["lead"], part[column], strict=True)}


def main() -> None:
    table = models.load_enso_monthly()
    results = run_comparison(table)
    best = results["best"]

    validation_mean = results["validation"]["regression"].groupby("model")["rmse"].mean()
    print("Validation mean RMSE (leads 1 to 6):")
    print(validation_mean.round(3).sort_values().to_string())
    print(f"\nChosen model: {best}")

    test_regression = results["test"]["regression"]
    print("\nTest RMSE by lead (models fitted on 1950 to 2016)")
    print(test_regression.pivot(index="model", columns="lead", values="rmse").round(3).to_string())
    print("\nTest rows scored per lead:", dict(zip(LEADS, test_regression.query("model == @best")["rows"], strict=True)))
    print("\nTest status accuracy by lead")
    print(results["test"]["status"].pivot(index="model", columns="lead", values="accuracy").round(3).to_string())
    print(f"\nEvent detection on the test years ({best})")
    print(event_summary(results["events"]).round(2).to_string())

    # Decision 2A: refit the chosen model on every row whose target is known (1950 to now).
    newest_month = table["date"].max().strftime("%Y-%m")
    oni_only = {
        "model_name": best,
        "models": models.fit_per_lead(models.REGRESSORS[best], results["frame"]),
        "rmse_by_lead": results["rmse_by_lead"],
        "lag_columns": LAG_COLUMNS,
        "hindcast_models": fit_hindcast_models(table, best),
    }

    era5 = models.load_era5_monthly()
    if era5 is None:
        print("\nNo era5_monthly.csv (run python -m app.data.load_era5). Saving the ONI-only model only.")
        decision, era5_version = None, None
    else:
        decision, era5_version = fit_era5_version(table, era5)
        print("\nERA5 decision (validation only):", decision)

    # The live model is the ERA5 version when kept; the ONI-only version is its fallback.
    bundle = {
        **(era5_version or oni_only),
        "uses_era5": era5_version is not None,
        "oni_only": oni_only if era5_version else None,
        "leads": LEADS,
        "newest_oni_month": newest_month,
        "hindcast_anchor_month": HINDCAST_ANCHOR_MONTH,
    }
    hindcast_years = sorted(bundle["hindcast_models"])
    metadata = {
        "model_name": best,
        "chosen_by": "lowest mean validation RMSE across leads 1 to 6 (validation 2009 to 2016)",
        "validation_mean_rmse": {m: round(float(v), 4) for m, v in validation_mean.items()},
        "rmse_by_lead_for_confidence_band": _rounded(bundle["rmse_by_lead"]),
        "uses_era5": bundle["uses_era5"],
        "era5_decision": decision,
        "oni_only_fallback": None if not era5_version else {
            "model_name": best, "rmse_by_lead_for_confidence_band": _rounded(oni_only["rmse_by_lead"]),
        },
        "era5_newest_month": None if era5 is None else era5["date"].max().strftime("%Y-%m"),
        "test_note": "Test scores describe the ONI-only model fitted on 1950 to 2016. The saved model is refitted "
                     "on all data. ERA5 test scores are in specs/layer1-forecast.md, section 7.",
        "test_mae_by_lead": _per_lead(test_regression, best, "mae"),
        "test_rmse_by_lead": _per_lead(test_regression, best, "rmse"),
        "final_fit": f"all anchor months with known targets, 1950-12 to {newest_month} data",
        "newest_oni_month": newest_month,
        "hindcast": {
            "years": f"{hindcast_years[0]} to {hindcast_years[-1]}",
            "anchor_month": HINDCAST_ANCHOR_MONTH,
            "rule": "fitted only on data up to March of the target year; ERA5 normals from the years before it",
        },
        "created": date.today().isoformat(),
    }
    save_model(bundle, metadata)
    print(f"\nSaved {SAVED_MODELS_DIR / MODEL_FILE}")
    print(f"Saved {SAVED_MODELS_DIR / METADATA_FILE}")


if __name__ == "__main__":
    main()
