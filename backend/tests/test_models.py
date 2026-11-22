import numpy as np
import pandas as pd
import pytest

from app.layer1_forecast import models
from app.layer1_forecast.features import LEADS, build_features


def make_table(oni_values, start="2000-01"):
    dates = pd.date_range(start, periods=len(oni_values), freq="MS")
    return pd.DataFrame({"date": dates, "oni": oni_values})


def wave_frame(months=240, start="2000-01"):
    """Made-up ONI that swings between about -2 and +2, so all three statuses appear."""
    t = np.arange(months)
    oni = 2.0 * np.sin(2 * np.pi * t / 40) + 0.3 * np.sin(2 * np.pi * t / 7)
    return build_features(make_table(oni, start=start))


def test_linear_regression_fits_an_exact_linear_series():
    # ONI = row number, so every target is lag1 + lead: an exact linear rule.
    frame = build_features(make_table([float(i) for i in range(80)]))
    train, validation = frame.iloc[:50], frame.iloc[50:62]

    fitted = models.fit_per_lead(models.REGRESSORS["linear_regression"], train)
    scores = models.regression_scores("lr", lambda lead, x: fitted[lead].predict(x), validation)

    assert scores["mae"].max() < 1e-6


def test_one_model_per_lead():
    fitted = models.fit_per_lead(models.REGRESSORS["linear_regression"], wave_frame())
    assert sorted(fitted) == LEADS


def test_persistence_error_equals_the_lead_on_a_counting_series():
    # ONI = row number, so predicting ONI(B) for B+h is off by exactly h.
    frame = build_features(make_table([float(i) for i in range(40)])).dropna()
    scores = models.regression_scores("persistence", lambda lead, x: x["oni_lag1"], frame)
    assert scores["mae"].tolist() == pytest.approx([float(h) for h in LEADS])


def test_most_common_status_uses_the_training_targets():
    frame = build_features(make_table([0.0] * 30 + [1.0] * 5))  # mostly neutral
    assert set(models.most_common_status(frame).values()) == {"Neutral"}


def test_run_validation_returns_every_model_and_lead():
    frame = wave_frame()
    results = models.run_validation(frame.iloc[:150], frame.iloc[150:])

    expected_regression = {"persistence", "linear_regression", "random_forest", "xgboost"}
    assert set(results["regression"]["model"]) == expected_regression
    assert set(results["status"]["model"]) == {"logistic_regression", "most_common_class"}
    assert len(results["regression"]) == len(expected_regression) * len(LEADS)
    assert sorted(results["confusion"]) == LEADS


class UntouchableSplit:
    """Stands in for the test split. Any use of it (reading, scoring, len) fails the test."""

    def __getattr__(self, name):
        raise AssertionError(f"models.py used the test split (attribute {name!r})")

    def __getitem__(self, key):
        raise AssertionError("models.py used the test split (indexing)")

    def __len__(self):
        raise AssertionError("models.py used the test split (len)")

    def __iter__(self):
        raise AssertionError("models.py used the test split (iteration)")


def test_main_never_loads_or_scores_the_test_split(monkeypatch, capsys):
    frame = wave_frame()
    fake_splits = {
        "train": frame.iloc[:150].reset_index(drop=True),
        "validation": frame.iloc[150:].reset_index(drop=True),
        "test": UntouchableSplit(),
    }
    monkeypatch.setattr(models, "load_enso_monthly", lambda: make_table([0.0] * 24))
    monkeypatch.setattr(models, "split_by_date", lambda _frame: fake_splits)

    models.main()  # raises AssertionError if the test split is touched in any way

    printed = capsys.readouterr().out
    assert f"validation rows: {len(fake_splits['validation'])}" in printed
