"""Is the red- or yellow-quarter gap between two crop types larger than normal variation?

Compares Irrigated Palay and Corn, each against Rainfed Palay.
Uses the same rows as the Layer 3 crop gap table (specs/layer3-simulation.md, section 4):
El Nino quarters by the 2-of-3-months rule, red or yellow by the PAGASA bands on observed rain.
Run from backend/:  PYTHONPATH=. .venv/Scripts/python.exe ../notebooks/06_crop_gap_check.py
"""

import numpy as np
from scipy.stats import mannwhitneyu

from app.layer1_forecast.models import load_enso_monthly
from app.layer2.features import load_tables
from app.layer2.map_output import dryness_colour, quarter_phase

N_RESAMPLES = 10_000
SEED = 0
BASE_CROP = "Rainfed Palay"
STRONG_QUARTERS = {(1998, 1), (2016, 1)}


def colour_rows(colour):
    table = load_tables()["yield"].merge(quarter_phase(load_enso_monthly()), on=["year", "quarter"], how="left")
    table = table[table["phase"] == "El Nino"].copy()
    table["colour"] = table["rain_pct"].round(1).map(dryness_colour)
    return table[table["colour"] == colour]


def changes(rows, crop):
    return rows.loc[rows["crop_type"] == crop, "yield_change_pct"].to_numpy()


def row_bootstrap(crop_values, base_values, rng):
    """Resample rows within each crop type. Treats every province-quarter as independent."""
    gaps = [np.median(rng.choice(crop_values, crop_values.size)) - np.median(rng.choice(base_values, base_values.size))
            for _ in range(N_RESAMPLES)]
    return np.percentile(gaps, [2.5, 97.5])


def quarter_bootstrap(rows, crop, rng):
    """Resample whole quarters, because provinces in the same quarter share the same weather."""
    quarters = [group for _, group in rows.groupby(["year", "quarter"])]
    gaps = []
    for _ in range(N_RESAMPLES):
        picked = [quarters[i] for i in rng.integers(0, len(quarters), len(quarters))]
        crop_values = np.concatenate([changes(q, crop) for q in picked])
        base_values = np.concatenate([changes(q, BASE_CROP) for q in picked])
        if crop_values.size and base_values.size:
            gaps.append(np.median(crop_values) - np.median(base_values))
    return np.percentile(gaps, [2.5, 97.5])


def compare(rows, crop, label):
    rng = np.random.default_rng(SEED)
    crop_values, base_values = changes(rows, crop), changes(rows, BASE_CROP)
    low, high = row_bootstrap(crop_values, base_values, rng)
    q_low, q_high = quarter_bootstrap(rows, crop, rng)
    p_value = mannwhitneyu(crop_values, base_values, alternative="two-sided").pvalue
    n_quarters = rows.loc[rows["crop_type"] == crop, ["year", "quarter"]].drop_duplicates().shape[0]
    print(f"\n{crop} vs {BASE_CROP}, {label}")
    print(f"  rows: {crop} {crop_values.size}, {BASE_CROP} {base_values.size}, quarters {n_quarters}")
    print(f"  medians: {crop} {np.median(crop_values):.1f}%, {BASE_CROP} {np.median(base_values):.1f}%")
    print(f"  gap: {np.median(crop_values) - np.median(base_values):+.1f} points")
    print(f"  95% CI, row bootstrap:     {low:+.1f} to {high:+.1f}")
    print(f"  95% CI, quarter bootstrap: {q_low:+.1f} to {q_high:+.1f}")
    print(f"  Mann-Whitney p-value: {p_value:.4f}")


if __name__ == "__main__":
    for colour in ["red", "yellow"]:
        rows = colour_rows(colour)
        without_strong = rows[[(y, q) not in STRONG_QUARTERS for y, q in zip(rows["year"], rows["quarter"])]]
        for crop in ["Irrigated Palay", "Corn"]:
            compare(rows, crop, f"all {colour} El Nino quarters")
            compare(without_strong, crop, "without 1998 Q1 and 2016 Q1")
        if colour == "yellow":
            in_test = rows[rows["crop_type"].isin(["Irrigated Palay", "Corn", BASE_CROP])]
            counts = in_test.groupby(["year", "quarter", "crop_type"]).size().unstack(fill_value=0)
            counts["total"] = counts.sum(axis=1)
            print("\nYellow quarters with the most rows:")
            print(counts.sort_values("total", ascending=False).head(5).to_string())
            print(f"  yellow quarters in total: {len(counts)}")
