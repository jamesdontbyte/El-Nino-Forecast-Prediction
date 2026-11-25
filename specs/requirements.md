# Project Requirements: El Niño Prediction System

**Working title:** An AI-Driven Predictive Simulation of El Niño Impact on Philippine Agriculture

**Status:** working draft. Algorithms, datasets, and thresholds may change after testing.

## 1. Project Basics

- **Course theme:** Predicting the Future: The Power of AI and ML
- **Project type:** Python-based machine learning application
- **Development approach:** flexible machine learning algorithm selection
- **Required outputs:** a functional application, source code, and a project presentation
- **Dataset expectation:** the professor wants students to handle a large amount of data. No minimum size was given.

## 2. Goal and Scope

The system forecasts El Niño conditions, estimates the effect on crops in a chosen Philippine province, and simulates how policy choices change the outcome.

**In scope:** El Niño forecast, province and crop impact with a map view, and a rule-based policy simulation. Agriculture is the focus.

**Out of scope:** disease prediction, a separate drought-risk feature, and reservoir monitoring. Sentinel satellite data is optional and not part of the core plan.

## 3. Tech Stack

- **Back end:** Python with FastAPI, run with Uvicorn
- **Front end:** React, TypeScript, Tailwind CSS, built with Vite. Plan in `specs/frontend.md`.
- **Map:** Leaflet (react-leaflet) with OpenStreetMap tiles. Province shapes come from `GET /api/shapes` (planned), so the map works without the tiles.
- **Data and ML:** pandas, NumPy, xarray, netCDF4, scikit-learn, XGBoost. TensorFlow or PyTorch only if the LSTM or CNN is added.
- **Notebooks:** Jupyter, for experiments only. Not part of the running app.
- **Rule:** all machine learning and data processing live in the back end. React only sends inputs and displays results.

## 4. User Inputs

- Province in the Philippines
- Crop (for example rice or corn)
- Policy choices: irrigation support and crop switching (on or off), and optionally the pump share, switch share and irrigation gain (defaults 20%, 10% and +3.6 points)

The user does not pick the forecast date, horizon, or model. The system works those out.

## 5. What the System Predicts

### Layer 1: El Niño forecast

The forecaster works in two cases:

- **No event underway:** whether an El Niño is coming, when it starts, and how strong it will be.
- **Event underway (the case now, since May 2026):** that it is active, its observed start month, and a forecast of how strong it gets and how long it lasts. Duration counts the months already observed plus the forecast months, as a range. The low end comes from the lower confidence band and the high end from the upper band. If the upper band stays at +0.5 or above through every forecast month, the true end is unknown, so duration is reported as "from L months to at least H months" and the API marks it as open-ended (true or false). If the lower band also stays at +0.5 or above throughout, it is reported as "at least N months".

Duration is only given when an event is underway. When no event is underway, it is empty (null).

The API also returns whether an event is underway (true or false).

**How targets are defined (built from the ONI index):**

- A month counts as El Niño when ONI is +0.5 or above, La Niña at -0.5 or below, otherwise neutral.
- Strength uses the peak ONI of the event (weak, moderate, strong). The cutoffs are a common convention, not official NOAA categories.
- Duration applies only to events that meet the five-season rule (five consecutive overlapping three-month periods at +0.5 or above). It is the number of months within the event where ONI is at or above +0.5. Shorter spells are not events and have no duration.
- Duration is the weakest prediction because there are few past events. Show it as a range, not one number.

### Layer 2: Impact on the chosen province and crop

- Expected change in rainfall for the province
- Expected change in crop yield for the chosen crop, against the province's own normal
- Crops: palay (irrigated, rainfed, total) and corn (white, yellow, total)
- Details are in `specs/layer2-impact.md`.
- **Land view:** a map of the province showing how the land would look under El Niño

**Land view details:**

- One flat 2D map with a toggle or slider between two views: a normal year (real past data) and the El Niño prediction.
- Colors show predicted dryness or stress: green healthy, yellow stressed, red severe.
- The user can also compare a past El Niño year (for example 2015 or 2023) against the prediction.
- Build order: first a rainfall-based dryness map with each province coloured as a whole shape, using CHIRPS rainfall. Optionally upgrade later to Sentinel vegetation data (NDVI). The interface stays the same either way.
- Colour bands use PAGASA rainfall categories (rainfall percent of normal): red 40% or less, yellow 41-80%, green above 80%.

### Layer 3: Simulation outcome

- Rule-based agents (farmers, local government) start from the Layer 2 results.
- The user toggles policy choices and runs the simulation.
- Output: outcomes with and without intervention, side by side.
- No machine learning in this layer.
- Policies: irrigation support and crop switching only. Both apply in 2027 Q1 only, because the 2026 Q4 crop is already planted. When both are on, irrigation goes first.
- Units: yield only (% of normal and t/ha). No pesos.
- About 100 farmer agents with a fixed random seed, so the same inputs give the same result.
- API route: `GET /api/simulate`.
- Details are in `specs/layer3-simulation.md`.

## 6. Datasets and Algorithms

The algorithm list is a plan and might change.

| Layer | Dataset | Source | Size | Status | Algorithms (plan) |
| --- | --- | --- | --- | --- | --- |
| 1 | ERA5 monthly data, Pacific region only (sea surface temperature, wind, pressure, rainfall) | Copernicus Climate Data Store | About 4 GB (estimate) | Confirmed source. Variables and region box still to finalize. | CNN (reads the maps), LSTM, XGBoost, Random Forest |
| 1 | ONI index, 1950 to September 2026 (primary ONI source for labels, targets, and lag features) | NOAA (`oni.ascii.txt`) | About 920 rows | Confirmed. Downloaded. | Linear regression (baseline), logistic regression (El Niño, neutral, La Niña label), Random Forest, XGBoost, LSTM |
| 1 | ENSO monthly indices, 1950 to May 2026 (RONI, Niño 3.4 anomaly, SOI; its ONI column is only compared with NOAA). ONI and RONI end in April 2026; Niño 3.4 anomaly and SOI end in May 2026. | Kaggle | About 900 rows | Confirmed. Secondary source. SOI matches NOAA's `soi.txt` exactly. | Same as the ONI row (extra features) |
| 1 | Equatorial Pacific buoy readings (TAO array) | Kaggle, El Nino Dataset | About 178k rows, 1980 to 1998 | Found, not yet opened. Check years and missing values. | XGBoost, LSTM |
| 2 | Philippine palay and corn area and production by province, quarterly, 1987 to 2026 (4 tables) | PSA OpenSTAT | 327 rows per table | Downloaded, checked. | Departure line (chosen for yield change; linear regression, Random Forest and XGBoost compared) |
| 2 | Philippine rainfall by province, every ten days, 1981 to 2026 | CHIRPS | One row per ten days for 17 regions and 81 provinces | Downloaded, checked. | XGBoost (chosen for rainfall; province line and Random Forest compared) |
| 2 | Province shapes (map) | philippines-json-maps | 18 files, 88 shapes | Downloaded, checked. | Not applicable |
| 2 | Sentinel vegetation data (optional) | Copernicus Sentinel | Not yet known | Optional. Only if the core works. | CNN or Random Forest on NDVI |
| 3 | Layer 2 outputs as starting conditions | Generated by the system | Not applicable | Not applicable | None (rule-based agents) |
| 3 | Crop gap table (median El Niño yield change per crop type and rain colour) | Built from the PSA crop tables (Layer 2) | 6 crop types x 3 colours | Built with the 2-of-3-months rule. Approved. | None (medians) |

ERA5 is gridded numerical data in NetCDF format, not photos. It is cut to the Pacific box (about 30°S to 30°N and 120°E to 70°W) and to the needed variables, keeping the full time range. Confirm the real size when placing the request.

The buoy data ends in 1998, so it is useful for learning but does not count toward the large-data goal. ERA5 is for Layer 1 only. Layer 2 uses quarterly crop data, so rainfall is turned into the same quarters. CHIRPS uses old province boundaries (for example Maguindanao and Davao del Sur), so some provinces are merged. See `specs/layer2-impact.md` for the matching and cleaning rules.

## 7. Evaluation

- Models that predict the ONI value are compared on MAE and RMSE. The status classifier is compared on accuracy and a confusion matrix. All models use the same split. Justify the final choice in the presentation.
- Always include a simple baseline (linear regression) to beat.
- Drop models that do not help.
- State clearly that the simulation shows possible scenarios, not certain outcomes.

## 8. Build Order

1. Project skeleton and back end (done: folders, .venv, FastAPI /health route).
2. Layer 1: load ENSO data, build labels, train baseline, compare models.
3. Add ERA5 Pacific data and the deep learning models if time allows.
4. Layer 2: impact model and the rainfall-based land view map.
5. Layer 3: rule-based simulation.
6. React front end connected to the API.
7. Presentation.

## 9. Open Items

- Confirm the final ERA5 variables and region box.
- Decide whether to add the Sentinel upgrade for the land view.
- Layer 3 (details in `specs/layer3-simulation.md`): the policy list is decided (irrigation support and crop switching). The pump share (default 20%), switch share (default 10%) and irrigation gain (default +3.6 points, estimated from two strong El Niños, not statistically firm) are stated assumptions the user can change. The irrigated share rule and the crop gap table are decided. Open: what the policy timing becomes when the forecast quarters move.
- Layer 2 (details in `specs/layer2-impact.md`): no open items left. Decided: what the "normal year" map shows, how the Layer 1 forecast becomes Layer 2 inputs (observed ONI months where available, Layer 1 forecast otherwise), the lag (the yield model uses this and last quarter's inputs), the algorithms (XGBoost for rainfall, the departure line for yield) and the API routes (`GET /api/options`, `GET /api/map`, `GET /api/impact`).
