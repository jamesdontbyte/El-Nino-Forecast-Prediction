# Layer 2 Spec: Impact and Land View

**Status:** draft. Items marked OPEN are not decided yet. Decide them after looking at the data in `notebooks/03_explore_layer2.ipynb`.

## 1. Purpose

Predict how El Niño changes rainfall and crop yield for the province and crop the user picks. Show the result on a map. Layer 3 starts from these results.

Yield change is measured against that province's own normal, not against other provinces.

## 2. Inputs and Outputs

**Input from the user:** a province and a crop. The user does not pick a date, horizon, or model.

**Input from the system:** the Layer 1 forecast. OPEN: how the forecast is turned into Layer 2 inputs.

**Crops:**

- Palay (rice): irrigated, rainfed, and total.
- Corn: white, yellow, and total.

**Outputs (exact fields to be decided):**

- Rainfall change for the province.
- Crop yield change for the province and crop, against the province's own normal.
- Map colours for the land view.

**Land view:**

- A flat 2D province map with a toggle between a normal year and the El Niño prediction.
- Colours show dryness: green healthy, yellow stressed, red severe.
- Provinces are coloured as whole shapes. There is no 25 km grid.
- The user can also compare a past El Niño year (for example 2015 or 2023).
- Shapes with no crop data are shown grey.
- OPEN: what the "normal year" map shows.
- OPEN: the dryness colour thresholds.

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
- Shapes with no crop data are shown grey: the NCR districts, City of Isabela, and Special Geographic Area.
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

Plan only. All of this is OPEN until tested.

- The plan in `specs/requirements.md` stays: Ridge regression, Random Forest, and K-Means (to group provinces).
- Start with a linear baseline. Other models must beat it.
- **Rainfall rule (decided):** for each province and calendar quarter, rainfall percent of normal = total rainfall in the quarter (sum of `rfh`) divided by its normal (sum of `rfh_avg`), times 100. This was chosen over averaging the ten-day `rfq` values because it does not soften dry quarters (Nueva Ecija 2015 Quarter 2: 57% with this rule, 70% with the average).
- **Normal (decided):** the normal yield follows the long-term trend, because yield rises strongly over 1987 to 2026. OPEN: the exact trend method.
- **Minimum data (decided):** 10 years per province, crop and quarter, because the normal is built per quarter. The app shows a prediction only for quarters that pass, and says "not enough data" for the others. At 10 years, 1,839 of 1,920 province, crop and quarter cells qualify (notebook 03).

## 7. Evaluation

- Models that predict a number (rainfall change, yield change) use MAE and RMSE.
- Always include a simple linear baseline to beat.
- Split by date, never randomly.
- Compare every model on the same split.

## 8. Files

Planned.

- `backend/app/data/`: the crop loader, the rainfall loader, and the lookup table.
- `notebooks/03_explore_layer2.ipynb`: counts usable data per province and crop, and looks at rainfall.

## 9. Done When

- The lookup table covers every crop province, CHIRPS PCODE, and shape, and the loader checks it.
- The crop and rainfall loaders follow the cleaning rules, with tests.
- A baseline and at least one other model are compared on the same split and metrics.
- The chosen province and crop return a rainfall change, a yield change, and map colours.
- The OPEN items above are decided and written down.

## 10. Open Items

- The dryness colour thresholds.
- The exact trend method for the normal yield.
- What the "normal year" map shows.
- How the Layer 1 forecast is turned into Layer 2 inputs.
- The final algorithms.
