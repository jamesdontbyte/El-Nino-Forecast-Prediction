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
- `duration_months`: only when an event is underway; null when no event is underway. A range (low and high), not a single number. It counts the months already observed plus the forecast months. The low end comes from the lower confidence band and the high end from the upper band. When `duration_open_ended` is true, the high end is a minimum, reported as "from L months to at least H months".
- `duration_open_ended`: true or false. True when the upper band is still at +0.5 or above in the last forecast month, so the true end of the event is unknown.
- `strength`: weak, moderate, or strong
- `forecast_series`: the predicted ONI value for each of the next 1 to 6 months, with a confidence range
- `model_used`: the name of the model that produced the result

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
| ERA5 monthly data, Pacific box, full time range | Extra features and the CNN | Source confirmed. Variables and box to finalize. |
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

**ERA5 request (suggested):** sea surface temperature, 10 m wind (u and v), mean sea level pressure, and total precipitation. Pacific box about 30°S to 30°N and 120°E to 70°W. Monthly means, 1940 to the latest month. Confirm the real file size before downloading.

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

**Open-ended duration:** if the upper band is still at +0.5 or above in the last forecast month, the true end is unknown. Set `duration_open_ended` to true and report the duration as "from L months to at least H months".

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
- Skill drops with lead time. Report that honestly, and do not hide the longer lead times.

## 8. API

- `GET /api/forecast` returns the output described in section 2.
- It loads a saved model from `backend/app/saved_models/`. It never trains on request.
- Training runs from a separate script, `train.py`, and saves the best model.

## 9. Files

- `backend/main.py`: the FastAPI app. It stays at the backend root and includes the forecast route.
- `backend/app/data/load_enso.py`: loads two files (NOAA ONI and the Kaggle file), cleans them, and joins them on the month.
- `backend/app/layer1_forecast/labels.py`: builds status, strength, duration, and start labels.
- `backend/app/layer1_forecast/models.py`: model definitions.
- `backend/app/layer1_forecast/train.py`: trains, compares, and saves.
- `backend/app/api/forecast.py`: the route.
- `notebooks/01_explore_enso.ipynb` and `notebooks/02_model_comparison.ipynb`.

## 10. Done When

- Our ONI values come from NOAA's `oni.ascii.txt`. The Kaggle ONI column is compared with it, and the differences are reported.
- Labels are built, and the known events (1982 to 83, 1997 to 98, 2015 to 16, 2023 to 24) are detected correctly. The event that began in May 2026 is detected and labelled ongoing.
- At least the baseline, logistic regression, Random Forest, and XGBoost are trained and compared in one table.
- The best model is saved, and `GET /api/forecast` returns every field in section 2.
- When an event is underway, duration is returned as a range from the lower band to the upper band. If the high end is open, it is reported as "from L months to at least H months". When no event is underway, duration is null.
- Metrics are reported on the untouched test period.

## 11. Open Items

- Finalize the ERA5 variables and region box before downloading.