"""Build El Niño labels from the monthly ONI series.

Rules are in specs/layer1-forecast.md, section 3.
Run from backend/:  python -m app.layer1_forecast.labels   (prints the events table)
"""

import numpy as np
import pandas as pd

from app.data.load_enso import OUTPUT_PATH as ENSO_MONTHLY_PATH

EL_NINO_THRESHOLD = 0.5
LA_NINA_THRESHOLD = -0.5
MIN_EVENT_MONTHS = 5  # NOAA's five consecutive overlapping three-month seasons

# Strength from the event's peak ONI. A common convention, not official NOAA categories.
MODERATE_FROM = 1.0
STRONG_FROM = 1.5


def month_status(oni: pd.Series) -> pd.Series:
    """Return "El Nino", "Neutral", or "La Nina" for each month."""
    status = np.select(
        [oni >= EL_NINO_THRESHOLD, oni <= LA_NINA_THRESHOLD],
        ["El Nino", "La Nina"],
        default="Neutral",
    )
    return pd.Series(status, index=oni.index, name="status")


def strength_from_peak(peak_oni: float) -> str:
    """Weak below 1.0, moderate from 1.0 to below 1.5, strong from 1.5."""
    if peak_oni >= STRONG_FROM:
        return "strong"
    if peak_oni >= MODERATE_FROM:
        return "moderate"
    return "weak"


def find_events(table: pd.DataFrame) -> pd.DataFrame:
    """Find El Niño events: at least MIN_EVENT_MONTHS months in a row with ONI >= +0.5.

    `table` needs columns `date` (first day of each month) and `oni`.
    Returns one row per event. An event that reaches the last month of data is
    "ongoing": its end_month is empty and its duration is only the months seen so far.
    """
    table = table.sort_values("date").reset_index(drop=True)
    warm = table["oni"] >= EL_NINO_THRESHOLD

    # Give every run of consecutive warm / not-warm months its own number:
    # the number goes up by one each time `warm` flips.
    run_number = (warm != warm.shift()).cumsum()
    last_date = table["date"].iloc[-1]

    events = []
    for _, run in table[warm].groupby(run_number[warm]):
        if len(run) < MIN_EVENT_MONTHS:
            continue  # too short to be an event (or not an event yet, at the end of the data)
        peak_row = run.loc[run["oni"].idxmax()]
        ongoing = run["date"].iloc[-1] == last_date
        events.append({
            "start_month": run["date"].iloc[0],
            "end_month": pd.NaT if ongoing else run["date"].iloc[-1],
            # Every month in the run is >= +0.5, so the duration is the run length.
            "duration_months": len(run),
            "peak_oni": peak_row["oni"],
            "peak_month": peak_row["date"],
            "strength": strength_from_peak(peak_row["oni"]),
            "ongoing": ongoing,
        })

    columns = ["start_month", "end_month", "duration_months", "peak_oni",
               "peak_month", "strength", "ongoing"]
    return pd.DataFrame(events, columns=columns)


def main() -> None:
    table = pd.read_csv(ENSO_MONTHLY_PATH, parse_dates=["date"])
    events = find_events(table)

    # Show dates as YYYY-MM for reading; an ongoing event has no end month.
    printable = events.copy()
    for col in ["start_month", "end_month", "peak_month"]:
        printable[col] = printable[col].dt.strftime("%Y-%m").fillna("-")
    print(printable.to_string(index=False))
    print(f"\n{len(events)} events, {events['ongoing'].sum()} ongoing")
    print("Months per status:")
    print(month_status(table["oni"]).value_counts().to_string())


if __name__ == "__main__":
    main()
