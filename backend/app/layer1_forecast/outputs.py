"""Turn a 6-month ONI forecast into the fields the API returns (layer1 spec, section 2).

The functions do not depend on which model made the forecast. They take the observed
ONI table, the forecast values, and the validation RMSE per lead.

Run from backend/:  python -m app.layer1_forecast.outputs   (demo with linear regression)
"""

import json

import pandas as pd

from app.layer1_forecast.features import (
    LAG_COLUMNS,
    LEADS,
    build_features,
    split_by_date,
)
from app.layer1_forecast.labels import (
    EL_NINO_THRESHOLD,
    find_events,
    month_status,
    strength_from_peak,
)


def confidence_band(anchor_month: pd.Timestamp, forecast_oni, rmse_by_lead: dict) -> pd.DataFrame:
    """Forecast ONI plus or minus the validation RMSE at each lead.

    `forecast_oni[i]` is the forecast for lead i + 1, the month anchor_month + i + 1.
    """
    rows = []
    for lead, oni in zip(LEADS, forecast_oni, strict=True):
        rmse = rmse_by_lead[lead]
        rows.append({
            "month": anchor_month + pd.DateOffset(months=lead),
            "oni": float(oni),
            "lower": float(oni) - rmse,
            "upper": float(oni) + rmse,
        })
    return pd.DataFrame(rows)


def leading_warm_months(values) -> int:
    """How many values in a row, from the first one, are at +0.5 or above."""
    count = 0
    for value in values:
        if value < EL_NINO_THRESHOLD:
            break
        count += 1
    return count


def duration_text(low: int, high: int, open_ended: bool) -> str:
    if open_ended and low == high:
        return f"at least {high} months"
    if open_ended:
        return f"from {low} months to at least {high} months"
    if low == high:
        return f"{low} months"
    return f"from {low} to {high} months"


def _month_text(date) -> str | None:
    return None if pd.isna(date) else pd.Timestamp(date).strftime("%Y-%m")


def build_outputs(observed: pd.DataFrame, band: pd.DataFrame, model_used: str) -> dict:
    """Build the API fields from observed ONI (`date`, `oni`) and the forecast band."""
    observed = observed.sort_values("date").reset_index(drop=True)
    last_observed = observed["date"].iloc[-1]
    forecast_months = len(band)

    observed_events = find_events(observed)
    underway = bool(len(observed_events) and observed_events["ongoing"].iloc[-1])

    start_month = None
    strength = None
    duration = None
    open_ended = False

    if underway:
        event = observed_events.iloc[-1]
        start_month = event["start_month"]
        # The event continues as long as the central forecast stays at +0.5 or above.
        central_run = band["oni"].iloc[: leading_warm_months(band["oni"])]
        peak = max([event["peak_oni"], *central_run])
        strength = strength_from_peak(peak)

        observed_months = int(event["duration_months"])
        low = observed_months + leading_warm_months(band["lower"])
        high = observed_months + leading_warm_months(band["upper"])
        open_ended = leading_warm_months(band["upper"]) == forecast_months
        duration = {"low": low, "high": high, "text": duration_text(low, high, open_ended)}
    else:
        # A predicted event must pass the same 5-month rule, counting observed and forecast months.
        combined = pd.concat(
            [observed[["date", "oni"]], band[["month", "oni"]].rename(columns={"month": "date"})],
            ignore_index=True,
        )
        events = find_events(combined)
        reaches_forecast = events["ongoing"] | (events["end_month"] > last_observed)
        predicted = events[reaches_forecast]
        if len(predicted):
            event = predicted.iloc[0]
            start_month = event["start_month"]
            strength = event["strength"]

    return {
        "event_underway": underway,
        "event_status": month_status(band["oni"]).tolist(),
        "start_month": _month_text(start_month),
        "duration_months": duration,
        "duration_open_ended": open_ended,
        "strength": strength,
        "forecast_series": [
            {
                "month": _month_text(row.month),
                "oni": round(row.oni, 2),
                "lower": round(row.lower, 2),
                "upper": round(row.upper, 2),
            }
            for row in band.itertuples()
        ],
        "model_used": model_used,
    }


def main() -> None:
    """Demo only: linear regression fitted on train, RMSE from validation. Nothing is saved."""
    from app.layer1_forecast.models import (
        REGRESSORS,
        fit_per_lead,
        load_enso_monthly,
        regression_scores,
    )

    table = load_enso_monthly()
    frame = build_features(table)
    splits = split_by_date(frame)
    train, validation = splits["train"], splits["validation"]

    fitted = fit_per_lead(REGRESSORS["linear_regression"], train)
    scores = regression_scores(
        "linear_regression", lambda lead, x: fitted[lead].predict(x), validation
    )
    rmse_by_lead = dict(zip(scores["lead"], scores["rmse"], strict=True))

    # The newest row is the live forecast input. Its targets are unknown, so nothing is scored.
    latest = frame.iloc[[-1]]
    anchor = latest["date"].iloc[0]
    forecast = [fitted[lead].predict(latest[LAG_COLUMNS])[0] for lead in LEADS]
    band = confidence_band(anchor, forecast, rmse_by_lead)
    outputs = build_outputs(table[["date", "oni"]], band, "linear_regression (demo)")

    print(f"Anchor month B (newest ONI): {anchor:%Y-%m}\n")
    series = pd.DataFrame(outputs["forecast_series"])
    series["status"] = outputs["event_status"]
    series["rmse"] = [round(rmse_by_lead[lead], 3) for lead in LEADS]
    print("forecast_series")
    print(series.to_string(index=False))
    print()
    summary = {key: value for key, value in outputs.items() if key not in ("forecast_series", "event_status")}
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
