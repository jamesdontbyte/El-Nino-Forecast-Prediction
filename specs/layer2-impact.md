# Layer 2 Spec: Impact and Land View

**Status:** draft. The data, cleaning rules, normal yield, colours and models are decided (evidence in notebooks 03, 04 and 05). Items marked OPEN are not decided yet; they belong to the map output and API steps.

## 1. Purpose

Predict how El Niño changes rainfall and crop yield for the province and crop the user picks. Show the result on a map. Layer 3 starts from these results.

Yield change is measured against that province's own normal, not against other provinces.

## 2. Inputs and Outputs

**Input from the user:** a province and a crop. The user does not pick a date, horizon, or model.

**Input from the system:** the Layer 1 forecast. OPEN: how the forecast is turned into Layer 2 inputs.

**Crops:**

- Palay (rice): irrigated, rainfed, and total.
- Corn: white, yellow, and total.

**Outputs (exact fields to be decided):**

- Rainfall change for the province.
- Crop yield change for the province and crop, against the province's own normal.
- Map colours for the land view.

**Land view:**

- A flat 2D province map with a toggle between a normal year and the El Niño prediction.
- Colours show dryness: green healthy, yellow stressed, red severe.
- Provinces are coloured as whole shapes. There is no 25 km grid.
- The user can also compare a past El Niño year (for example 2015 or 2023).
- Shapes with no crop data are shown grey.
- OPEN: what the "normal year" map shows.
- **Dryness colours (decided):** based on rainfall percent of normal, using PAGASA's rainfall categories: 40% or less is way below normal, 41-80% is below normal, 81-120% is near normal, above 120% is above normal.
  - Map: red is 40% or less, yellow is 41-80%, green is above 80% (near normal and above normal are both not dry).
  - Yield change is shown as a number, not as a colour.
  - Source: PAGASA Dry Spell/Drought Assessment, 31 Dec 2023, https://pubfiles.pagasa.dost.gov.ph/pagasaweb/files/climate/dryspelldrought/DrySpell-Drought-assessment_outlook_31Dec2023.pdf. The same bands are on https://bagong.pagasa.dost.gov.ph/climate/climate-prediction/seasonal-forecast.
  - PAGASA's 2023 climatological publication writes "below 40%" instead of "40% or less". This only matters at exactly 40%.
  - Why rainfall: in notebook 04, El Niño quarters have median rainfall 72% of normal against 99% in neutral quarters, while same-quarter yield change differs by only 1 to 3 points. In the 2015-16 El Niño quarters, 361 of 567 province-quarters are yellow or red under these bands.

## 3. Data

All files are in `data/raw/philippines/`. The data folder is gitignored.

**PSA OpenSTAT crop tables:** `palay_areas.csv`, `palay_production.csv`, `corn_area.csv`, `corn_production.csv`.

- Crop types: Irrigated Palay, Rainfed Palay, and Palay (the total). White Corn, Yellow Corn, and Corn (the total).
- Semicolon separated, with a title line and a blank line before the header. Read with `sep=";"` and `skiprows=2`.
- 109 locations: PHILIPPINES, regions (two leading dots), and provinces and some cities (four leading dots). That is 327 rows per file.
- Columns for every quarter, semester, and annual value, 1987 to 2026. 2026 Quarter 4 is empty.
- Area is in hectares and production is in metric tons. Yield = production / area.
- Missing values are written "..". Many cells are 0.00. For palay area among province quarter cells: 1,356 zero and 2,455 missing. For corn area: 1,704 zero and 2,455 missing.

**CHIRPS rainfall:** `phl-rainfall-subnat-full.csv`.

- One row every ten days (a dekad), from 1981-01-01 to 2026-11-01.
- Columns: date, adm_level, adm_id, PCODE, n_pixels, rfh, rfh_avg, r1h, r1h_avg, r3h, r3h_avg, rfq, r1q, r3q, version.
- adm_level 1 is 17 regions. adm_level 2 is 81 provinces.
- Provinces are identified by PCODE (for example PH16068), not by name.
- `rfq` is the rainfall anomaly in percent of normal.
- `version` is "final" or "prelim". The 392 prelim rows are all from October and November 2026.

**Province shapes:** `regions/medres/provdists-region-*.json`, from the philippines-json-maps project.

- 18 files (one per region) with 88 shapes: 82 with geo_level "Prov", 4 NCR districts ("Dist"), City of Isabela, and "Special Geographic Area" (these last two have no geo_level).
- Properties: `adm1_psgc`, `adm2_psgc` (10-digit PSGC code), and `adm2_en` (name).

ERA5 is not used in Layer 2. It is only for Layer 1. Sentinel NDVI stays optional.

## 4. Matching the Sources

The three sources use different keys, so a hand-made lookup table links them. Columns: `crop_name`, `prov3`, `rain_pcode`, `map_psgc`, `note`.

- It lives in `backend/app/data/` and is committed. It is hand-made reference data, not downloaded data.
- The loading code checks that every crop province, CHIRPS PCODE, and shape is covered.

**The key:** the CHIRPS PCODE is "PH" plus the first 5 digits of the 10-digit PSGC code (2-digit region and 3-digit province part). Match on the 3-digit province part. All 81 CHIRPS provinces match a shape this way, and the 3-digit part is unique in both files.

**Mismatches to handle:**

- Four provinces changed region but keep the same 3-digit part: Negros Occidental (CHIRPS PH06045, shape PH18045), Negros Oriental (PH07046, PH18046), Siquijor (PH07061, PH18061), and Sulu (PH19066, PH09066).
- CHIRPS uses old boundaries (checked by comparing shape area with pixel count):
  - Maguindanao 087 covers both Maguindanao del Norte (087) and del Sur (088). There is no CHIRPS row for 088.
  - Davao del Sur 024 includes Davao Occidental (086). There is no CHIRPS row for 086.
  - NCR is one CHIRPS unit (074) but four shapes. NCR has no crop data.
- Shapes with no crop data are shown grey: the NCR districts, City of Isabela, and Special Geographic Area.
- Crop names that differ from shape names: "Cotabato (North Cotabato)" to "Cotabato", "Davao de Oro (Compostela Valley)" to "Davao de Oro", and "Tawi-tawi" to "Tawi-Tawi".
- Footnote marks (a/, b/, c/, d/) and leading dots must be stripped from crop names.

## 5. Cleaning Rules

Decided by the user.

- Use quarter columns only. Do not use semester or annual columns.
- **Negros Occidental, Negros Oriental, Siquijor:** the old row has 1987 to 2023. The footnoted row (a/ or b/, under Negros Island Region) has 2024 to 2025. Join them into one series. The years do not overlap.
- **Sulu:** the BARMM Sulu row has 1987 to 2025. The footnoted "Sulu c/" row under Region IX has numbers only in 2026 Quarters 1 to 3 (white corn 76, 117 and 114 ha; irrigated palay 5 ha in Quarter 3). The two rows never both have data in the same quarter. Join them into one Sulu series, like the Negros rows.
- **Maguindanao:** PSA keeps the old combined history under "Maguindanao del Sur" (1987 to 2025). "Maguindanao del Norte" only has 2024 to 2025. Merge del Norte into del Sur as one "Maguindanao" series, matched to CHIRPS PH19087. On the map, both shapes get the same colour.
- **Davao Occidental:** crop data is 2019 to 2025. Merge it into Davao del Sur, matched to CHIRPS PH11024. Both shapes get the same colour.
- **City rows** are added into their province: Bacolod City to Negros Occidental, Butuan City to Agusan del Norte, City of Davao to Davao del Sur, Puerto Princesa City to Palawan, Zamboanga City to Zamboanga del Sur. Sum area and production first, then compute yield.
- **City check:** for every quarter from 1987 to 2026 in all four tables, wherever a city has a number, province plus city equals the region total exactly. So adding never double-counts.
  - Davao City and Zamboanga City are 0.00 in 2021 to 2024. Bacolod, Butuan, and Puerto Princesa only have data in 2026 Quarters 1 to 3.
  - In those empty years the city appears to be counted inside its province. For example, Davao del Sur palay area is 29,803 ha in 2024, then 26,557 ha in 2025 when the city row returns with 2,804 ha.
  - This is an inference from the totals. PSA does not state it.
- **Yield** is computed only when area is above 0. Zero or missing area gives a missing yield, not zero.
- **BARMM gap:** from 2023 on, the BARMM region total is larger than the sum of its province rows (palay area: 16,466 ha in 2023, 20,203 ha in 2025; up to 2022 the gap is 0). The region row has a footnote "d/" whose text is not in the CSV. The cause is not confirmed, and this area cannot be given to any province. Decided: leave it out for now. Only province rows are used, so this area is simply not counted.

## 6. Models

Decided: the normal yield, the yield change, the minimum data, the El Niño quarter rule, and the model choice (rainfall: XGBoost; yield: departure line). Only the API questions in section 10 stay open.

- Start with a simple baseline. Other models must beat it.
- **Step 1, rainfall (decided):** predicts rainfall percent of normal per province and quarter.
  - Inputs: ONI this quarter and last quarter (quarterly ONI = mean of 3 months), quarter, province.
  - Training 1981-2008 (9,072 rows), validation 2009-2016 (2,592), test 2017-2026 (3,159).
  - Chosen: XGBoost, because it has the lowest validation RMSE of the four models (scores in section 7).
  - In El Niño quarters actual rainfall is about 74% of normal and predicted 70-72% (notebook 05).
- **Step 2, yield (decided):** predicts yield change % against the 10-year-line normal, clipped to +-100%.
  - Inputs: rain % this and last quarter, ONI this and last quarter. The pooled models also get crop type, quarter and province.
  - Training rows 1997-2008 (16,073). The first scorable year is 1997 because the normal needs 10 earlier years. Validation has 12,855 rows and test 16,434. It is trained on all 6 crop types.
  - Chosen: the departure line. It is a straight line through departures from normal (rain % - 100, and ONI) with no intercept, so a normal quarter always predicts 0%.
  - Why it was added: in the first comparison, linear regression, Random Forest and XGBoost all lost to the "always 0%" reference. They learned a fixed level of about +4% from 1997-2008, because yields sat above their 10-year-line normal then.
  - Rejected: the median past El Niño yield change per cell (no ML). Validation RMSE 19.35. Many cells had 0 or 1 training El Niño quarters.
  - El Niño effect: about 5% lower yield per +1 rise in last quarter's ONI (coefficient -5.2 on the validation fit). Rain barely matters: about +0.3% per 10 points below normal, which is the wrong direction for drought. The effect is real but small.
  - Lag (decided): validation RMSE of the departure line is 16.98 with this and last quarter, and 17.12 with this quarter only. Last quarter helps a little, so both are kept.
- The saved models are refitted on all rows (same as Layer 1). Test scores belong to the models fitted on rows up to 2016. Files: `backend/app/saved_models/layer2_rain.joblib`, `layer2_yield.joblib`, `layer2_models.json` (gitignored), written by `python -m app.layer2.train`.
- **Rainfall rule (decided):** for each province and calendar quarter, rainfall percent of normal = total rainfall in the quarter (sum of `rfh`) divided by its normal (sum of `rfh_avg`), times 100. This was chosen over averaging the ten-day `rfq` values because it does not soften dry quarters (Nueva Ecija 2015 Quarter 2: 57% with this rule, 70% with the average).
- **Normal yield (decided):** the normal follows the trend, because yield rises strongly over 1987 to 2026. For each province, crop, quarter and year, fit a straight line (yield = a + b x year) on the 10 years before that year, then extend it one year.
  - It uses only past years, so it does not leak future data, and the normal always uses the latest years.
  - Why: yield growth seems to slow after about 2010, so a long line keeps expecting the old fast growth. Median yield change in neutral quarters, all three fits scored on the same 45,099 cell-years (notebook 04, section 6; train is 1997-2008):

    | Normal | Train | Validate | Test | Spread (IQR) validate / test |
    | --- | --- | --- | --- | --- |
    | Line fitted once on 1987-2008 | -0.9% (fitted on these years) | +0.8% | -6.9% | 27.1 / 35.9 |
    | Line through all past years | +5.5% | +0.7% | -4.1% | 17.8 / 16.7 |
    | Line through the last 10 years | +3.8% | -1.1% | 0.0% | 14.6 / 13.8 |

    - The last-10-years line has no drift in the test years and the smallest spread. Its train median is +3.8% because yields were still speeding up in 1997-2008.
- **Yield change (decided):** (actual - normal) / normal x 100, only where the normal is above 0. Summaries must use medians and percentiles, not means: a tiny positive normal gives huge percents (up to about +450,000% in notebook 04).
- **Minimum data (decided):** the 10 years before the year being scored must all have a yield, because the normal is built per quarter. Otherwise the app says "not enough data" for that quarter. This replaces the earlier rule of 10 years per province, crop and quarter.
- **El Niño quarter rule (decided):** a quarter counts as El Niño when at least 2 of its 3 months fall inside an El Niño event from the Layer 1 labels (`find_events` in `backend/app/layer1_forecast/labels.py`, five-season rule).
  - For the ongoing event, the end is the last ONI month. Single warm months that never become an event do not count.
  - La Niña quarters use the same rule.
  - Quarters that are neither are neutral. Quarters that touch an event with only one month are "mixed" and left out of comparisons.
  - 1987 to 2026: 41 El Niño, 42 La Niña, 64 neutral, 13 mixed.

**Limitations:**

- Some cells (province, crop, quarter) are thin. 52 cells have no yield before 2009 (mostly Batanes and Dinagat Islands). 171 cells have a median area under 100 ha, so their yields are noisy. No area floor was set.
- Under the minimum data rule, 1,712 of 1,920 cells (province, crop, quarter) are usable now, meaning all of 2016-2025 have a yield (Q1 418, Q2 414, Q3 436, Q4 444). In the test years 2017-2026, 16,434 of 17,626 cell-years with a yield (93.2%) can be scored. The others show "not enough data" (notebook 04, section 6).
- CHIRPS normals (`rfh_avg`) are fixed per ten-day period and may include test years. This is a small leak in rainfall percent of normal that we cannot change.
- No yield skill on the test years: the chosen yield model is level with "always normal".
- The Palay and Corn totals are sums of their parts, so training on all 6 crop types counts each harvest twice.
- The Layer 1 forecast ONI error is not carried into Layer 2, so the app's confidence is understated.
- The app's "this quarter" and "last quarter" ONI may mix observed and forecast months. OPEN for the API step: how that mix is built and which quarter the map shows.

## 7. Evaluation

**Train, validation and test split (decided):** train 1987-2008, validate 2009-2016, test 2017-2026. These are the same boundaries as Layer 1. Split by date, never randomly.

- Models that predict a number (rainfall change, yield change) use MAE and RMSE.
- Always include a simple linear baseline to beat.
- Split by date, never randomly.
- Compare every model on the same split.

**Step 1, rainfall** (percent of normal; the reference always predicts 100%):

| Model | Val MAE | Val RMSE | Test MAE | Test RMSE |
| --- | --- | --- | --- | --- |
| Reference (always 100%) | 30.7 | 41.5 | 27.6 | 36.1 |
| Province line (rain % = a + b x ONI, one line per province and quarter) | 26.0 | 36.5 | 21.9 | 30.5 |
| Random Forest | 25.5 | 34.9 | 25.9 | 35.3 |
| XGBoost (chosen) | 24.0 | 33.9 | 23.1 | 31.8 |

**Step 2, yield** (yield change %; the reference always predicts 0%):

| Model | Val MAE | Val RMSE | Test MAE | Test RMSE |
| --- | --- | --- | --- | --- |
| Reference (always 0%) | 11.75 | 17.08 | 10.79 | 16.77 |
| Linear regression | 14.43 | 19.48 | 11.64 | 17.16 |
| Random Forest | 15.01 | 20.68 | 12.24 | 17.80 |
| XGBoost | 14.38 | 19.34 | 11.83 | 17.27 |
| Departure line (chosen) | 11.77 | 16.98 | 10.85 | 16.78 |

- Fed step 1's predicted rainfall, as the app does, the departure line scores validation RMSE 17.02 and test RMSE 16.73.
- The departure line beats the reference on validation (16.98 vs 17.08) but is level with it on test (16.78 vs 16.77).
- test_note: on test, the province line did slightly better than XGBoost for rainfall (30.5 vs 31.8). The choice is not changed after seeing test scores, because the model is chosen by validation RMSE.

## 8. Files

Planned.

- `backend/app/layer2/`: `features.py`, `models.py`, `train.py`.
- `backend/tests/test_layer2_models.py`
- `notebooks/05_layer2_models.ipynb`

- `backend/app/data/`: the crop loader, the rainfall loader, and the lookup table.
- `notebooks/03_explore_layer2.ipynb`: counts usable data per province and crop, and looks at rainfall.
- `notebooks/04_normal_and_colours.ipynb`: compares trend fits for the normal yield and the colour options.

## 9. Done When

- The lookup table covers every crop province, CHIRPS PCODE, and shape, and the loader checks it.
- The crop and rainfall loaders follow the cleaning rules, with tests.
- A baseline and at least one other model are compared on the same split and metrics.
- The chosen province and crop return a rainfall change, a yield change, and map colours.
- The OPEN items above are decided and written down.

## 10. Open Items

- What the "normal year" map shows.
- How the Layer 1 forecast is turned into Layer 2 inputs.
- API step: how the app's "this quarter" and "last quarter" ONI are built when they mix observed and forecast months, and which quarter the map shows.
