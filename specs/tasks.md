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
- [ ] From the forecast ONI series, work out start month and strength using the label rules.
- [ ] Confidence range: forecast ONI plus or minus the validation RMSE at each lead time.
- [ ] Duration range (only when an event is underway, otherwise null): observed months plus forecast months. Low end from the lower band, high end from the upper band.
- [ ] Open-ended duration: if the upper band is still at +0.5 or above in the last forecast month, set duration_open_ended to true and report "from L months to at least H months".
- [ ] Strength when an event is underway: peak ONI across the observed and forecast months together.

## 9. Compare and save
- [ ] notebooks/02_model_comparison.ipynb: one table with every model, same split, same metrics.
- [ ] Run the final comparison on the test period once.
- [ ] train.py: train, compare, and save the best model to backend/app/saved_models/.

## 10. API
- [ ] backend/app/api/forecast.py: GET /api/forecast loads the saved model (never trains) and returns every field in layer1 spec section 2.
- [ ] Connect the route to the FastAPI app in backend/main.py and check it in the browser.
- [ ] Go through the "Done When" list in the layer1 spec.

## Later (only after the above works)
- [ ] Finalize ERA5 variables and box, then download ERA5.
- [ ] Optional: TAO buoy data.
- [ ] Optional: LSTM, then CNN on ERA5.
