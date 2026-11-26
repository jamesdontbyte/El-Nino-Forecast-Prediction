# Layer 2 Spec: Impact and Land View

**Status:** draft. The data, cleaning rules, normal yield, colours and models are decided (evidence in notebooks 03, 04 and 05). The map output and the API routes are decided. Reopened on 2026-11-26 for the map upgrade in section 11 (zoom to province, municipal colours, optional cropland mask). Its open items are in section 10.

## 1. Purpose

Predict how El Niño changes rainfall and crop yield for the province and crop the user picks. Show the result on a map. Layer 3 starts from these results.

Yield change is measured against that province's own normal, not against other provinces.

## 2. Inputs and Outputs

**Input from the user:** a province and a crop. The user does not pick a date, horizon, or model.

**Input from the system:** the Layer 1 forecast. **ONI mix (decided):** a quarter's ONI is the mean of its 3 months, each month observed if available, otherwise the Layer 1 forecast. Last quarter's ONI is built the same way. 2026 Q4: ONI 2.45 (forecast), last quarter 2.14 (Q3 2026, observed). 2027 Q1: ONI 1.77 (forecast), last quarter 2.45 (forecast).

**Crops:**

- Palay (rice): irrigated, rainfed, and total.
- Corn: white, yellow, and total.

**Outputs (decided):** four routes in `backend/app/api/layer2.py`. The first three read the saved models and data on every request (no cache) and never train, like `GET /api/forecast`. Map views take about 0.5 s and crop data about 0.7 s.

- `GET /api/options`: `provinces` and `crops`.
  - `provinces`: 80 crop province names from `province_lookup.csv` (merged provinces appear once). NCR, City of Isabela and the Special Geographic Area are not included because they have no crop data.
  - `crops`: Irrigated Palay, Rainfed Palay, Palay, White Corn, Yellow Corn, Corn.
- `GET /api/map`: the map views from `map_output`: 2 forecast quarters x 4 views x 88 shapes. Each shape has `map_psgc`, `province`, `rain_pct` and `colour`.
- `GET /api/shapes`: the 88 map shapes as one GeoJSON FeatureCollection, for the front-end map (`backend/app/layer2/shapes.py`).
  - Built from the 18 files in `data/raw/philippines/regions/medres/` on the first request, then kept in memory.
  - Each feature keeps only `map_psgc` (`adm2_psgc` padded to 10 digits, matching `/api/map`) and `name` (`adm2_en`).
  - Coordinates are rounded to 3 decimals (about 110 m). About 2.3 MB, or about 460 KB gzipped (`GZipMiddleware` in `backend/main.py`).
- `GET /api/impact?province=...&crop=...`: the result for the chosen province and crop.
  - `province`, `crop`.
  - `models_used`: rain is xgboost, yield is departure_line.
  - `quarters`: one entry per forecast quarter, with `quarter` (for example "2026 Q4"), `oni`, `oni_prev`, `rain_pct` (predicted, 1 decimal), `colour`, `enough_data`, `yield_change_pct`, `normal_yield_t_per_ha` and `predicted_yield_t_per_ha`.
  - The three yield fields are null when `enough_data` is false. That means one of the 10 previous years has no yield, or the normal is not above 0. Rain and ONI are still returned.
- **Last quarter's rain (decided):** the observed rain % if that quarter has rainfall data, otherwise the predicted value of the quarter before. Today 2026 Q4 uses observed 2026 Q3, and 2027 Q1 uses predicted 2026 Q4. The unrounded rain % goes into the yield model. Rounding is only for display.
- **Predicted yield (decided):** predicted yield (t/ha) = normal x (1 + yield change / 100). The yield change is the yield model's prediction clipped to -100 .. +100, as in training.
- **Errors (decided):**
  - Unknown province or crop: 422, naming the bad value.
  - Missing saved model: 503, naming both train commands (`python -m app.layer1_forecast.train` and `python -m app.layer2.train`).
  - Missing data file: 503, saying which data file is missing.
- **Example, Nueva Ecija Palay:**
  - 2026 Q4: ONI 2.45 / 2.14, rain 65.7% (yellow), yield change -4.5%, normal 5.95 t/ha, predicted 5.68.
  - 2027 Q1: ONI 1.77 / 2.45, rain 38.3% (red), yield change -6.0%, normal 6.03, predicted 5.67.
  - Batanes Irrigated Palay: `enough_data` is false in both quarters (rain 87.1% green, 72.0% yellow).
- **Check:** all 80 provinces x 6 crops run without errors. Share with enough data: 92.5% for 2026 Q4 and 88.8% for 2027 Q1.

**Land view:**

- A flat 2D province map with a toggle between four views (below).
- Colours show dryness: green healthy, yellow stressed, red severe.
- Provinces are coloured as whole shapes. There is no 25 km grid. **Being changed (2026-11-26):** the map will colour each municipality by its own rainfall instead (section 11). Why: a province colour hides dry and wet parts inside one province, and municipal shapes are now available. The province colour stays in `/api/impact` and Layer 3, because the yield model and the crop gap table work per province.
- **Forecast quarters (decided):** the quarters fully covered by observed plus forecast ONI. Now: 2026 Q4 and 2027 Q1 (ONI is observed to September 2026, forecast October 2026 to March 2027). Labels look like "2026 Q4".
- **Four views (decided):** for each forecast quarter, each view lists all 88 map shapes with `map_psgc`, `province` (the lookup's `crop_name`), `rain_pct` (rounded to 1 decimal) and colour.
  - `prediction`: rain % predicted by the saved rainfall model (XGBoost) from the quarter's ONI.
  - `normal`: observed rainfall in the most recent year whose same quarter was neutral (no El Niño or La Niña, by the 2-of-3-months rule, using observed ONI only). Now: 2025 for Q4 and 2026 for Q1. The year is part of the output.
  - `el_nino_2015_16` and `el_nino_2023_24`: observed rainfall for the same quarter of the year inside each event (Q4: 2015 Q4 and 2023 Q4; Q1: 2016 Q1 and 2024 Q1).
- **Colours (decided):** PAGASA bands on the rounded value: red 40.0 or less, yellow 80.0 or less, green above. Missing rainfall is grey.
- **No-crop areas (decided):** the 4 NCR shapes are coloured by rainfall (CHIRPS PH13074), because the map shows dryness, which needs only rainfall. City of Isabela and the Special Geographic Area have no rainfall and are grey.
- Current output (green / yellow / red / grey of 88 shapes):
  - 2026 Q4: prediction 1/85/0/2; normal (2025) 86/0/0/2; 2015 Q4 33/53/0/2; 2023 Q4 47/39/0/2.
  - 2027 Q1: prediction 0/6/80/2; normal (2026) 70/16/0/2; 2016 Q1 9/35/42/2; 2024 Q1 16/62/8/2.
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

**Municipal shapes (checked 2026-11-26):** `Municipality/municities-provdist-*.json`, from the same philippines-json-maps project.

- 88 files, one per province shape. The number in the file name is that shape's `adm2_psgc`, and all 88 province shapes (all of `map_psgc` in the lookup table) have exactly one file. So the existing lookup links every municipality to its crop province and CHIRPS PCODE with no new matching table.
- 1,642 shapes: 1,493 "Mun" and 149 "City". 1 to 53 per file (median 17). 1,339 Polygon and 303 MultiPolygon.
- Properties: `adm1_psgc`, `adm2_psgc`, `adm3_psgc` (unique, 1,642 codes), `adm3_en` (name, UTF-8, no repeated name inside a province), `geo_level`, `area_km2`, and a few length and area fields.
- Use the file's `adm2_psgc` for the province, not digits of `adm3_psgc`: 34 highly urbanized cities (for example City of Davao, City of Cebu, the NCR cities) have a different province part in their own code.
- No-crop areas: the 4 NCR files have 17 cities and Pateros. City of Isabela is 1 shape. The Special Geographic Area has 8.
- Sizes: area from 0 km² (Kalayaan) up, median 112 km². 125 municipalities are smaller than one CHIRPS pixel (about 31 km²) and 729 are under 100 km².
- 7.4 MB raw. About 3.1 MB with coordinates rounded to 3 decimals, about 620 KB gzipped (province shapes: 460 KB).

**No municipal rainfall yet:** `phl-rainfall-subnat-full.csv` has only adm_level 1 (17 regions) and 2 (81 provinces). Municipal colours need the CHIRPS grid itself (section 11).

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
- Shapes with no crop data: see the no-crop areas rule in section 2.
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

Decided: the normal yield, the yield change, the minimum data, the El Niño quarter rule, and the model choice (rainfall: XGBoost; yield: departure line).
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
- The 2027 Q1 prediction is redder than any observed Q1. Observed Q1 after strong El Niños (of 81 provinces): 1983 had 52 red (median 36% of normal), 1992 51 red (37%), 1998 55 red (34%), 2016 40 red (40%). So a very dry Q1 fits history. But the model predicts a typical value with less spread than real provinces. When that typical value is just under 40%, almost every province turns red at once. The red count is likely exaggerated. Read the map as "most provinces near or below the red line".
- The map colours only the central forecast. The confidence band is not shown.
- A short cold spell under 5 months counts as neutral, so the "normal" year is by our rule, not NOAA's list.
- The map output has no shape names for NCR, City of Isabela and the Special Geographic Area (province is empty). The front end reads names from the GeoJSON.
- The predicted yield change is almost the same for every province and crop (2026 Q4: -4.4% to -5.0%; 2027 Q1: -5.9% to -6.6%). The departure line has no province or crop inputs and its rain weights are tiny, so it mostly follows ONI. Provinces differ in their normal and predicted yield in t/ha, not in the percent change.
- Not in the map output: geometry, the front end, and yield on the map.

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
- `backend/app/layer2/map_output.py`: builds the map output. Run with `python -m app.layer2.map_output`.
- `backend/app/layer2/impact.py`: builds the result for one province and crop.
- `backend/app/api/layer2.py`: the three routes (`/api/options`, `/api/map`, `/api/impact`). The router is included in `backend/main.py`.
- `backend/tests/test_layer2_models.py`
- `backend/tests/test_layer2_map.py`
- `backend/tests/test_api_layer2.py`
- `notebooks/05_layer2_models.ipynb`

- `backend/app/data/`: the crop loader, the rainfall loader, and the lookup table.
- `notebooks/03_explore_layer2.ipynb`: counts usable data per province and crop, and looks at rainfall.
- `notebooks/04_normal_and_colours.ipynb`: compares trend fits for the normal yield and the colour options.

## 9. Done When

- The lookup table covers every crop province, CHIRPS PCODE, and shape, and the loader checks it.
- The crop and rainfall loaders follow the cleaning rules, with tests.
- A baseline and at least one other model are compared on the same split and metrics.
- The chosen province and crop return a rainfall change, a yield change, and map colours.
- All decisions are written down. Nothing is open.

## 10. Open Items

For the map upgrade in section 11. Decided by the user on 2026-11-26:

1. **Municipal rainfall source (decided):** CHIRPS grid, 0.05°, cut to the Philippines. The download route and file size are looked up first and shown to the user before anything large is downloaded.
   - Found (2026-11-26): NOAA ERDDAP dataset `chirps20GlobalMonthlyP05` (CHIRPS v2.0, monthly, variable `precip` in mm/month, dimensions time, latitude, longitude, longitude -180..180, fill value -9999). It can cut a lat/lon box server-side, for example `https://coastwatch.pfeg.noaa.gov/erddap/griddap/chirps20GlobalMonthlyP05.nc?precip[(1981-01-01):1:(2025-02-01)][(4.5):1:(21.2)][(114.2):1:(126.7)]`. Latitude order is not stated, so check it on a small request first.
   - Its data ends at 2025-02-01. That covers the normal period (1989-2018) and both El Niño events, but not the current `normal` view years (2025 Q4, 2026 Q1). A route for 2025-2026 months is not found yet.
   - Estimated size for the Philippines box: about 250 x 334 pixels x 530 months x 4 bytes, about 180 MB uncompressed. This is a calculation, not a measured file size.
   - CHIRPS v2 production ends after December 2026 (CHC). v3 exists. Our CSV is v2.
3a. **`rfh_avg` years:** the HDX HAPI climate guide and the PhilRice catalog give the long-term average as 1989-01-01 to 2018-12-31. Not confirmed against our numbers until the province check runs.
2. **Prediction view (decided): option (a).** The prediction view stays coloured per province and is labelled as a province prediction. Only the three past-data views (`normal`, `el_nino_2015_16`, `el_nino_2023_24`) are municipal. Rejected: (b) retraining the rainfall model on municipal rows, because it reopens the model choice in sections 6 and 7 and mostly relearns the province (neighbouring municipalities share pixels); (c) scaling the province prediction by each municipality's past El Niño ratio, because it is a rule, not ML, and noisy with about 10 El Niño quarters per calendar quarter.
3. **Normal period (decided):** the same years as the CSV's `rfh_avg`, checked against the CSV (section 11) before any municipal number is trusted.

Still open:

4. **Cropland source** (step 3, optional, later).

## 11. Map Upgrade (planned 2026-11-26, not built)

Three steps, each its own task, committed and pushed separately.

**Step 1, zoom to province:** when the user picks a province, the map fits its bounds.

- Front end only. Merged provinces zoom to all their shapes (Maguindanao: 2 shapes; Davao del Sur: 2 shapes), found through `/api/map`'s `province` field.
- No choice: the map stays at the whole-country view.

**Step 2, municipal colours:**

- In the three past-data views, each of the 1,642 municipalities gets its own rain % of normal and colour (the prediction view stays per province, section 10), same rule as provinces (quarter total over quarter normal, section 6) and the same PAGASA bands on the rounded value. Missing rainfall is grey.
- Rainfall per municipality: take the CHIRPS pixels whose centre is inside the shape, average their rain and their normal separately, then divide (ratio of sums, as in section 6; averaging pixel percents would soften dry quarters). Sea pixels have no value (-9999 or NaN) and are masked first.
- If no pixel centre is inside (small municipalities), use the nearest pixel that has a value, measured from a point inside the shape (a centroid can fall at sea for odd shapes and MultiPolygons). Beyond a distance cap it is grey (cap to be set, about one pixel). Kalayaan (0 km², far from Palawan) will be grey.
- Reading the grid uses xarray and netCDF4 on a Philippines-only cut. Point-in-shape uses matplotlib's `Path`. All three are already installed, so no new dependency.
- Monthly grids are enough, because quarters are whole months.
- The municipal normal must use the same years as the CSV's `rfh_avg`. That period is not confirmed yet, so it is an open item. With a different period, municipal and province values would disagree for no real reason.
- Prelim and final: use final grids where they exist. Which latest months are prelim gets written down when downloaded. The "last quarter's rain" rule (section 2) keeps using the province CSV.
- This is a one-off preprocessing script writing a quarterly table to `data/processed/` (gitignored). The API only reads it.
- Check, before trusting any municipal number: rebuild the 81 province quarter totals from the grid (rain and normal) and compare them with the CSV's summed `rfh` and `rfh_avg`. Group by CHIRPS unit (`rain_pcode` in the lookup, so old boundaries like Maguindanao 087 and NCR count as one unit). This tests the normal years, the pixel rule and the CHIRPS version at once. Also compare pixel counts with `n_pixels` (183 for Nueva Ecija). The tolerance is written down before running the check.
- The three observed views (`normal`, `el_nino_2015_16`, `el_nino_2023_24`) work per municipality with the same years as now. Nothing is trained, so there is no new leak. If the normal period includes test years, that is the same known leak as in the limitations.
- The `normal` view's year is picked only from years present in both the CSV and the grid, so a newer neutral quarter that is missing from the grid does not show grey.
- **New routes, existing ones unchanged:** `GET /api/municipal_shapes` (1,642 shapes, about 620 KB gzipped) and `GET /api/municipal_map` (one row per municipality per view). `/api/shapes` and `/api/map` stay as they are, so their tests and the province outline keep working. First map load is about 1.1 MB gzipped in total. Route names are a proposal.
- No-crop areas: NCR municipalities are coloured by rainfall like any other. City of Isabela and the Special Geographic Area get colours too, because the grid covers them. This changes the "grey" rule in section 2 for the municipal map only.
- Unchanged: `/api/impact` keeps the province rain % and colour, and Layer 3 keeps using them (Layer 3 does not read the map output).
- **Yield stays per province:** PSA crop data is per province only. Wherever yield is shown, it is labelled "province estimate". The Impact cards' rain % and colour are labelled "province rainfall", so they are not confused with a municipality's colour on the map. The map tooltip says the colour is municipal rainfall.
- Zoom (step 1) sits outside the keyed `<GeoJSON>` and depends only on the province, so restyling 1,642 shapes does not re-trigger it. It takes its bounds from the province shapes, not from stored layer references, because a remount replaces the layers.
- Each `/api/municipal_map` row also carries its province's `map_psgc`, so the front end can link a municipality to its province.
- Speed: the municipal layer's `key` is quarter and view only, not province. Only the 88-shape province outline layer is keyed on province, so picking a province does not rebuild 1,642 shapes. `MapContainer` gets `preferCanvas` (draws on one canvas instead of 1,642 SVG paths). Lag is a judgement, not measured yet.

**Step 3, cropland mask (optional, later):** colour only farmland inside each municipality. The data source is not chosen. Only planned if steps 1 and 2 work.
