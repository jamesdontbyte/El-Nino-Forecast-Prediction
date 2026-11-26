# Layer 2 (impact and land view)

## Decisions already made
- [x] Data sources chosen and downloaded: PSA crop tables, CHIRPS rainfall, province shapes.
- [x] Matching on the 3-digit province part checked.
- [x] City rows checked against region totals.
- [x] Cleaning rules decided for Negros, Sulu, Maguindanao, Davao Occidental, cities, and zero area.

## To do
- [x] notebooks/03_explore_layer2.ipynb: count usable data per province and crop, and look at rainfall.
- [x] Decide the minimum data: the 10 years before the year being scored must all have a yield.
- [x] Decide the rule for turning ten-day rainfall into quarters: quarter total over quarter normal.
- [x] Decide what "normal" means: it follows the yield trend.
- [x] BARMM gap from 2023 on: left out for now.
- [x] Decide the exact trend method for the normal yield: straight line through the previous 10 years.
- [x] Decide the dryness colour thresholds: PAGASA rainfall bands.
- [x] notebooks/04_normal_and_colours.ipynb: compare trend fits and colour options.
- [x] Split: train 1987-2008, validate 2009-2016, test 2017-2026.
- [x] El Nino quarter rule: at least 2 of 3 months inside an event.
- [x] Build the lookup table in backend/app/data/ (committed).
- [x] Crop loader with the cleaning rules.
- [x] Rainfall loader.
- [x] Tests for the cleaning rules.

## Later
- [x] Baseline model, then other models, on the same split.
- [x] Map output (colours per province).
- [x] API route for Layer 2.

## Map upgrade (specs/layer2-impact.md, section 11)
Commit and push after each task.
- [x] Check the municipal shapes: 88 files, 1,642 shapes, every province shape covered, codes match the lookup.
- [x] Decide the open items in section 10: CHIRPS grid, prediction view option (a), normal period matching `rfh_avg`.
- [x] Look up the CHIRPS grid download route and size, and the `rfh_avg` years. Show the user before downloading.
- [x] Check CHC for 2025-2026 monthly files: found yearly NetCDF files (164 + 137 MiB).
- [x] Download the CHC 2025 and 2026 yearly files, cut to the Philippines (`data/raw/philippines/chirps_chc/`, 2026 ends in October). January and February 2025 are identical to ERDDAP.
- [x] Province check: rebuild the 81 province quarters from the grid and compare with the CSV. The 1989-2018 normal is confirmed (`python -m app.layer2.grid_rain`, test in tests/test_grid_rain.py).
- [x] Step 1: zoom to the chosen province (front end, see tasks-frontend.md).
- [x] Step 2a: download the CHIRPS grid for the Philippines, 1981-01 to 2025-02, from ERDDAP in 5 parts (174 MB, `data/raw/philippines/chirps_grid/`, gitignored).
- [x] Step 2b: preprocessing script `python -m app.layer2.municipal_rain`: municipal quarterly rain % to data/processed/municipal_rain_quarterly.csv. 1 municipality (Kalayaan) has no value.
- [x] Step 2c: new routes `/api/municipal_shapes` and `/api/municipal_map`, with new tests (1,642 shapes, codes match). Existing routes and tests unchanged.
- [x] Step 2d: front end colours municipalities, yield labelled "province estimate", card rain labelled "province rainfall" (browser click-through still to do by the user).
- [ ] Step 3 (optional): cropland mask. Source to be decided.
