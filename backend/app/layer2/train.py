"""Choose, test, and save the two Layer 2 models.

Order for each step (so the test years cannot influence the choice):
1. Score every model on validation (fitted on train: rainfall 1981 to 2008, yield 1997 to 2008).
2. Choose the model with the lowest validation RMSE.
3. Score every model once on the test years (fitted on everything up to 2016).
4. Refit the chosen model on all rows and save it.

The yield model is trained on observed rainfall, but the app gives it step 1's predicted
rainfall. So the chosen yield model is also scored with predicted rainfall: that is the
honest number for the app. A lag check scores it with this quarter's inputs only.

Saves layer2_rain.joblib, layer2_yield.joblib and layer2_models.json. The Layer 1 files
(oni_forecast.*) are never touched.

Run from backend/:  python -m app.layer2.train
"""

import json
from datetime import date

import joblib
import pandas as pd

from app.layer1_forecast.features import VALIDATION_LAST_YEAR
from app.layer1_forecast.train import SAVED_MODELS_DIR
from app.layer2 import models
from app.layer2.features import (
    RAIN_TARGET,
    YIELD_NUMERIC_THIS_QUARTER,
    YIELD_TARGET,
    add_previous_quarter,
    load_tables,
    split_by_year,
)

RAIN_MODEL_FILE = "layer2_rain.joblib"
YIELD_MODEL_FILE = "layer2_yield.joblib"
METADATA_FILE = "layer2_models.json"


def with_predicted_rain(yield_rows: pd.DataFrame, rain_table: pd.DataFrame, rain_model) -> pd.DataFrame:
    """Replace observed rainfall (this and last quarter) with step 1's predictions."""
    predicted = rain_table[["pcode", "year", "quarter"]].assign(rain_pct=rain_model.predict(rain_table))
    predicted = add_previous_quarter(predicted, "rain_pct", keys=["pcode"])
    rows = yield_rows.drop(columns=["rain_pct", "rain_pct_prev"]).merge(
        predicted, on=["pcode", "year", "quarter"], how="left", validate="many_to_one")
    if rows[["rain_pct", "rain_pct_prev"]].isna().any().any():
        raise ValueError("Some yield rows have no predicted rainfall.")
    return rows


def run_step(table: pd.DataFrame, models_by_name: dict, target: str, reference: float) -> dict:
    """Validation scores, the chosen model, and the one-time test scores for one step."""
    splits = split_by_year(table)
    validation, validation_models = models.compare(
        models_by_name, splits["train"], splits["validation"], target, reference)
    best = models.choose_best(validation, models_by_name)  # decided before any test score exists

    up_to_validation = table[table["year"] <= VALIDATION_LAST_YEAR]
    test, test_models = models.compare(models_by_name, up_to_validation, splits["test"], target, reference)
    return {
        "splits": splits, "validation": validation, "best": best,
        "validation_model": validation_models[best], "test": test, "test_model": test_models[best],
    }


def run_comparison(tables: dict) -> dict:
    """Both steps, plus the predicted-rainfall scores and the lag check. Saves nothing."""
    rain = run_step(tables["rain"], models.RAIN_MODELS, RAIN_TARGET, models.RAIN_REFERENCE)
    crop = run_step(tables["yield"], models.YIELD_MODELS, YIELD_TARGET, models.YIELD_REFERENCE)
    best_yield, splits = crop["best"], crop["splits"]

    # The app's chain: step 1 predicts rainfall, step 2 uses it. Same fit years as each score.
    chained = []
    for period, rain_model, yield_model in [
        ("validation", rain["validation_model"], crop["validation_model"]),
        ("test", rain["test_model"], crop["test_model"]),
    ]:
        rows = with_predicted_rain(splits[period], tables["rain"], rain_model)
        chained.append({"period": period, **models.score(best_yield, rows[YIELD_TARGET], yield_model.predict(rows))})

    # Lag check: the chosen yield model with this quarter's rainfall and ONI only.
    this_quarter = models.YIELD_MODELS[best_yield](YIELD_NUMERIC_THIS_QUARTER)
    this_quarter.fit(splits["train"], splits["train"][YIELD_TARGET])
    actual = splits["validation"][YIELD_TARGET]
    lag_check = pd.DataFrame([
        {"inputs": "this and last quarter",
         **models.score(best_yield, actual, crop["validation_model"].predict(splits["validation"]))},
        {"inputs": "this quarter only", **models.score(best_yield, actual, this_quarter.predict(splits["validation"]))},
    ])

    return {"rain": rain, "yield": crop, "chained": pd.DataFrame(chained), "lag_check": lag_check}


def _scores(table: pd.DataFrame) -> dict:
    return {row.model: {"rows": int(row.rows), "mae": round(float(row.mae), 3), "rmse": round(float(row.rmse), 3)}
            for row in table.itertuples()}


def _years(frame: pd.DataFrame) -> str:
    return f"{frame['year'].min()} to {frame['year'].max()}"


def main() -> None:
    tables = load_tables()
    results = run_comparison(tables)

    for step in ["rain", "yield"]:
        part = results[step]
        print(f"\nStep {step}: validation (fitted on {_years(part['splits']['train'])})")
        print(part["validation"].round(3).to_string(index=False))
        print(f"Chosen: {part['best']}")
        print(f"Step {step}: test (fitted up to {VALIDATION_LAST_YEAR})")
        print(part["test"].round(3).to_string(index=False))
    print("\nChosen yield model fed step 1's predicted rainfall (what the app does)")
    print(results["chained"].round(3).to_string(index=False))
    print("\nLag check on validation")
    print(results["lag_check"].round(3).to_string(index=False))

    # Refit each chosen model on all rows and save.
    rain_best, yield_best = results["rain"]["best"], results["yield"]["best"]
    final_rain = models.RAIN_MODELS[rain_best]().fit(tables["rain"], tables["rain"][RAIN_TARGET])
    final_yield = models.YIELD_MODELS[yield_best]().fit(tables["yield"], tables["yield"][YIELD_TARGET])
    SAVED_MODELS_DIR.mkdir(parents=True, exist_ok=True)
    joblib.dump({"model_name": rain_best, "model": final_rain}, SAVED_MODELS_DIR / RAIN_MODEL_FILE)
    joblib.dump({"model_name": yield_best, "model": final_yield}, SAVED_MODELS_DIR / YIELD_MODEL_FILE)

    metadata = {
        "rain_model": rain_best,
        "yield_model": yield_best,
        "chosen_by": "lowest validation RMSE (validation 2009 to 2016); the reference cannot win",
        "rain_training_years": _years(results["rain"]["splits"]["train"]),
        "yield_training_years": _years(results["yield"]["splits"]["train"]),
        "rain_validation": _scores(results["rain"]["validation"]),
        "yield_validation": _scores(results["yield"]["validation"]),
        "test_note": f"Test scores describe models fitted on data up to {VALIDATION_LAST_YEAR}. "
                     "The saved models are refitted on all rows.",
        "rain_test": _scores(results["rain"]["test"]),
        "yield_test": _scores(results["yield"]["test"]),
        "yield_with_predicted_rain": {
            row.period: {"mae": round(float(row.mae), 3), "rmse": round(float(row.rmse), 3)}
            for row in results["chained"].itertuples()
        },
        "lag_check_validation_rmse": {
            row.inputs: round(float(row.rmse), 3) for row in results["lag_check"].itertuples()
        },
        "final_fit": f"rain {_years(tables['rain'])}, yield {_years(tables['yield'])}",
        "created": date.today().isoformat(),
    }
    (SAVED_MODELS_DIR / METADATA_FILE).write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    for name in [RAIN_MODEL_FILE, YIELD_MODEL_FILE, METADATA_FILE]:
        print(f"Saved {SAVED_MODELS_DIR / name}")


if __name__ == "__main__":
    main()
