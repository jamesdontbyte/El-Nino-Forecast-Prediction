# Layer 1 Spec: El Niño Forecast

**Status:** draft. Values marked (suggested) are proposals to confirm before building.

## 1. Purpose

Report whether an El Niño is underway. If none, predict whether one is coming, when it starts, and how strong it will be. If one is underway, give its observed start, then forecast how strong it gets and how long it lasts. Duration is only given when an event is underway. This is the core machine learning layer. Layers 2 and 3 depend on its output.

## 2. Inputs and Outputs

**Input (from the system, not the user):** the latest available climate data. The user does not pick a date, horizon, or model.

**Two cases:**

- **No event underway:** report whether an El Niño is coming, when it starts, and how strong it will be.
- **Event underway (the case now):** report that it is active, return the observed start month (May 2026), then forecast how strong it gets and how long it lasts.

**Output (returned by the API):**

- `event_underway`: true or false
- `event_status`: El Niño, neutral, or La Niña for each forecast month
- `start_month`: the predicted first month of El Niño conditions, or none. When an event is underway, this is the observed start month.
- `duration_months`: only when an event is underway; null when no event is underway. A range (low and high), not a single number. It counts the months already observed plus the forecast months. The low end comes from the lower confidence band and the high end from the upper band. When `duration_open_ended` is true, the high end is a minimum, reported as "from L months to at least H months". If the lower band also stays at +0.5 or above through every forecast month, low and high are equal and it is reported as "at least N months". Returned as low, high, and that text.
- `duration_open_ended`: true or false. True when the upper band stays at +0.5 or above through every forecast month, so the true end of the event is unknown. Always false when no event is underway.
- `strength`: weak, moderate, or strong
- `forecast_series`: the predicted ONI value for each of the next 1 to 6 months, with a confidence range
- `model_used`: the name of the model that produced the result

**Optional target year (added later, see section 12):** `GET /api/forecast?year=YYYY`. Without `year`, the route works exactly as above. With `year`, the response also has `mode` (`hindcast`, `forecast`, or `climatology`) and `target_year`. This is the one exception to "the user does not pick the forecast date": the year is optional and the system still picks the anchor month, horizon, and model.

## 3. Label Definitions

All labels are built from the monthly ONI index.

- **Event status:** El Niño when ONI is +0.5 or above. La Niña when ONI is -0.5 or below. Neutral otherwise.
- **Event:** NOAA requires five consecutive overlapping three-month periods at the threshold. Confirmed on NOAA's ONI page.
- This five-season rule is NOAA's historical ONI convention. NOAA's operational definition now uses RONI.
- **Strength:** uses the peak ONI of the event. Weak from 0.5 to below 1.0, moderate from 1.0 to below 1.5, strong from 1.5 and above. (ONI has two decimals, so a peak of 0.97 is weak and 1.49 is moderate.) These cutoffs are a common convention, not official NOAA categories. When an event is underway, strength uses the peak ONI across the observed months and the forecast months together.
- **Duration:** applies only to events that meet the five-season rule. It is the number of months within the event where ONI is at or above +0.5. Shorter spells are not events and have no duration.
- **Start month:** the first month of an event that meets the five-season rule.
- **Ongoing event:** an event that has not ended by the last month of data is labelled "ongoing". The El Niño that began in May 2026 is ongoing. Its months can be used for ONI and status targets, but it is excluded from duration scoring because its final duration is not known yet.

## 4. Data

| Data | Use | Status |
| --- | --- | --- |
| NOAA ONI (`oni.ascii.txt`), 1950 to September 2026 | Source of truth for ONI: labels, targets, and lag features | Confirmed. Downloaded. |
| ENSO monthly indices from Kaggle | Secondary source for RONI, Niño 3.4 anomaly, and SOI. Its ONI column is only compared with NOAA. | Confirmed. ONI and SOI compared with NOAA. |
| ERA5 monthly data, Pacific box, January 1950 to October 2026 | Extra features and the CNN | Downloaded and checked. Four files in two halves, about 1.2 GB. |
| TAO buoy data from Kaggle | Optional learning dataset, 1980 to 1998 only | Not yet opened. |

**NOAA ONI file (`oni.ascii.txt`):** the source of truth for ONI. Columns are SEAS, YR, TOTAL, and ANOM. ANOM is the ONI value. It covers 1950 to September 2026 (the ASO 2026 season).

- Map each season to its centre month (DJF = January, JFM = February, and so on up to NDJ = December).
- Labels, targets, and lag features use this ONI.

**Kaggle ENSO dataset:** El Nino-Southern Oscillation (ENSO) Data. Link: https://www.kaggle.com/datasets/shabanamir/enso-data/data. A secondary source for RONI, Niño 3.4 anomaly, and SOI. Its ONI column is not used for labels. ONI and RONI end in April 2026; Niño 3.4 anomaly and SOI end in May 2026.

**Kaggle vs NOAA ONI comparison:** the months align when each NOAA season is mapped to its centre month (shifting by one month either way fits worse). The values are not identical. The mean absolute difference is 0.07, and 49 months change status (El Niño, neutral, or La Niña) depending on which file is used. The likely cause, for example an older NOAA data version in the Kaggle file, is not confirmed.

**Kaggle vs NOAA SOI comparison:** the Kaggle SOI column matches the ANOMALY block of NOAA's `soi.txt` exactly (all 905 shared months, 1951-01 to 2026-05). It does not match the STANDARDIZED block. NOAA's file runs to October 2026, five months past the Kaggle file. `soi.txt` is fixed-width, its numbers can touch (`-1.7-999.9`), and -999.9 means missing. Details are in `notebooks/01_explore_enso.ipynb`, section 5.

**Columns kept:**

- Date
- ONI (only for the comparison with NOAA)
- RONI
- Nino 3.4 SST Anomaly
- SOI
- ENSO Phase-Intensity (ONI-based)

All other columns are ignored for now.

- **Phase-intensity column:** never use it as a training feature. It is derived from ONI, so it would leak the answer into the model. It cannot check our monthly labels either, because it has one label per 12-month block and a "very strong" class. Our strength scale stays three levels.
- **Checking our labels:** check that the events 1982 to 83, 1997 to 98, 2015 to 16, and 2023 to 24 are found, and that the event that began in May 2026 is found and labelled ongoing.
- **Encoding:** the file is UTF-8 and loads with plain `pd.read_csv`. The phase-intensity column names contain a literal "�".
- **Cross-check:** the ONI column has been compared with NOAA's `oni.ascii.txt`, and the SOI column with NOAA's `soi.txt` (see above).

**Loader rules (Kaggle file):**

- Strip whitespace from column names (for example, the ONI column is read as `"  ONI"`).
- Drop the `Unnamed: 0` column.
- Drop rows where all of RONI, Nino 3.4 SST Anomaly, and SOI are empty (the placeholder months at the end of 2026).
- `Date` is the middle month of the three-month window, in M/D/YYYY format.
- Ignore the Season columns.

**Index choice:** labels, targets, and lag features use ONI. RONI is a possible later option. It comes from the Kaggle file, which ends in April 2026, so switching would need a new source.

**Note:** NOAA moved its official ENSO monitoring to RONI in February 2026. We use ONI because it has a long history and the strength cutoffs were written for it. Explain this choice in the presentation.

**ERA5 request (confirmed):** sea surface temperature, 10 m wind (u and v), mean sea level pressure, and total precipitation, 30°S to 30°N, in two halves: west (120°E to 180°) and east (180°W to 70°W). Monthly means, 0.25° grid. Downloaded and checked:

- **Four files, about 1.2 GB in total.** Copernicus splits each half into two files: `stepType-avgad` holds tp only (monthly sums), `stepType-avgua` holds u10, v10, msl, and sst. The folder names (`Era5_1`, `Era5_2`) do not say which half is which, so the loader picks the half from each file's longitudes, never from the name. `Era5_1` is east (152 + 618 MB), `Era5_2` is west (88 + 357 MB).
- **Time:** every file has every month from January 1950 to October 2026 (922 months), with no gaps or duplicates. The tp files stamp each month 06:00 and the others 00:00, so every time stamp is rounded down to the first of its month before merging.
- **Grid:** latitude runs 30 to -30 (north to south) in 0.25° steps in all four files. Both halves use -180 to 180 longitudes. The 180° column is in both halves (180 in the west, -180 in the east) and is identical in every variable and every month, so it is kept once.
- **Preliminary months:** September and October 2026 are ERA5T (`expver` 0005), an early release that ECMWF may still revise. All earlier months are final (`expver` 0001). Decided: keep them, with a `preliminary` column in `era5_monthly.csv`.
- **Land:** sst is empty (NaN) over land (7% of the east grid, 16% of the west). Box averages leave land cells out.

Build the ENSO-only pipeline first. Add ERA5 only after the baseline works.

## 5. Models

Build in this order. Stop adding models once the comparison is clear.

1. **Linear regression:** baseline. Every other model must beat it.
2. **Logistic regression:** predicts the status (El Niño, neutral, or La Niña) 1 to 6 months ahead, not the current month.
3. **Random Forest and XGBoost:** forecast the ONI value from lagged ONI features (ONI 1, 3, 6, and 12 months earlier). ONI only for now.
4. **LSTM (optional):** time series forecast, only after the models above work.
5. **CNN (optional):** reads ERA5 maps, only if ERA5 is downloaded and time allows.

Start and duration are derived from the forecast ONI series using the label rules in section 3. They are not trained as separate targets at first.

**Confidence range:** the forecast ONI plus or minus the RMSE at each lead time, measured on the validation period.

**Duration range (only when an event is underway):** count the months already observed, then add the forecast months. The low end uses the lower confidence band, and the high end uses the upper band. When no event is underway, `duration_months` is null.

**Open-ended duration:** if the upper band stays at +0.5 or above through every forecast month, the true end is unknown. Set `duration_open_ended` to true and report the duration as "from L months to at least H months", or "at least N months" when the lower band also stays at +0.5 or above throughout (so L = H). If the upper band dips below +0.5 and later rises again, the high end stops at the first dip and the duration is not open-ended.

**Status, start, and strength come from the ONI forecast:** `event_status`, `start_month`, and `strength` are all derived from the forecast ONI values (the regression model), so they always agree with `forecast_series`. Logistic regression is a comparison model only.

**Predicted events:** when no event is underway, a predicted event must also meet the five-season rule, counting the observed months and the forecast months together. Its start can be an already-observed month. Warming that is too short to meet the rule gives no start month.

## 6. Train and Test Split

- Split by date, never randomly. Random splits leak future information into training.
- Train on 1950 to 2008, validate on 2009 to 2016, test on 2017 to the latest month.
- The test period includes the 2023 to 2024 event. Keep it untouched until the final comparison.
- The last months of the test period are an event still in progress (the one that began in May 2026), so scores for that event are rough.
- **No leakage:** lag features may only use data that would really be available at forecast time. The newest ONI value is about two months old, because each ONI value is a three-month average centred on its month.
- **Anchor month (B):** each row is anchored on the newest published ONI month. Lead h targets the ONI at B+h. Lag k is the ONI k months before the first forecast month (B+1), so lag 1 is ONI(B). Every feature is at or before B.
- **Split boundaries:** rows go to a period by their anchor month. Train and validation rows whose targets reach into the next period are dropped (the last 6 of each).
- There are only about 20 events since 1950. Treat results as rough, and say so in the presentation.

## 7. Evaluation

- **Forecast value:** MAE and RMSE of the predicted ONI on the test period, reported per lead time (1 to 6 months ahead).
- **Event status:** accuracy and a confusion matrix.
- **Start and duration:** how many test-period events were detected, and how far off the start month and duration were. The ongoing event is excluded from duration scoring.
- Compare every model on the same split. Models that predict the ONI value use MAE and RMSE. The status classifier uses accuracy and a confusion matrix.
- Each model is fitted once per lead time (6 models per algorithm), with fixed settings and no tuning.
- Two reference rows with no model are always shown: persistence (the forecast for every lead is the newest ONI) for MAE and RMSE, and most-common-class (always the most common training status) for status accuracy.
- Skill drops with lead time. Report that honestly, and do not hide the longer lead times.
- **Model choice:** the lowest mean validation RMSE across leads 1 to 6, one model for all leads, decided before any test score exists. Result: linear regression (0.488; XGBoost 0.525, Random Forest 0.561, persistence 0.685).
- **Test scoring:** every model is fitted on 1950 to 2016 and scored once on 2017 onward. Each lead is scored only on rows whose target is observed (116 rows at lead 1 down to 111 at lead 6).
- **Saved model:** the chosen model is refitted on all rows with known targets (1950 to the newest ONI) and saved by `train.py`. Its confidence band uses the validation RMSE. The test scores describe the 1950 to 2016 version, so they are an estimate for the saved model.
- **Test results (linear regression):** RMSE 0.107 at lead 1 rising to 0.664 at lead 6 (persistence 0.189 to 0.893). Status accuracy (logistic regression) 0.92 at lead 1 down to 0.51 at lead 6 (most-common-class about 0.43). Event detection: all 4 test events found at lead 1 (mean start error 0.5 months), 3 of 4 at leads 2 to 4, 2 of 4 at leads 5 and 6. Each lead's forecast series keeps its months past the newest observation, so the ongoing 2026 event is scored on real forecasts. Details are in `notebooks/02_model_comparison.ipynb`.
- **ERA5 comparison (Part B, section 13):** run with `python -m app.layer1_forecast.compare_era5` from backend/. Same 90 validation rows for every version, same fixed settings, no tuning. Mean validation RMSE across leads 1 to 6:

  | Version | Linear regression | Random Forest | XGBoost |
  | --- | --- | --- | --- |
  | ONI only | 0.488 | 0.561 | 0.525 |
  | ONI + ERA5 | **0.436** | 0.540 | 0.507 |
  | ONI only, training from 1979 (reference) | 0.484 | 0.568 | 0.553 |
  | ONI + ERA5, anomalies and training from 1979 (check) | 0.424 | 0.554 | 0.521 |

  Persistence 0.685. Linear regression validation RMSE by lead, ONI only vs ONI + ERA5: 0.130 vs 0.116, 0.296 vs 0.256, 0.456 vs 0.399, 0.587 vs 0.522, 0.690 vs 0.624, 0.771 vs 0.703. ERA5 helps linear regression at every lead, more at longer leads. It helps Random Forest and XGBoost on average but not at every lead (Random Forest +0.003 at lead 1, XGBoost +0.006 at lead 6). The 1979 check is slightly better again (0.424), so the older, less reliable ERA5 years do not seem to hurt.
- **ERA5 decision (rule fixed before the run, validation only):** keep ERA5 only if the best ONI + ERA5 model has a lower mean validation RMSE than the best ONI-only model (0.488) and is not worse at leads 1 to 3. Result: kept. Linear regression with ERA5 (0.436) beats linear regression ONI only (0.488) and is better at leads 1, 2 and 3. The 1979 versions are a check, not candidates.
- **ERA5 test scores (second look at the test years):** scored only after the decision, fitted on 1950 to 2016. The test years were already scored once above, so this is a second look; say so in the presentation. Linear regression test RMSE, ONI only vs ONI + ERA5: mean 0.409 vs 0.382, lead 1 0.107 vs 0.102, lead 6 0.664 vs 0.625. MAE mean 0.336 vs 0.318.

## 8. API

- `GET /api/forecast` returns the output described in section 2. The optional `year` query is described in section 12.
- It loads a saved model from `backend/app/saved_models/`. It never trains on request.
- If the saved model or the processed ONI file is missing, it returns 503 with a message to run `python -m app.layer1_forecast.train` first.
- The model and the ONI file are read on every request, so a retrained model is used without restarting the server.
- Training runs from a separate script, `train.py`, and saves the best model.

## 9. Files

- `backend/main.py`: the FastAPI app. It stays at the backend root and includes the forecast route.
- `backend/app/data/load_enso.py`: loads two files (NOAA ONI and the Kaggle file), cleans them, and joins them on the month.
- `backend/app/layer1_forecast/labels.py`: builds status, strength, duration, and start labels.
- `backend/app/layer1_forecast/models.py`: model definitions.
- `backend/app/layer1_forecast/train.py`: trains, compares, and saves.
- `backend/app/api/forecast.py`: the route.
- `backend/app/layer1_forecast/features.py`: lag features, targets, and the split.
- `backend/app/data/load_era5.py` (planned, section 13): ERA5 box averages.
- `notebooks/01_explore_enso.ipynb` and `notebooks/02_model_comparison.ipynb`.

## 10. Done When

- Our ONI values come from NOAA's `oni.ascii.txt`. The Kaggle ONI column is compared with it, and the differences are reported.
- Labels are built, and the known events (1982 to 83, 1997 to 98, 2015 to 16, 2023 to 24) are detected correctly. The event that began in May 2026 is detected and labelled ongoing.
- At least the baseline, logistic regression, Random Forest, and XGBoost are trained and compared in one table.
- The best model is saved, and `GET /api/forecast` returns every field in section 2.
- When an event is underway, duration is returned as a range from the lower band to the upper band. If the high end is open, it is reported as "from L months to at least H months". When no event is underway, duration is null.
- Metrics are reported on the untouched test period.

## 11. Open Items

- Part A (section 12): decided. Hindcast anchor March, years 1960 to 2100, no year input in the front end for now.
- Part B (section 13): confirm which ERA5 variables and box were actually requested, once the download finishes.

## 12. Part A: Optional Target Year

**Request:** `GET /api/forecast?year=YYYY`. `year` is optional. Without it, nothing changes. Let B be the newest ONI month (now September 2026) and B+6 the last forecast month (now March 2027).

**Three modes, picked from the year:**

| Mode | Years (now) | Rule | What it returns |
| --- | --- | --- | --- |
| `hindcast` | 1960 to 2025 | year before B's year | What the system would have forecast at the time, next to what really happened |
| `forecast` | 2026 and 2027 | B's year to B+6's year | The normal forecast, unchanged |
| `climatology` | 2028 to 2100 | after B+6's year | The historical average for each month, labelled as an average, not a forecast |

Years outside 1960 to 2100 return 422 (FastAPI's "invalid input" error).

- **Why 1960:** the hindcast model for 1960 is trained on ONI from 1950 up to March 1960. Anchors start in December 1950 (the first with 12 months of lags), so lead 6 has about 106 rows (to September 1959) and lead 1 about 111. That is enough for linear regression, the chosen model. Earlier years would have too few rows.
- **Why 2100:** climatology gives the same answer for every later year, so the limit is only there to reject typing mistakes.
- **Edge cases of the rule:** the year limits move with B. If B is June or earlier, B+6 is in B's own year, so the next year is already climatology. If B is December, the forecast covers January to June of the next year. In forecast mode, every year in the range returns the same 6 months, and `note` says which months they are. The observed part of B's year is not hindcast; it is shown as observed ONI in the normal forecast.

**Every response with `year` adds:**

- `mode`: `hindcast`, `forecast`, or `climatology`
- `target_year`: the year asked for
- `note`: one sentence that says what the numbers are (for example "Average of 1950 to 2025, not a forecast.")

**Fields by mode** (no year = the response today, unchanged):

| Field | No year | `forecast` | `hindcast` | `climatology` |
| --- | --- | --- | --- | --- |
| section 2 fields | yes | yes | yes, as known at the anchor month | absent |
| `mode`, `target_year`, `note` | absent | yes | yes | yes |
| `observed_oni` in each `forecast_series` month | absent | absent | yes | absent |
| `climatology` (12 rows) | absent | absent | absent | yes |

Absent means the key is not in the response, so the existing front-end types and the Layer 2 and 3 callers do not change. Climatology returns only `mode`, `target_year`, `note`, `model_used` ("climatology (no model)"), and `climatology`.

**Forecast mode:** the same fields as without `year`. The 6 forecast months may cover only part of the year (now October 2026 to March 2027). Months past B+6 are not filled in.

**Hindcast mode:**

- Anchor month: March of the target year (decided). The forecast covers April to September, leads 1 to 6, the same as the live forecast. Most El Niño events start between April and June (1982, 1997, 2015, 2023), so this window shows whether the system would have seen the start coming. A December anchor would cover only January to June and miss most of the growth. Spring forecasts are known to be the hardest (the "spring predictability barrier"), so expect weaker skill than the live forecast's average.
- Uses only ONI up to the anchor month. Events, start, duration, and strength are worked out from that cut table with the same rules as the live forecast (section 5).
- Each `forecast_series` month also has `observed_oni`: what really happened, for comparison.
- **No leakage:** the saved model was refitted on all data up to 2026, so it has already seen every past year. Using it would make hindcasts look better than they really are. Instead, `train.py` also fits the chosen model once per hindcast year, on the ONI table cut at that year's anchor month (all rows with known targets, as for the live model, so every target used is at or before the anchor), and saves these in the model file. The route still never trains on request (section 8).
- The confidence band uses the same validation RMSE as the live forecast. For early years with little training data, the real error is likely larger. Say so in the presentation.
- `model_used` is the chosen model's name with "(hindcast)" added.
- **Limits to state in the presentation:** the model type (linear regression) and the band RMSE were chosen and measured on 2009 to 2016, so hindcasts up to 2016 use a choice made with later data, and for 2009 to 2016 the band was measured on the same years. NOAA also recomputes past ONI with updated base periods and sea temperature data, so the inputs are slightly cleaner than what forecasters had at the time. No test can catch this.

**Climatology mode:**

- Built from observed ONI, all full years 1950 to the year before B (now 1950 to 2025).
- For each calendar month (January to December): `mean_oni`, and the share of years in El Niño, neutral, and La Niña status in that month (`el_nino_share`, `neutral_share`, `la_nina_share`, each 0 to 1).
- Also `event_start_share`: the share of years in which an El Niño event (five-season rule) started in that calendar month. Summed over the 12 rows, it is the share of years with an event start.
- ONI is an anomaly, so `mean_oni` is close to 0 in every month. The status shares are the useful part. This is why the label says "average, not a forecast".
- Returned as `climatology`: a list of 12 rows, one per month. The other fields are absent (see the fields table).

**Model file:** the hindcast models are stored in the same `oni_forecast.joblib`, keyed by year. An older model file without them returns 503 with the retrain message, not a 500 error.

**Code reuse:** `forecast_from_bundle` gets the ONI table and the models per lead as inputs, so the live forecast and the hindcast share one code path. Its callers (`api/forecast.py`, `layer2/impact.py`, `layer2/map_output.py`, `simulation/simulate.py`) keep the same result.

**Files:** `backend/app/api/forecast.py` (route, mode choice), `backend/app/layer1_forecast/outputs.py` (climatology rows), `backend/app/layer1_forecast/train.py` (hindcast models). Layer 2 and Layer 3 keep calling the forecast without `year`. The front end does not use `year` for now; it can be tried through FastAPI's `/docs` page (decided: no year input in the front end for now).

**Done when:** each mode returns the fields above, the hindcast models never use data after their anchor month (checked by a test), the route without `year` returns the same result as before, and tests cover the year limits and the mode boundaries.

## 13. Part B: ERA5 Pacific Features

**Status:** files downloaded and checked (section 4). `load_era5.py` builds `era5_monthly.csv`, `features.add_era5_lags` joins it, and `compare_era5.py` ran the comparison: ERA5 is kept (section 7). Saving the ERA5 model, the fallback, and `era5_used` are not built yet.

**Goal:** add a few ERA5 Pacific features to the existing ONI models (linear regression, Random Forest, XGBoost) and keep them only if they lower the validation RMSE. Logistic regression is only a comparison model (section 5), so it stays on ONI only. The CNN on ERA5 maps stays a separate optional item.

**Features:** box averages, one number per month each, turned into anomalies (the value minus that calendar month's average):

| Feature | ERA5 variable | Box |
| --- | --- | --- |
| `era5_sst_nino34` | sea surface temperature | Niño 3.4: 5°S to 5°N, 170°W to 120°W |
| `era5_u10_west` | 10 m eastward wind (u) | Western equatorial Pacific: 5°S to 5°N, 120°E to 180° (westerly wind bursts often come before El Niño) |
| `era5_mslp_diff` | mean sea level pressure | Tahiti box (15°S to 20°S, 147°W to 152°W) minus Darwin box (10°S to 15°S, 128°E to 133°E), an ERA5 version of SOI |
| `era5_tp_central` | total precipitation | Central equatorial Pacific: 5°S to 5°N, 170°E to 140°W |

- **Anomaly base period:** the monthly averages use the train years only (1950 to 2008), so no later data leaks into the features. For the 1979 check the normals use 1979 to 2008 instead (`add_anomalies(table, base_first_year=1979)` on the raw columns).
- **Units of the raw box averages:** `sst_nino34_rel_k` in kelvin (a difference, so the same as °C), `u10_west_ms` in m/s (positive = wind blowing east), `mslp_diff_hpa` in hPa (Tahiti minus Darwin; ERA5 gives Pa), `tp_central_mm_day` in mm per day. ERA5 monthly tp is the average daily total in metres (the file says only "m"), so it is multiplied by 1000. Check: the central box averages 3.7 mm/day, which fits a daily rate, not a monthly one.
- **Preliminary months:** the `preliminary` column is True for ERA5T months (`expver` 0005). With lag 1 and lag 3, they only reach anchor months from September 2026 on. Right now that is one test row (anchor 2026-09), which is the live forecast row and has no observed targets, so it is never scored. No train or validation row uses them. Check this again whenever the data is updated.
- **Newest month:** ERA5 runs to October 2026, one month past ONI (September 2026), so ERA5 currently reaches month B.
- **Warming trend:** the Pacific is warming, so a fixed 1950 to 2008 base makes the SST anomaly run warm in later years, while ONI uses moving base periods. `era5_sst_nino34` is therefore the Niño 3.4 average minus the 20°S to 20°N average over the whole box (a relative index, the same idea as NOAA's RONI). No trend line has to be fitted.
- **Grid conventions:** ERA5 files from the Copernicus store usually store latitude from north to south, so latitude is selected as `slice(5, -5)`. Longitude may be -180 to 180 or 0 to 360. Check the files before selecting, or the selection comes back empty.
- **Joining the two files:** the west file (120°E to 180°) and the east file (180°W to 70°W) are joined on longitude. First convert both to 0 to 360 (180°W to 70°W becomes 180 to 290), then join them, so the Pacific is one grid from 120 to 290 with no break at the date line. The 180° column is in both halves: it must match in every variable and every month (the loader stops if not), then it is kept once. Check that the variables, years, months, and preliminary flags match before joining. The central rainfall box (170°E to 140°W) crosses the date line, so it needs the joined grid. In 0 to 360 the boxes are: Niño 3.4 190 to 240, western wind 120 to 180, Tahiti 208 to 213, Darwin 128 to 133, central rainfall 170 to 220.
- **Data quality changes over time:** ERA5 wind and rainfall before 1979 (before satellites) are less reliable, and its SST source changes around 2007, near the train and validation boundary. Run the comparison once more with ERA5 starting in 1979 as a check, and drop `era5_tp_central` if it does not help. **Result (validation only, `compare_era5 tp_check`):** `era5_tp_central` is kept. Best mean validation RMSE with it 0.436 (linear regression), without it 0.445 (linear regression). It helps linear regression at leads 1 to 5 and ties at lead 6. Decided: ERA5 is used from 1950, not 1979 (the 1979 run stays a check). No other feature is checked this way, and the test years were not looked at again.
- **Lags:** each feature at lag 1 and lag 3, using the same anchor rule as ONI (section 6). Every feature is at or before B.
- **Years:** 1950 onward, so the rows match the ONI rows. ERA5 starts in 1940; the extra years are not used.
- **Processing:** `backend/app/data/load_era5.py` reads the NetCDF files with xarray, averages each box (weighted by cos(latitude), because grid cells shrink toward the poles; land cells are left out), and saves `data/processed/era5_monthly.csv` with `date`, `preliminary`, the four raw columns, and the four anomaly columns. Raw and processed files stay gitignored. Run it from backend/ with `python -m app.data.load_era5` (about 25 seconds; it loads the whole grid, about 2.5 GB of data, into memory). Checked: no gaps, anomalies average 0 in 1950 to 2008, and correlations with ONI are 0.91 (SST), 0.59 (wind), -0.73 (pressure difference; 0.96 with SOI), and 0.80 (rain).
- **Join:** `features.add_era5_lags` adds the ERA5 lags to the `build_features` rows, matched by date (lag 1 = ERA5 at B, lag 3 = ERA5 at B-2). Rows missing any ERA5 lag are dropped. With ERA5 from 1950 this drops no rows (train 691, validation 90, test 117; ERA5 starts before the first anchor, 1950-12, and ends after the newest, 2026-09). For the 1979 check it drops 339 train rows (train starts at anchor 1979-03, 352 rows left) and no validation or test rows. A test checks that changing any ERA5 or ONI value after B leaves row B unchanged.
- **Live forecast when ERA5 is behind (decided):** if ERA5 is kept but does not reach month B, the route falls back to the ONI-only forecast. It does not return an error. The response says which version ran in a new field, `era5_used` (true or false). This replaces the earlier suggestion of a 503 error, because a 503 would also stop Layer 2 and Layer 3, which build on the same forecast. With the fallback they keep working on the ONI-only forecast.
- **What `train.py` saves when ERA5 is kept:** the chosen ERA5 model and the best ONI-only model (the current choice rule applied to the ONI-only scores), each with its own validation RMSE per lead for the band. `model_used` names the model that actually ran.
- **`era5_used` in each mode:** present in the response without `year`, in `forecast` mode, and in `hindcast` mode. Absent in `climatology` (no model). If ERA5 is not kept, it is always false. Adding this key is the one change to the response without `year`; it does not break the existing front-end types.
- **Hindcast:** past years always have ERA5, so hindcasts use the ERA5 version when ERA5 is kept.

**Comparison (same split, same metrics):**

- Every regression model is scored twice on validation: ONI lags only, and ONI lags plus ERA5, with MAE and RMSE per lead. Both versions are scored on the same rows (months where both ONI and ERA5 exist). MAE and RMSE per lead, and accuracy and a confusion matrix for logistic regression.
- The model choice rule does not change (lowest mean validation RMSE, section 7). ERA5 is kept only if a model with ERA5 wins.
- **Test period:** the test years were already scored once (section 7). Scoring them again for the ERA5 models is a second look. The choice is still made on validation only, before the new test scores exist, and the presentation says the test period has been used twice.
- If ERA5 is kept, the hindcast models (section 12) use the same features.

**Size check:** confirm the real file size and the months covered before processing.

**Done when:** `era5_monthly.csv` is built and checked (no gaps, anomalies near 0 on average in the train years), the comparison table shows every model with and without ERA5, the choice is written in section 7, the API still returns every field plus `era5_used`, and a test shows the fallback to ONI only when ERA5 does not reach month B.