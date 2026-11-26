import numpy as np
import pandas as pd
import pytest
from fastapi.testclient import TestClient

from app.api.forecast import forecast_mode
from app.data.load_era5 import RAW_COLUMNS, add_anomalies
from app.layer1_forecast import models, train
from app.layer1_forecast.features import (
    LAG_AND_ERA5_COLUMNS,
    LAG_COLUMNS,
    LEADS,
    add_era5_lags,
    build_features,
)
from main import app

SECTION_2_FIELDS = {
    "event_underway", "event_status", "start_month", "duration_months",
    "duration_open_ended", "strength", "forecast_series", "model_used", "era5_used",
}
YEAR_FIELDS = {"mode", "target_year", "note"}
CLIMATOLOGY_FIELDS = YEAR_FIELDS | {"model_used", "climatology"}


@pytest.fixture
def table():
    t = np.arange(240)
    dates = pd.date_range("2000-01", periods=len(t), freq="MS")
    return pd.DataFrame({"date": dates, "oni": 2.0 * np.sin(2 * np.pi * t / 40)})


@pytest.fixture
def era5(table):
    """Made-up ERA5 table over the same months as `table`, with raw columns and anomalies."""
    noise = np.random.default_rng(0).normal(size=(len(table), len(RAW_COLUMNS)))
    raw = pd.DataFrame(noise, columns=RAW_COLUMNS).assign(date=table["date"])
    return add_anomalies(raw, base_first_year=2000)


@pytest.fixture
def client(monkeypatch, tmp_path, table):
    monkeypatch.setattr(train, "SAVED_MODELS_DIR", tmp_path)
    monkeypatch.setattr(models, "load_enso_monthly", lambda: table)
    monkeypatch.setattr(models, "load_era5_monthly", lambda: None)  # tests opt in to ERA5
    return TestClient(app)


def save_small_model(directory, table, with_hindcast=True, era5=None):
    """An ONI-only model file, or with `era5` an ERA5 model file with the ONI-only fallback.

    Band widths differ (ONI only 0.2, ERA5 0.3), so a response shows which version ran.
    """
    fit = models.REGRESSORS["linear_regression"]
    oni_only = {
        "model_name": "linear_regression", "models": models.fit_per_lead(fit, build_features(table)),
        "rmse_by_lead": {h: 0.2 for h in LEADS}, "lag_columns": LAG_COLUMNS,
    }
    if with_hindcast:
        # The fixture starts in 2000, so hindcast models exist only for 2002 to 2018.
        oni_only["hindcast_models"] = train.fit_hindcast_models(table, "linear_regression")
    bundle = {**oni_only, "leads": LEADS, "hindcast_anchor_month": train.HINDCAST_ANCHOR_MONTH}
    if era5 is not None:
        frame = add_era5_lags(build_features(table), era5)
        bundle.update({
            "models": models.fit_per_lead(fit, frame, columns=LAG_AND_ERA5_COLUMNS),
            "rmse_by_lead": {h: 0.3 for h in LEADS}, "lag_columns": LAG_AND_ERA5_COLUMNS,
            "hindcast_models": train.fit_hindcast_models(table, "linear_regression", era5),
            "uses_era5": True, "oni_only": oni_only,
        })
    train.save_model(bundle, {"model_name": "linear_regression"}, directory=directory)


def band_width(body):
    first = body["forecast_series"][0]
    return round(first["upper"] - first["oni"], 2)


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


def test_forecast_uses_era5_when_it_reaches_the_newest_month(client, monkeypatch, tmp_path, table, era5):
    save_small_model(tmp_path, table, era5=era5)
    monkeypatch.setattr(models, "load_era5_monthly", lambda: era5)
    body = client.get("/api/forecast").json()

    assert set(body) == SECTION_2_FIELDS
    assert body["era5_used"] is True
    assert band_width(body) == 0.3  # the ERA5 model's own band


@pytest.mark.parametrize("case", ["no_era5_file", "era5_older_than_oni", "empty_value"])
def test_forecast_falls_back_to_oni_only(client, monkeypatch, tmp_path, table, era5, case):
    save_small_model(tmp_path, table, era5=era5)
    if case == "era5_older_than_oni":
        era5 = era5[era5["date"] < pd.Timestamp("2019-12-01")]  # newest ONI month B is 2019-12
    if case == "empty_value":
        era5 = era5.copy()
        era5.loc[era5["date"] == pd.Timestamp("2019-10-01"), "era5_mslp_diff"] = np.nan  # lag 3 of B
    monkeypatch.setattr(models, "load_era5_monthly", lambda: None if case == "no_era5_file" else era5)
    body = client.get("/api/forecast").json()

    assert body["era5_used"] is False
    assert band_width(body) == 0.2  # the ONI-only model's own band
    save_small_model(tmp_path, table)  # an ONI-only model file gives exactly the same answer
    assert client.get("/api/forecast").json() == body


def test_hindcast_uses_era5(client, monkeypatch, tmp_path, table, era5):
    save_small_model(tmp_path, table, era5=era5)
    monkeypatch.setattr(models, "load_era5_monthly", lambda: era5)
    body = client.get("/api/forecast?year=2015").json()

    assert body["era5_used"] is True
    assert body["model_used"] == "linear_regression (hindcast)"
    assert band_width(body) == 0.3


def test_old_model_file_says_era5_not_used(client, monkeypatch, tmp_path, table, era5):
    save_small_model(tmp_path, table)  # no uses_era5 key, like files saved before ERA5
    monkeypatch.setattr(models, "load_era5_monthly", lambda: era5)
    assert client.get("/api/forecast").json()["era5_used"] is False


def test_api_reads_the_era5_csv_and_never_opens_netcdf(client, monkeypatch, tmp_path, table, era5):
    save_small_model(tmp_path, table, era5=era5)
    csv_path = tmp_path / "era5_monthly.csv"
    era5.to_csv(csv_path, index=False)
    monkeypatch.undo()  # back to the real load_era5_monthly, pointed at the made-up CSV
    monkeypatch.setattr(train, "SAVED_MODELS_DIR", tmp_path)
    monkeypatch.setattr(models, "load_enso_monthly", lambda: table)
    monkeypatch.setattr(models, "ERA5_MONTHLY_PATH", csv_path)

    def no_loader(*args, **kwargs):
        raise AssertionError("the API must not run the ERA5 loader")

    monkeypatch.setattr("xarray.open_dataset", no_loader)
    monkeypatch.setattr("app.data.load_era5.main", no_loader)
    assert client.get("/api/forecast").json()["era5_used"] is True
