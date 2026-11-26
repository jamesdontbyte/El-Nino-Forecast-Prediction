import pandas as pd
import pytest

from app.layer1_forecast.compare_era5 import decide


def make_scores(oni_by_lead, era5_by_lead):
    """Validation RMSE per lead for linear regression in each version; other models score worse."""
    rows = []
    for version, by_lead in [("oni_only", oni_by_lead), ("oni_era5", era5_by_lead)]:
        for lead, rmse in enumerate(by_lead, start=1):
            rows.append({"version": version, "model": "linear_regression", "lead": lead, "rmse": rmse})
            rows.append({"version": version, "model": "xgboost", "lead": lead, "rmse": rmse + 1})
    rows.append({"version": "oni_only", "model": "persistence", "lead": 1, "rmse": 0.0})  # cannot win
    return pd.DataFrame(rows)


ONI = [0.1, 0.3, 0.4, 0.6, 0.7, 0.8]


@pytest.mark.parametrize(
    ("era5", "keep"),
    [
        ([0.1, 0.2, 0.4, 0.5, 0.6, 0.7], True),  # lower mean, ties at lead 1 and 3 count as not worse
        ([0.1, 0.31, 0.3, 0.4, 0.5, 0.6], False),  # lower mean, but worse at lead 2
        ([0.1, 0.3, 0.4, 0.6, 0.7, 0.8], False),  # same mean is not lower
        ([0.1, 0.3, 0.4, 0.7, 0.8, 0.9], False),  # better nowhere, worse later
    ],
)
def test_decision_rule(era5, keep):
    decision = decide(make_scores(ONI, era5))
    assert decision["oni_best"] == "linear_regression"
    assert decision["keep_era5"] is keep
