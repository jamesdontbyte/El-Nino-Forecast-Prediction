"""Does the province El Nino dryness input help the Layer 2 rain model? (specs/layer2-impact.md)

Baseline: the dense XGBoost rain model. Candidate: the same model and settings plus
`el_nino_dryness`. Both fitted on 1981-2008. The keep rule was fixed before this ran:
keep only if validation RMSE is lower overall, lower in El Nino quarters (ONI 1.0 or more),
and not higher in Q4.

Run from backend/:  PYTHONPATH=. .venv/Scripts/python.exe ../notebooks/08_rain_dryness_check.py
Only after the decision, score the test years once (fitted on 1981-2016):
                    PYTHONPATH=. .venv/Scripts/python.exe ../notebooks/08_rain_dryness_check.py score_test
"""

import sys

import numpy as np
import pandas as pd

from app.layer2 import models
from app.layer2.features import (
    DRYNESS,
    RAIN_CATEGORICAL,
    RAIN_NUMERIC,
    RAIN_TARGET,
    STRONG_ONI,
    el_nino_dryness,
    load_tables,
    split_by_year,
)

pd.set_option("display.width", 200)


def make_models() -> dict:
    return {
        "xgboost (baseline)": models.RAIN_MODELS["xgboost"](),
        "xgboost + dryness": models.pooled(models.xgboost(), RAIN_NUMERIC + [DRYNESS], RAIN_CATEGORICAL),
    }


def rmse(error: pd.Series) -> float:
    return float(np.sqrt((error ** 2).mean()))


def scores(fit_rows: pd.DataFrame, scored: pd.DataFrame) -> pd.DataFrame:
    """RMSE overall, in El Nino quarters, and per calendar quarter; MAE overall; prediction spread."""
    groups = {"all": scored["oni"].notna(), f"El Nino (ONI >= {STRONG_ONI})": scored["oni"] >= STRONG_ONI}
    groups |= {f"Q{q}": scored["quarter"] == q for q in [1, 2, 3, 4]}
    rows = []
    for name, model in make_models().items():
        predicted = pd.Series(model.fit(fit_rows, fit_rows[RAIN_TARGET]).predict(scored), index=scored.index)
        error = predicted - scored[RAIN_TARGET]
        row = {"model": name, "MAE all": error.abs().mean()}
        row |= {f"RMSE {group}": rmse(error[mask]) for group, mask in groups.items()}
        hot = groups[f"El Nino (ONI >= {STRONG_ONI})"]
        row["El Nino predicted std"] = float(predicted[hot].std())
        row["El Nino observed std"] = float(scored.loc[hot, RAIN_TARGET].std())
        rows.append(row)
    return pd.DataFrame(rows).set_index("model")


def decide(validation: pd.DataFrame) -> dict:
    base, new = validation.loc["xgboost (baseline)"], validation.loc["xgboost + dryness"]
    hot = f"RMSE El Nino (ONI >= {STRONG_ONI})"
    checks = {
        "lower overall": bool(new["RMSE all"] < base["RMSE all"]),
        "lower in El Nino quarters": bool(new[hot] < base[hot]),
        "not higher in Q4": bool(new["RMSE Q4"] <= base["RMSE Q4"]),
    }
    return checks | {"keep": all(checks.values())}


def main() -> None:
    rain = load_tables()["rain"]
    rain[DRYNESS] = el_nino_dryness(rain, rain)  # each row uses only years before its own
    splits = split_by_year(rain)
    train, validation = splits["train"], splits["validation"]
    print(f"Rows: train {len(train)}, validation {len(validation)}. "
          f"Empty dryness: train {train[DRYNESS].isna().mean():.0%}, validation {validation[DRYNESS].isna().mean():.0%}")
    print(f"Validation El Nino quarters: {sorted(set(zip(*validation.loc[validation['oni'] >= STRONG_ONI, ['year', 'quarter']].T.values)))}")

    scored = scores(train, validation)
    print("\nValidation 2009-2016, fitted on 1981-2008")
    print(scored.round(2).T.to_string())
    decision = decide(scored)
    print("\nDecision (validation only):", decision)

    if sys.argv[1:] == ["score_test"]:
        fit_rows = pd.concat([train, validation])
        print("\nTest 2017 on, fitted on 1981-2016. A second look at the test years (first in layer2/train.py).")
        print(scores(fit_rows, splits["test"]).round(2).T.to_string())


if __name__ == "__main__":
    main()
