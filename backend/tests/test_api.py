import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.layer1_forecast import models, train
from app.layer1_forecast.features import LAG_COLUMNS, LEADS, build_features
from main import app

SECTION_2_FIELDS = {
    "event_underway", "event_status", "start_month", "duration_months",
    "duration_open_ended", "strength", "forecast_series", "model_used",
}


@pytest.fixture
def table():
    t = np.arange(240)
    dates = pd.date_range("2000-01", periods=len(t), freq="MS")
    return pd.DataFrame({"date": dates, "oni": 2.0 * np.sin(2 * np.pi * t / 40)})


@pytest.fixture
def client(monkeypatch, tmp_path, table):
    monkeypatch.setattr(train, "SAVED_MODELS_DIR", tmp_path)
    monkeypatch.setattr(models, "load_enso_monthly", lambda: table)
    return TestClient(app)


def save_small_model(directory, table):
    fitted = models.fit_per_lead(models.REGRESSORS["linear_regression"], build_features(table))
    bundle = {
        "model_name": "linear_regression", "models": fitted, "rmse_by_lead": {h: 0.2 for h in LEADS},
        "lag_columns": LAG_COLUMNS, "leads": LEADS,
    }
    train.save_model(bundle, {"model_name": "linear_regression"}, directory=directory)


def test_forecast_returns_every_section_2_field(client, tmp_path, table):
    save_small_model(tmp_path, table)
    response = client.get("/api/forecast")

    assert response.status_code == 200
    body = response.json()
    assert set(body) == SECTION_2_FIELDS
    assert body["model_used"] == "linear_regression"
    assert len(body["forecast_series"]) == 6
    assert len(body["event_status"]) == 6
    for month in body["forecast_series"]:
        assert month["lower"] <= month["oni"] <= month["upper"]
    # The first forecast month is the month after the newest ONI month.
    assert body["forecast_series"][0]["month"] == "2020-01"


def test_forecast_without_saved_model_returns_503(client):
    response = client.get("/api/forecast")
    assert response.status_code == 503
    assert "app.layer1_forecast.train" in response.json()["detail"]


def test_health_still_ok(client):
    assert client.get("/health").json() == {"status": "ok"}
