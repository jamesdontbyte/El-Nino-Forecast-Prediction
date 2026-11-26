"""Layer 2 models for both steps, scored with MAE and RMSE.

Step 1 (rainfall): ONI -> rainfall percent of normal for each province and quarter.
Step 2 (yield): rainfall percent and ONI -> yield change for each province, crop and quarter.

Every model in a step is scored on the same rows. Each step also has a reference row with
no model (always normal: 100 percent rainfall, 0 percent yield change) to beat.

Run from backend/:  python -m app.layer2.models   (prints the validation tables)
"""

import numpy as np
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.ensemble import RandomForestRegressor
from sklearn.linear_model import LinearRegression
from sklearn.metrics import mean_absolute_error, mean_squared_error
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder
from xgboost import XGBRegressor

from app.layer2.features import (
    RAIN_CATEGORICAL,
    RAIN_NUMERIC,
    RAIN_TARGET,
    YIELD_CATEGORICAL,
    YIELD_NUMERIC,
    YIELD_TARGET,
    load_tables,
    split_by_year,
)

RANDOM_STATE = 42  # same results on every run
RAIN_REFERENCE = 100.0  # "always normal rainfall"
YIELD_REFERENCE = 0.0  # "always normal yield"


class ProvinceLine:
    """Rainfall baseline: one straight line per province and quarter, rain % = a + b x ONI.

    Each line's slope b says how strongly that province's rainfall in that quarter follows ONI.
    """

    def fit(self, features: pd.DataFrame, target: pd.Series) -> "ProvinceLine":
        rows = features.assign(target=target.to_numpy())
        lines = []
        for (pcode, quarter), group in rows.groupby(["pcode", "quarter"]):
            slope, intercept = np.polyfit(group["oni"], group["target"], 1)
            lines.append({"pcode": pcode, "quarter": quarter, "slope": slope, "intercept": intercept})
        self.lines = pd.DataFrame(lines)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        rows = features[["pcode", "quarter", "oni"]].merge(
            self.lines, on=["pcode", "quarter"], how="left", validate="many_to_one")
        if rows["slope"].isna().any():
            raise ValueError("No fitted line for some province and quarter.")
        return (rows["intercept"] + rows["slope"] * rows["oni"]).to_numpy()


class DepartureLine:
    """Yield model: a straight line through departures from normal, with no intercept.

    Rain columns become (rain % - 100) and ONI stays as it is (its normal is 0), so a normal
    quarter always predicts 0 percent. With no intercept it cannot learn a fixed level from the
    training years, which pushed the other models too high (1997 to 2008 sat above their normal).
    """

    def __init__(self, numeric: list[str] = YIELD_NUMERIC):
        self.numeric = numeric

    def _departures(self, features: pd.DataFrame) -> pd.DataFrame:
        departures = features[self.numeric].astype(float)
        rain_columns = [c for c in self.numeric if c.startswith("rain")]
        departures[rain_columns] -= RAIN_REFERENCE
        return departures

    def fit(self, features: pd.DataFrame, target: pd.Series) -> "DepartureLine":
        self.model = LinearRegression(fit_intercept=False).fit(self._departures(features), target)
        return self

    def predict(self, features: pd.DataFrame) -> np.ndarray:
        return self.model.predict(self._departures(features))


def pooled(regressor, numeric: list[str], categorical: list[str]) -> Pipeline:
    """One model for all rows. Categories (province, quarter, crop) become 0/1 columns.

    The output is dense: in a sparse matrix XGBoost reads a stored 0.0 (for example ONI 0.0) as missing.
    """
    columns = ColumnTransformer([
        ("categories", OneHotEncoder(handle_unknown="ignore"), categorical),
        ("numbers", "passthrough", numeric),
    ], sparse_threshold=0)
    return Pipeline([("columns", columns), ("model", regressor)])


def random_forest() -> RandomForestRegressor:
    return RandomForestRegressor(n_estimators=300, min_samples_leaf=5, n_jobs=-1, random_state=RANDOM_STATE)


def xgboost() -> XGBRegressor:
    return XGBRegressor(n_estimators=300, max_depth=3, learning_rate=0.05, random_state=RANDOM_STATE)


# Fixed settings, no tuning (same as Layer 1).
RAIN_MODELS = {
    "province_line": lambda: ProvinceLine(),
    "random_forest": lambda: pooled(random_forest(), RAIN_NUMERIC, RAIN_CATEGORICAL),
    "xgboost": lambda: pooled(xgboost(), RAIN_NUMERIC, RAIN_CATEGORICAL),
}

# `numeric` can be narrowed to this quarter's inputs for the lag check.
YIELD_MODELS = {
    "linear_regression": lambda numeric=YIELD_NUMERIC: pooled(LinearRegression(), numeric, YIELD_CATEGORICAL),
    "random_forest": lambda numeric=YIELD_NUMERIC: pooled(random_forest(), numeric, YIELD_CATEGORICAL),
    "xgboost": lambda numeric=YIELD_NUMERIC: pooled(xgboost(), numeric, YIELD_CATEGORICAL),
    # Added after the first comparison: the only yield model that beat the reference on validation.
    "departure_line": lambda numeric=YIELD_NUMERIC: DepartureLine(numeric),
}


def score(name: str, actual: pd.Series, predicted) -> dict:
    return {
        "model": name,
        "rows": len(actual),
        "mae": mean_absolute_error(actual, predicted),
        "rmse": float(np.sqrt(mean_squared_error(actual, predicted))),
    }


def compare(models: dict, train: pd.DataFrame, scored: pd.DataFrame, target: str,
            reference: float) -> tuple[pd.DataFrame, dict]:
    """Fit every model on `train`, score on `scored`. Returns the score table and fitted models."""
    rows = [score("reference_normal", scored[target], np.full(len(scored), reference))]
    fitted = {}
    for name, make_model in models.items():
        fitted[name] = make_model().fit(train, train[target])
        rows.append(score(name, scored[target], fitted[name].predict(scored)))
    scores = pd.DataFrame(rows)
    if scores["rows"].nunique() != 1:
        raise ValueError("Models were scored on different rows.")
    return scores, fitted


def choose_best(scores: pd.DataFrame, models: dict) -> str:
    """Lowest validation RMSE. The reference row cannot win."""
    candidates = scores[scores["model"].isin(models)]
    return candidates.set_index("model")["rmse"].idxmin()


def main() -> None:
    tables = load_tables()
    for step, models, target, reference in [
        ("rain", RAIN_MODELS, RAIN_TARGET, RAIN_REFERENCE),
        ("yield", YIELD_MODELS, YIELD_TARGET, YIELD_REFERENCE),
    ]:
        splits = split_by_year(tables[step])  # the test split is never used here
        scores, _ = compare(models, splits["train"], splits["validation"], target, reference)
        print(f"\nStep {step}: validation scores (lower is better)")
        print(scores.round(3).to_string(index=False))


if __name__ == "__main__":
    main()
