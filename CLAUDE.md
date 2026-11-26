# CLAUDE.md

Read specs/requirements.md for the full requirements. Keep it in sync with the code, and update it when a decision changes.

## Project
An AI-Driven Predictive Simulation of El Niño Impact on Philippine Agriculture.
Course final project. Theme: "Predicting the Future: The Power of AI and ML".
Required output: a functional application, source code, and a presentation.

## Stack
- Back end: Python with FastAPI
- Front end: React, TypeScript, Tailwind CSS, built with Vite (plan in specs/frontend.md)
- Map: Leaflet (react-leaflet) with OpenStreetMap tiles
- ML: pandas, xarray, scikit-learn, XGBoost; TensorFlow or PyTorch only if the LSTM or CNN is added

## Rules
- All machine learning and data processing live in the Python back end. React only sends inputs and displays results.
- Start with simple ML, get the whole app working, then add deep learning if time allows.
- Keep it simple. Do not add features that were not asked for.
- Never commit data files. The data folder is gitignored.
- The hand-made province lookup table in backend/app/data/ is reference data written by hand. It is committed.
- The plan is a working draft. Algorithms and datasets may change after testing. Compare models on the same metrics: MAE and RMSE for models that predict a number, accuracy and a confusion matrix for classifiers.

## What the user inputs
- The user picks a province in the Philippines, a crop, and policy choices (for example irrigation support, subsidy, crop switching).
- The user does not pick the forecast date, horizon, or model. The system works those out.
- Exception: the user may give an optional target year on the forecast. The system still picks the start month, the horizon, and the model.

## Layers
Details for each layer are in specs/requirements.md.
1. **El Niño forecast.** Reports whether an El Niño is underway. If none, predicts whether one is coming, when it starts and how strong it will be. If one is underway, gives the observed start, then forecasts how strong it gets and how long it lasts.
2. **Impact and land view.** Predicts rainfall and crop yield change for the chosen province and crop, and shows it on a map.
3. **Simulation.** Rule-based, no ML. Compares outcomes with and without the chosen policies.

## Structure
- backend/ : main.py (the FastAPI app) and app/ with data/ (loading), layer1_forecast/, layer2, simulation, api/ (routes), and saved_models/ (gitignored)
- frontend/ : React app, with a page per layer and a map component
- data/ : raw and processed datasets (gitignored)
- notebooks/ : experiments and model comparison
- specs/ : requirements notes

## Working style
- Keep responses concise unless asked otherwise.
- Read CLAUDE.md and the specs folder before planning or changing anything. The specs are the source of truth.
- Change mode: use sub-agents for implementation where possible and act as the coordinator. Run independent changes in parallel. Use premium models for complex code and mid-tier models for documentation.
- Before presenting a plan, have sub-agents review it from different angles.
- After finishing any feature, large or small, run the checks below.

## Checks
- Back end: run ruff and the tests (pytest) from backend/. pytest exit code 5 means no tests were found yet. It is not a failure. The first tests will be for the labels.
- Start the server from backend/ and confirm /health still returns ok.
- Before starting the API, run `python -m app.layer1_forecast.train` from backend/ so the saved model exists (saved_models/ is gitignored).
- Before starting the API, also run `python -m app.layer2.train` from backend/ so the Layer 2 models exist (about a minute).
- Front end (once it exists): run the type check, the linter, and the build.
- Report any failing check. Do not hide it.