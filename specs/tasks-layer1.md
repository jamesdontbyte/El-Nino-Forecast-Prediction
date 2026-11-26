# Tasks: Layer 1 (El Niño forecast)

Work top to bottom. Tick each box when done. Details are in specs/layer1-forecast.md.

## 0. Setup
- [x] Project skeleton, .gitignore, backend/.venv, and GET /health.
- [x] Install ruff, pytest, Jupyter, and ipykernel into .venv and add them to requirements.txt.

## 1. Decisions before coding
- [x] Write the Kaggle ENSO dataset name and link into the specs.
- [x] Confirm the event rule (five consecutive overlapping three-month periods) against NOAA.
- [x] Duration applies only to events that meet the five-season rule. It counts the months within the event where ONI is at or above +0.5.
- [x] Strength uses the event's peak ONI: weak 0.5 to below 1.0, moderate 1.0 to below 1.5, strong 1.5 and above (a convention, not official NOAA categories).
- [x] Split: train 1950 to 2008, validate 2009 to 2016, test 2017 to the latest month.
- [x] Lead times: 1 to 6 months.
- [x] Metrics: MAE and RMSE for models that predict ONI; accuracy and a confusion matrix for the status classifier.
- [x] backend/main.py stays at the backend root.
- [x] Index: ONI. RONI is a possible later option, but it comes from the Kaggle file (ends April 2026), so switching would need a new source.

## 2. Get the data
- [x] Download the Kaggle ENSO file into data/raw/enso/.
- [x] Download NOAA oni.ascii.txt and soi.txt into data/raw/enso/.
- [x] ONI source of truth: NOAA's oni.ascii.txt (1950 to September 2026). Kaggle is a secondary source for RONI, Niño 3.4 anomaly, and SOI.

## 3. Explore
- [x] notebooks/01_explore_enso.ipynb: list columns, date range, missing values, and plot ONI over time.

## 4. Load and clean
- [x] backend/app/data/load_enso.py: read ONI from NOAA's oni.ascii.txt (ANOM column), mapping each season to its centre month (DJF = January).
- [x] load_enso.py: read RONI, Niño 3.4 SST anomaly, and SOI from the Kaggle file, following the Kaggle loader rules in the layer1 spec. Join both on the month, one row per month.
- [x] Save the cleaned table to data/processed/enso_monthly.csv.
- [x] Compare the Kaggle ONI column with NOAA's oni.ascii.txt (done by hand; results are in the layer1 spec).
- [x] Compare the Kaggle SOI column with NOAA's soi.txt file and note any differences.

## 5. Labels
- [x] labels.py: status per month (El Niño, neutral, La Niña).
- [x] labels.py: find events with the five-season rule. Give each a start month, duration, peak ONI, and strength.
- [x] Check that 1982 to 83, 1997 to 98, 2015 to 16, and 2023 to 24 are found with sensible start, duration, and strength.
- [x] Label the event that began in May 2026 as "ongoing". Use its months for ONI and status targets, and exclude it from duration scoring.
- [x] First tests: tests for labels.py.

## 6. Features and split
- [x] Build lag features from ONI only (1, 3, 6, and 12 months earlier), using only data available at forecast time.
- [x] Build targets: ONI at each lead time (1 to 6 months).
- [x] Split by date into train, validation, and test. Do not look at test results until step 9.

## 7. Models (one at a time)
- [x] Linear regression baseline: MAE and RMSE per lead time on validation.
- [x] Logistic regression: status 1 to 6 months ahead, accuracy and confusion matrix.
- [x] Random Forest.
- [x] XGBoost.

## 8. Turn the forecast into the outputs
- [x] From the forecast ONI series, work out start month and strength using the label rules.
- [x] Confidence range: forecast ONI plus or minus the validation RMSE at each lead time.
- [x] Duration range (only when an event is underway, otherwise null): observed months plus forecast months. Low end from the lower band, high end from the upper band.
- [x] Open-ended duration: if the upper band stays at +0.5 or above through every forecast month, set duration_open_ended to true and report "from L months to at least H months" ("at least N months" when the lower band also stays warm throughout).
- [x] Strength when an event is underway: peak ONI across the observed and forecast months together.

## 9. Compare and save
- [x] notebooks/02_model_comparison.ipynb: one table with every model, same split, same metrics.
- [x] Run the final comparison on the test period once.
- [x] train.py: train, compare, and save the best model to backend/app/saved_models/.
- [x] Score event detection on the test period: events found, start and duration error per lead (ongoing event excluded from duration).

## 10. API
- [x] backend/app/api/forecast.py: GET /api/forecast loads the saved model (never trains) and returns every field in layer1 spec section 2.
- [x] Connect the route to the FastAPI app in backend/main.py and check it in the browser.
- [x] Go through the "Done When" list in the layer1 spec.

## 11. Part A: optional target year (layer1 spec, section 12)
- [x] Confirm the section 12 values: anchor March, years 1960 to 2100, no front-end year input.
- [x] train.py: fit the chosen model once per hindcast year on the ONI table cut at that year's anchor (March of the target year), so every target used is at or before the anchor, and save them in oni_forecast.joblib keyed by year. Update the metadata file. Test: no hindcast model uses data after its anchor.
- [x] forecast.py: `forecast_from_bundle` takes the ONI table and the models per lead, so the live forecast and the hindcast share one path. Check its callers (layer2 impact and map, simulation) still give the same result.
- [x] outputs.py: climatology rows (mean ONI, status shares, and event start share per calendar month) from full observed years. Tests.
- [x] forecast.py: optional `year` query (1960 to 2100), mode choice, `mode`, `target_year`, `note`, and `observed_oni` in hindcast. Without `year`, the response is unchanged. An old model file without hindcast models returns 503. Update `save_small_model` in tests/test_api.py. Tests for each mode, the boundary years, and B in June and in December.
- [x] Run the checks and go through the "Done when" list in section 12.

## 12. Part B: ERA5 features (layer1 spec, section 13). Do not start until ERA5 is downloaded.
- [x] Confirm the ERA5 variables and boxes requested: SST, 10 m u and v wind, mean sea level pressure, total precipitation, 30°S to 30°N, two files (120°E to 180° and 180°W to 70°W).
- [x] Once downloaded: check the years, months, file size, and longitude convention of both files, and that their variables, years, and months match.
- [x] backend/app/data/load_era5.py: box averages (cos-latitude weighted), anomalies against the 1950 to 2008 monthly averages, save data/processed/era5_monthly.csv. Check for gaps.
- [x] features.py: join ERA5 on the month, add lag 1 and lag 3 of each ERA5 feature. Tests.
- [ ] Compare every regression model with and without ERA5 on validation, on the same rows. Repeat once with ERA5 from 1979 as a check. Choose with the existing rule, then score the test period once more. Record the result in section 7.
- [ ] Always: add `era5_used` to the response (false while ERA5 is not kept; absent in climatology).
- [ ] If ERA5 is kept: train.py saves the ERA5 model and the best ONI-only model, each with its own validation RMSE. The route falls back to ONI only when ERA5 does not reach month B and sets `era5_used`. Hindcast models use the ERA5 features. Test the fallback.
- [ ] Run the checks.

## Later (only after the above works)
- [x] Finalize ERA5 variables and box, then download ERA5. (Downloaded. Part B above covers the rest.)
- [ ] Optional: TAO buoy data.
- [ ] Optional: LSTM, then CNN on ERA5.
- [ ] Decide whether SOI comes from NOAA's soi.txt, which reaches October 2026, instead of the Kaggle file, which ends in May 2026. Not needed while the models use ONI only.
