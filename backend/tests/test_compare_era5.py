import pandas as pd
import pytest

from app.layer1_forecast import compare_era5
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


@pytest.mark.parametrize(("with_tp", "without_tp", "keep"), [(0.40, 0.45, True), (0.45, 0.45, False), (0.50, 0.45, False)])
def test_tp_check_keeps_tp_only_if_it_lowers_the_mean(monkeypatch, with_tp, without_tp, keep):
    def fake_scores(versions):
        rows = []
        for version, rmse in [("with_tp", with_tp), ("without_tp", without_tp)]:
            rows += [{"version": version, "model": "linear_regression", "lead": h, "rmse": rmse} for h in range(1, 7)]
        return pd.DataFrame(rows)

    monkeypatch.setattr(compare_era5, "score_versions", fake_scores)
    monkeypatch.setattr(compare_era5, "add_era5_lags", lambda frame, era5: frame)
    monkeypatch.setattr(compare_era5, "build_features", lambda table: table)
    assert compare_era5.tp_check(pd.DataFrame(), pd.DataFrame())["keep_tp"] is keep
