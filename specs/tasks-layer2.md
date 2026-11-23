# Layer 2 (impact and land view)

## Decisions already made
- [x] Data sources chosen and downloaded: PSA crop tables, CHIRPS rainfall, province shapes.
- [x] Matching on the 3-digit province part checked.
- [x] City rows checked against region totals.
- [x] Cleaning rules decided for Negros, Sulu, Maguindanao, Davao Occidental, cities, and zero area.

## To do
- [x] notebooks/03_explore_layer2.ipynb: count usable data per province and crop, and look at rainfall.
- [x] Decide the minimum data: 10 years per province, crop and quarter.
- [x] Decide the rule for turning ten-day rainfall into quarters: quarter total over quarter normal.
- [x] Decide what "normal" means: it follows the yield trend.
- [x] BARMM gap from 2023 on: left out for now.
- [ ] Decide the exact trend method for the normal yield.
- [ ] Decide the dryness colour thresholds.
- [x] Build the lookup table in backend/app/data/ (committed).
- [x] Crop loader with the cleaning rules.
- [x] Rainfall loader.
- [x] Tests for the cleaning rules.

## Later
- [ ] Baseline model, then other models, on the same split.
- [ ] Map output (colours per province).
- [ ] API route for Layer 2.
