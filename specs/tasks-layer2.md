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
- [ ] Decide the open items in section 10 (rainfall source, prediction view, normal period).
- [ ] Step 1: zoom to the chosen province (front end, see tasks-frontend.md).
- [ ] Step 2a: download the CHIRPS grid for the Philippines (data/ is gitignored).
- [ ] Step 2b: preprocessing script: municipal quarterly rain % to data/processed/, with the province check.
- [ ] Step 2c: new routes `/api/municipal_shapes` and `/api/municipal_map`, with new tests (1,642 shapes, codes match). Existing routes and tests unchanged.
- [ ] Step 2d: front end colours municipalities, yield labelled "province estimate", card rain labelled "province rainfall".
- [ ] Step 3 (optional): cropland mask. Source to be decided.
