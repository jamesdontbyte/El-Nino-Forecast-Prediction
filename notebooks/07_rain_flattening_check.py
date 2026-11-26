"""Why does the Layer 2 rain model give almost every province the same rain at very high ONI?

Train and validation only; the test years are not scored. Changes nothing.
Run from backend/:  PYTHONPATH=. .venv/Scripts/python.exe ../notebooks/07_rain_flattening_check.py
"""

import joblib
import numpy as np
import pandas as pd

from app.layer2 import models
from app.layer2 import train as layer2_train
from app.layer2.features import RAIN_TARGET, load_tables, split_by_year

pd.set_option("display.width", 220)
FORECAST_INPUTS = {"2026 Q4": (4, 2.52, 2.14), "2027 Q1": (1, 1.95, 2.52)}  # quarter, oni, oni_prev

rain = load_tables()["rain"]
splits = split_by_year(rain)
train, validation = splits["train"], splits["validation"]
quarters = rain[["year", "quarter", "oni", "oni_prev"]].drop_duplicates()
provinces = sorted(rain["pcode"].unique())
print(f"Rain table: {len(rain)} rows, {len(provinces)} provinces, {quarters['year'].min()} to {quarters['year'].max()}")

# 1. How many past quarters reach the forecast's ONI level?
print("\n1. Past quarters by ONI level (each quarter has one row per province)")
for low in [1.0, 1.5, 1.8, 2.0]:
    for period, part in [("train 1981-2008", train), ("train+validation 1981-2016", pd.concat([train, validation]))]:
        q = part[["year", "quarter", "oni", "oni_prev"]].drop_duplicates()
        print(f"  ONI >= {low}: {period}: {int((q['oni'] >= low).sum())} quarters, "
              f"of which Q1: {int(((q['oni'] >= low) & (q['quarter'] == 1)).sum())}")
strong = quarters[(quarters["oni"] >= 1.5) | (quarters["oni_prev"] >= 1.5)].sort_values(["year", "quarter"])
print("  Every quarter with ONI or last quarter's ONI >= 1.5:")
print(strong.round(2).to_string(index=False))

# 2. Spread of predictions across provinces as ONI rises (model fitted on train, as in validation).
print("\n2. Spread of predicted rain across provinces (models fitted on 1981-2008)")
fitted = {name: models.RAIN_MODELS[name]().fit(train, train[RAIN_TARGET]) for name in ["xgboost", "province_line"]}
rows = []
for quarter in [1, 4]:
    # Not exactly 0: the one-hot columns make the input sparse, and XGBoost then reads ONI 0.0 as missing.
    for oni in [0.01, 0.5, 1.0, 1.5, 2.0, 2.5]:
        grid = pd.DataFrame({"pcode": provinces, "quarter": quarter, "oni": oni, "oni_prev": oni})
        for name, model in fitted.items():
            p = model.predict(grid)
            rows.append({"quarter": quarter, "oni=oni_prev": oni, "model": name, "mean": p.mean(), "std": p.std(),
                         "min": p.min(), "max": p.max(), "distinct (0.1)": len(np.unique(np.round(p, 1)))})
print(pd.DataFrame(rows).round(1).to_string(index=False))
for label, (quarter, oni, prev) in FORECAST_INPUTS.items():
    grid = pd.DataFrame({"pcode": provinces, "quarter": quarter, "oni": oni, "oni_prev": prev})
    for name, model in fitted.items():
        p = model.predict(grid)
        print(f"  {label} inputs (ONI {oni}, prev {prev}), {name}: mean {p.mean():.1f}, std {p.std():.1f}, "
              f"range {p.min():.1f} to {p.max():.1f}, most common value shared by "
              f"{pd.Series(np.round(p, 1)).value_counts().iloc[0]} of {len(p)}")

# 3. Where XGBoost splits: on ONI or on a province?
booster = fitted["xgboost"].named_steps["model"].get_booster()
names = fitted["xgboost"].named_steps["columns"].get_feature_names_out()
trees = booster.trees_to_dataframe()
splits_only = trees[trees["Feature"] != "Leaf"].copy()
splits_only["name"] = [names[int(f[1:])] for f in splits_only["Feature"]]
splits_only["kind"] = np.where(splits_only["name"].str.contains("pcode"), "province",
                      np.where(splits_only["name"].str.contains("quarter"), "quarter", "oni"))
print("\n3. XGBoost splits by feature kind (300 trees, depth 3):")
print(splits_only["kind"].value_counts().to_string())
print("  Total gain by kind (how much each kind reduces error):")
print(splits_only.groupby("kind")["Gain"].sum().round(0).to_string())

# 4. Do provinces differ in the same way from one strong El Nino to the next?
print("\n4. Observed province rain % in strong El Nino quarters (ONI >= 1.5), all years 1981-2016")
seen = pd.concat([train, validation])
hot = seen[seen["oni"] >= 1.5]
for (year, quarter), group in hot.groupby(["year", "quarter"]):
    r = group[RAIN_TARGET]
    print(f"  {year} Q{quarter} ONI {group['oni'].iloc[0]:.2f}: provinces {len(r)}, mean {r.mean():.0f}%, "
          f"std {r.std():.0f}, range {r.min():.0f} to {r.max():.0f}, below 40%: {(r < 40).sum()}")
for quarter in [1, 4]:
    events = hot[hot["quarter"] == quarter].pivot_table(index="pcode", columns="year", values=RAIN_TARGET)
    if events.shape[1] >= 2:
        corr = events.corr(method="spearman")
        pairs = corr.where(np.triu(np.ones(corr.shape, dtype=bool), 1)).stack().dropna()
        print(f"  Q{quarter}: rank correlation of provinces between strong events {list(events.columns)}: "
              + ", ".join(f"{a}-{b}: {v:.2f}" for (a, b), v in pairs.items()))

# 5. Validation errors per province (2009-2016), models fitted on 1981-2008.
print("\n5. Validation RMSE per province, 2009-2016")
per_province = []
for pcode, group in validation.groupby("pcode"):
    actual = group[RAIN_TARGET]
    row = {"pcode": pcode, "rows": len(group)}
    for name, model in fitted.items():
        row[name] = float(np.sqrt(((model.predict(group) - actual) ** 2).mean()))
    row["always_100"] = float(np.sqrt(((100 - actual) ** 2).mean()))
    per_province.append(row)
per_province = pd.DataFrame(per_province)
print(per_province[["xgboost", "province_line", "always_100"]].describe().round(1).to_string())
print(f"  Provinces where xgboost beats always-100: {(per_province['xgboost'] < per_province['always_100']).sum()} "
      f"of {len(per_province)}; where province_line beats xgboost: "
      f"{(per_province['province_line'] < per_province['xgboost']).sum()}")
print("  Worst 5 for xgboost:")
print(per_province.sort_values("xgboost", ascending=False).head(5).round(1).to_string(index=False))

# Validation El Nino quarters only (the 2015-16 event), where flattening would matter.
hot_val = validation[validation["oni"] >= 1.0]
print(f"\n  Validation quarters with ONI >= 1.0: {sorted(set(zip(hot_val['year'], hot_val['quarter'])))}")
for name, model in fitted.items():
    error = model.predict(hot_val) - hot_val[RAIN_TARGET]
    print(f"  {name}: RMSE {np.sqrt((error ** 2).mean()):.1f}, mean error {error.mean():+.1f} "
          f"(positive = predicted too wet), predicted std across rows {model.predict(hot_val).std():.1f}, "
          f"actual std {hot_val[RAIN_TARGET].std():.1f}")

# 6. Side finding: ONI exactly 0.0 is read as missing by the saved XGBoost rain model.


saved = joblib.load(layer2_train.SAVED_MODELS_DIR / layer2_train.RAIN_MODEL_FILE)["model"]
for oni in [0.0, 0.001]:
    one = pd.DataFrame({"pcode": [provinces[0]], "quarter": [1], "oni": [oni], "oni_prev": [oni]})
    print(f"\n6. Saved model, {provinces[0]} Q1, ONI = previous ONI = {oni}: {saved.predict(one)[0]:.1f}%")
print(f"   Quarters with ONI or last quarter's ONI exactly 0 so far: "
      f"{int(((quarters['oni'] == 0) | (quarters['oni_prev'] == 0)).sum())}")
