import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.forecast import forecast_mode
from app.layer1_forecast import models, train
from app.layer1_forecast.features import LAG_COLUMNS, LEADS, build_features
from main import app

SECTION_2_FIELDS = {
    "event_underway", "event_status", "start_month", "duration_months",
    "duration_open_ended", "strength", "forecast_series", "model_used",
}
YEAR_FIELDS = {"mode", "target_year", "note"}
CLIMATOLOGY_FIELDS = YEAR_FIELDS | {"model_used", "climatology"}


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


def save_small_model(directory, table, with_hindcast=True):
    fitted = models.fit_per_lead(models.REGRESSORS["linear_regression"], build_features(table))
    bundle = {
        "model_name": "linear_regression", "models": fitted, "rmse_by_lead": {h: 0.2 for h in LEADS},
        "lag_columns": LAG_COLUMNS, "leads": LEADS,
    }
    if with_hindcast:
        # The fixture starts in 2000, so hindcast models exist only for 2002 to 2018.
        bundle["hindcast_models"] = train.fit_hindcast_models(table, "linear_regression")
        bundle["hindcast_anchor_month"] = train.HINDCAST_ANCHOR_MONTH
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


# The fixture's newest month B is 2019-12, so B+6 is 2020-06.
def test_hindcast_year_returns_anchor_forecast_with_observed_oni(client, tmp_path, table):
    save_small_model(tmp_path, table)
    body = client.get("/api/forecast?year=2015").json()

    assert set(body) == SECTION_2_FIELDS | YEAR_FIELDS
    assert body["mode"] == "hindcast"
    assert body["target_year"] == 2015
    assert body["model_used"].endswith("(hindcast)")
    months = [month["month"] for month in body["forecast_series"]]
    assert months == [f"2015-{m:02d}" for m in range(4, 10)]
    observed = dict(zip(table["date"].dt.strftime("%Y-%m"), table["oni"]))
    for month in body["forecast_series"]:
        assert month["observed_oni"] == round(observed[month["month"]], 2)


def test_forecast_year_returns_normal_forecast_with_note(client, tmp_path, table):
    save_small_model(tmp_path, table)
    no_year = client.get("/api/forecast").json()
    body = client.get("/api/forecast?year=2020").json()

    assert set(body) == SECTION_2_FIELDS | YEAR_FIELDS
    assert body["mode"] == "forecast"
    assert {key: body[key] for key in SECTION_2_FIELDS} == no_year
    assert "2020-01 to 2020-06" in body["note"]


def test_climatology_year_returns_only_climatology_fields(client, tmp_path, table):
    save_small_model(tmp_path, table)
    body = client.get("/api/forecast?year=2050").json()

    assert set(body) == CLIMATOLOGY_FIELDS
    assert body["mode"] == "climatology"
    assert body["model_used"] == "climatology (no model)"
    assert len(body["climatology"]) == 12
    assert body["note"] == "Average of 2000 to 2018, not a forecast."


@pytest.mark.parametrize("year, mode", [
    (2018, "hindcast"), (2019, "forecast"), (2020, "forecast"), (2021, "climatology"),
])
def test_mode_boundary_years(client, tmp_path, table, year, mode):
    save_small_model(tmp_path, table)
    response = client.get(f"/api/forecast?year={year}")
    assert response.status_code == 200
    assert response.json()["mode"] == mode


@pytest.mark.parametrize("year", [1959, 2101])
def test_year_outside_limits_returns_422(client, year):
    assert client.get(f"/api/forecast?year={year}").status_code == 422


def test_forecast_mode_with_newest_month_in_june():
    # B+6 is December of B's year, so the next year is already climatology.
    june = pd.Timestamp("2026-06-01")
    assert forecast_mode(2025, june) == "hindcast"
    assert forecast_mode(2026, june) == "forecast"
    assert forecast_mode(2027, june) == "climatology"


def test_forecast_mode_with_newest_month_in_december():
    # B+6 is June of the next year, so the next year is still forecast.
    december = pd.Timestamp("2026-12-01")
    assert forecast_mode(2026, december) == "forecast"
    assert forecast_mode(2027, december) == "forecast"
    assert forecast_mode(2028, december) == "climatology"


def test_old_model_file_without_hindcast_models(client, tmp_path, table):
    save_small_model(tmp_path, table, with_hindcast=False)
    response = client.get("/api/forecast?year=2015")
    assert response.status_code == 503
    assert "app.layer1_forecast.train" in response.json()["detail"]
    assert client.get("/api/forecast").status_code == 200


def test_hindcast_year_missing_from_model_file_returns_503(client, tmp_path, table):
    save_small_model(tmp_path, table)
    response = client.get("/api/forecast?year=2001")  # too early for the fixture to fit
    assert response.status_code == 503
    assert "app.layer1_forecast.train" in response.json()["detail"]
