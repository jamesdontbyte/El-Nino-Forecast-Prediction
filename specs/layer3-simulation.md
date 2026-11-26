# Layer 3 Spec: Policy Simulation

**Status:** draft. The policies, units, agents, timing, the two policy shares and the irrigation gain (assumptions with defaults the user can change) are decided. The crop gap table (section 4) is approved. The irrigated share rule and the irrigation gain rules are decided. Policies act in every forecast quarter after the first (built). The replay of "El Niño 2015-16" is built in the back end; its front end is not built yet (section 11).

## 1. Purpose

Show how policy choices change the El Niño outcome for the province and crop the user picks. Rule-based agents (farmers and the local government) start from the Layer 2 results. The result is shown side by side: without policies and with the chosen policies.

No machine learning in this layer. The results are possible scenarios, not certain outcomes, and the output says so.

## 2. Inputs and Outputs

**Input from the user:** a province, a crop (one of the 6 Layer 2 crops), and two on/off toggles: irrigation support and crop switching. Optionally, the three assumptions in section 5: `pump_share` and `switch_share` (each 0 to 1) and `irrigation_gain` (0 to 10 points).

**Input from the system:**

- The Layer 2 result for the province (from `province_impact` in `backend/app/layer2/impact.py`): for each forecast quarter, the yield change %, the rain colour, `enough_data`, and the normal yield in t/ha. Layer 3 needs the chosen crop plus Irrigated Palay, Rainfed Palay and Corn. The data and models are loaded once per request and `province_impact` is called for each crop (calling `load_impact` 4 times took 4.4 s).
- The crop gap table (section 4).
- The province's irrigated palay share (section 3).

**Units (decided):** yield only: yield change % of normal and t/ha. No pesos.

**Output:** see section 6.

## 3. Agents and Rules

**Farmers (decided):** about 100 farmer agents per run, with traits drawn from a fixed random seed. The same inputs always give the same result. Both runs (without and with policies) use the same farmers. Only the policies differ.

Farmer traits:

- **Crop type**, set from the chosen crop:
  - Palay: each farmer is irrigated or rainfed. The chance of irrigated is the province's irrigated share.
  - Irrigated Palay: every farmer is irrigated. Rainfed Palay: every farmer is rainfed.
  - White Corn, Yellow Corn, Corn: every farmer grows that corn type.

Which farmers get a pump or switch is also picked with the fixed seed.

**Irrigated share (decided):** irrigated palay area divided by total palay area (irrigated plus rainfed) in the province, from `load_crops()` (`crop_type`, `province`, `year`, `quarter`, `area_ha`). Use the most recent year where all 4 quarters have area and the total is above 0. Some provinces have no rainfed area in some quarters (for example Nueva Ecija), so a share of 100% must work.

**A farmer's result:** the Layer 2 yield change % for the province and quarter, plus the gap for the farmer's crop type in that quarter's rain colour (section 4).

- Layer 2's yield model has no crop input, so its yield change % is the same for every crop in a province and quarter. The crop gap is what makes crop types differ.
- So the "without" result for a single crop type (for example Rainfed Palay) is the Layer 2 number plus that type's gap. It can differ from `/api/impact` by the gap.
- t/ha = that crop type's normal yield x (1 + yield change / 100).

**Local government (one per run):** gives out pumps and issues the switching advice.

**Policy timing (decided):** both policies act in every forecast quarter after the first. The first quarter's crop is already planted, so neither pumps nor a crop switch can change it. In the first quarter, "with" equals "without". Pumps go to the same farmers in every policy quarter. (Status: built.)

**Irrigation support (decided: palay only):**

- The local government gives pumps to a share of the rainfed palay farmers: the pump share (section 5, default 20%). The number of farmers is the share times the number of rainfed palay farmers, rounded. The farmers are picked with the fixed seed.
- **Irrigation gain (decided: an assumption):** in red quarters, a farmer with a pump gets the rainfed palay result plus the irrigation gain (section 5, default +3.6 points). The default is the red-quarter gap between irrigated and rainfed palay in section 4, which is estimated from two strong El Niños and not statistically firm.
- **Other colours (decided):** in yellow and green quarters a pump adds nothing. Only the red gap was checked, and a pump matters most when rain is very low.
- **t/ha (decided):** a farmer with a pump keeps the Rainfed Palay normal yield. The Irrigated Palay normal comes from established irrigation (Nueva Ecija 2026 Q4: 5.95 t/ha against 4.85 rainfed), which a pump in one season does not give.
- In practice, help this fast means small pumps or shallow tube wells, not canals. The default gain comes from established irrigation, so it is an upper bound.

**Crop switching (decided: kept, expected to show no gain):**

- Only when the quarter's rain colour is red, the local government advises rainfed palay farmers to switch to corn.
- A share of the rainfed palay farmers switch to Corn (the total): the switch share (section 5, default 10%). The number is the share times the number of rainfed palay farmers, rounded. They are picked with the fixed seed from the rainfed farmers without a pump. If fewer farmers are left than the number, all of them switch.
- Switched farmers get the Corn gap and the Corn normal yield.
- The past data shows corn lost as much as rainfed palay in very dry El Niño quarters, with no difference between them (section 4). So switching is expected to give no gain. The simulation shows this honestly.

**Both on (decided):** irrigation goes first. Rainfed farmers who did not get a pump may then switch.

**Where the policies do not apply:**

- Corn crops (White, Yellow, Corn): no policy applies. There is no irrigated corn data, and corn is the switch target.
- Irrigated Palay: no policy applies, because there are no rainfed farmers.
- The output names the policies that did not apply and says why. It does not raise an error.

**Missing data (proposed):**

- If the chosen crop has `enough_data` false in a quarter, that quarter has no results, like Layer 2. Rain and colour are still returned.
- If Corn has `enough_data` false, switching is skipped for that quarter and the output says why. Pumps need only the Rainfed Palay data, which the farmers already use.

## 4. Crop Gap Table

The median yield change in past El Niño quarters, per crop type and rain colour, pooled over all provinces. A crop type's gap is its median minus the Palay (total) median in the same colour.

**How it is built (step 2):**

- Rows: the Layer 2 yield table (`load_tables()["yield"]` in `backend/app/layer2/features.py`), which covers 1997-2026 because the normal needs 10 past years.
- El Niño quarters: the 2-of-3-months rule (`quarter_phase` in `backend/app/layer2/map_output.py`, observed ONI only). There are 31 El Niño quarters in these years.
- Colour: `dryness_colour` on the observed rain % rounded to 1 decimal (the PAGASA bands, as on the map).
- Medians, not means, because a tiny normal gives huge percents (`specs/layer2-impact.md`).

An earlier rough check (quarter mean ONI of +0.5 or above) gave nearly the same numbers: counts moved by at most 2, and the Rainfed Palay red gap changed from -3.1 to -3.2.

Median yield change (% of normal) in El Niño quarters (number of province-quarters in brackets):

| Crop type | Red (40% or less) | Yellow (41-80%) | Green (above 80%) |
| --- | --- | --- | --- |
| Palay | -3.7 (158) | -0.5 (1,243) | -1.2 (902) |
| Irrigated Palay | -3.3 (156) | -0.3 (1,222) | -1.1 (886) |
| Rainfed Palay | -6.8 (130) | -1.4 (918) | -1.3 (656) |
| Corn | -6.8 (139) | -1.8 (1,158) | -1.9 (843) |
| White Corn | -7.8 (130) | -1.3 (1,081) | -2.4 (782) |
| Yellow Corn | -6.4 (100) | -2.3 (865) | -1.9 (655) |

Gaps from Palay (percentage points):

| Crop type | Red | Yellow | Green |
| --- | --- | --- | --- |
| Irrigated Palay | +0.4 | +0.2 | +0.1 |
| Rainfed Palay | -3.2 | -0.9 | -0.2 |
| Corn | -3.1 | -1.3 | -0.8 |
| White Corn | -4.1 | -0.7 | -1.3 |
| Yellow Corn | -2.8 | -1.8 | -0.7 |

What it shows: in red quarters, irrigated palay lost about half as much as rainfed palay. Corn did no better than rainfed palay.

Caution: the red cells are thin and come mostly from two quarters. Of the 158 red Palay rows, 46 are 1998 Q1 and 37 are 2016 Q1 (the two strong El Niños). The rest are spread over 9 quarters with 5 to 20 rows each.

**Check against normal variation** (`notebooks/06_crop_gap_check.py`). Red El Niño quarters, each crop against Rainfed Palay. The 95% intervals come from 10,000 bootstrap resamples of the difference in medians: once resampling rows, once resampling whole quarters, because provinces in the same quarter share the same weather. The p-value is from a two-sided Mann-Whitney rank test.

| Comparison | Rows | Gap (points) | 95% interval, rows | 95% interval, quarters | p-value |
| --- | --- | --- | --- | --- | --- |
| Irrigated Palay, all red quarters | 156 / 130 | +3.6 | -0.5 to +7.1 | -1.7 to +6.5 | 0.06 |
| Irrigated Palay, without 1998 Q1 and 2016 Q1 | 75 / 64 | -0.9 | -4.4 to +2.2 | -3.2 to +2.9 | 0.57 |
| Corn, all red quarters | 139 / 130 | +0.1 | -4.9 to +4.0 | -5.1 to +3.4 | 0.99 |
| Corn, without 1998 Q1 and 2016 Q1 | 64 / 64 | -2.5 | -7.5 to +2.3 | -6.8 to +4.2 | 0.30 |

- **The irrigation gain is uncertain and driven by two events.** The +3.6 gap is not clearly larger than normal variation, and without 1998 Q1 and 2016 Q1 it disappears. So the simulation treats the irrigation gain as an assumption (section 5), not as a data result.
- **Corn shows no gap.** In neither run is corn different from rainfed palay. This supports "switching shows no gain".

**Yellow quarters (checked November 2026, same script, same method).** Not used by the simulation: the irrigation gain still applies only in red quarters unless a graded gain (option B) is approved.

| Comparison | Rows | Gap (points) | 95% interval, rows | 95% interval, quarters | p-value |
| --- | --- | --- | --- | --- | --- |
| Irrigated Palay, all yellow quarters | 1,222 / 918 | +1.0 | +0.1 to +2.1 | -0.0 to +2.3 | 0.006 |
| Irrigated Palay, without 1998 Q1 and 2016 Q1 | 1,164 / 887 | +0.9 | +0.1 to +2.1 | -0.2 to +2.3 | 0.012 |
| Corn, all yellow quarters | 1,158 / 918 | -0.4 | -1.5 to +1.1 | -1.8 to +1.8 | 0.34 |
| Corn, without 1998 Q1 and 2016 Q1 | 1,106 / 887 | -0.6 | -1.5 to +1.0 | -2.0 to +1.8 | 0.47 |

- The yellow irrigated gap is small (about 1 point) but spread over 31 quarters (the largest, 2010 Q1, holds about 5% of rows) and barely moves without 1998 Q1 and 2016 Q1. The quarter-resampled interval touches 0, so it is likely real but only borderline firm. (The gap table's 1.1 is the difference of two rounded medians.)
- Corn again shows no gap.

## 5. Assumptions

These are assumptions, not data. The output lists them with the values used.

| Assumption | Default | User can change | Query parameter |
| --- | --- | --- | --- |
| Number of farmers | 100 | No | - |
| Pump share: share of rainfed palay farmers who get a pump (in every policy quarter) | 20% (0.2) | Yes, 0 to 1 | `pump_share` |
| Switch share: share of rainfed palay farmers who switch to corn, only in red quarters | 10% (0.1) | Yes, 0 to 1 | `switch_share` |
| Irrigation gain: percentage points a pump adds to a rainfed palay farmer's yield change in red quarters | +3.6 | Yes, 0 to 10 | `irrigation_gain` |

**Irrigation gain (decided):** the default +3.6 is labelled "estimated from two strong El Niños, not statistically firm" (section 4). Range 0 to 10 (decided): a pump cannot lower yield, and 10 is above the top of the 95% interval (+7.1).

The two shares are plain stated assumptions (decided). No source gives either share directly. Background only, not the source of the values:

- The Department of Agriculture said it installed 616 water pumps in 7 regions during the 2023-24 El Niño (DA news clippings, 27 April 2024, https://www.da.gov.ph/wp-content/uploads/2024/04/CLIPPINGS-FOR-APRIL-27-2024.pdf).
- **Unconfirmed:** a PhilRice household survey of 59 rice provinces reportedly found that fewer than 10% of respondents diversified their crops in both seasons (https://www.philrice.gov.ph/crop-diversification-mitigates-climate-change-impacts). This comes from a search summary only. The page could not be opened (certificate error). It covers all years, not El Niño advisories.

If the shares add up to more than 1, switching takes whoever is left (section 3).

## 6. Output and API

**Route (built):** `GET /api/simulate?province=...&crop=...&irrigation=true|false&switching=true|false&pump_share=0.2&switch_share=0.1&irrigation_gain=3.6` in `backend/app/api/simulation.py`. The router is included in `backend/main.py`.

- `pump_share`, `switch_share` and `irrigation_gain` are optional (decided), with defaults 0.2, 0.1 and 3.6. The shares must be between 0 and 1, and the gain between 0 and 10, inclusive.
- `irrigation` and `switching` are optional too and default to false (no policy).
- Reads the saved models and data on every request and never trains, like the other routes. A request takes about 1.2 s.
- The seed is fixed, so the same inputs (including the shares and the gain) always give the same output.
- Errors:
  - 422 for an unknown province or crop (same as `/api/impact`, shared `check_province_and_crop` in `backend/app/api/layer2.py`).
  - 422 for a share below 0 or above 1 (decided), or a gain below 0 or above 10.
  - 503 for a missing model or data file. The route reuses `missing_file` from `backend/app/api/layer2.py`.

**Response (built):**

- `province`, `crop`, `policies` (the two toggles), `farmers`, `seed`, `irrigated_share`, `pump_share`, `switch_share`, `irrigation_gain`.
- `quarters`: one entry per forecast quarter, with:
  - `quarter`, `rain_pct`, `colour`, `enough_data`.
  - `without` and `with`, each with: the average yield change % (every farmer counts the same), and one row per crop group (Irrigated Palay, Rainfed Palay, Rainfed Palay with pump, Corn (switched), or the corn type) with the number of farmers, the yield change % and the t/ha. Both are null when the chosen crop has no data in the quarter.
  - In `with`: `pumps_given` and `switched` counts.
  - `notes`: policies that did not apply and why.
- `assumptions`: the list from section 5, each with `name`, `value` (the value used) and `note`. The irrigation gain's note is "estimated from two strong El Niños, not statistically firm" (decided).
- `disclaimer`: "These are possible scenarios, not certain outcomes."

Palay and corn t/ha are never averaged together. Only the yield change % is averaged across all farmers.

## 7. Files

Built.

- `backend/app/simulation/__init__.py`, `backend/app/simulation/simulate.py`: farmers, local government, the crop gap table, the run, and the replay events (`REPLAY_EVENTS`, `REPLAY_NOTE`).
- `backend/app/layer2/impact.py`: `impact_entries` builds the Layer 2 entries for both modes; `replay_impact` gives them for a past event from observed rain and ONI.
- `backend/app/api/simulation.py`: the route.
- `backend/app/api/layer2.py`: `/api/options` lists the replay events.
- `backend/tests/test_simulation.py`: rule tests with hand-made Layer 2 inputs, plus the replay builder and `irrigated_share(up_to_year=...)` on hand-made tables, so no data files are needed.
- `backend/tests/test_api_simulation.py`: 422 on bad input (province, crop, shares outside 0 to 1, gain outside 0 to 10, unknown event) and the response shape, including the irrigation gain note, the replay fields and `replay_events` in `/api/options`. Skips when the saved models are missing, like `backend/tests/test_api_layer2.py`.

## 8. Done When

- The crop gap table is rebuilt with the 2-of-3-months El Niño rule, and the numbers are in this spec.
- Tests pass, including:
  - with no policies on, "with" equals "without";
  - running the same inputs twice gives identical output;
  - changing a share or the irrigation gain changes the result;
  - a share outside 0 to 1 or a gain outside 0 to 10 gives 422;
  - the irrigation gain changes nothing in yellow and green quarters;
  - corn crops and Irrigated Palay ignore both policies;
  - the first quarter is the same with and without;
  - switching is skipped when Corn has no data.
- `/api/simulate` works for:
  - Antique Palay (main demo, borderline): irrigated share 0.663 (2025), so 35 of 100 farmers are rainfed. The demo shows its real result under the live forecast, with no made-up red case. The demo province is only an example: its quarter colours come from the live Layer 1 forecast, so they change when the forecast changes. Antique sits close to the red cutoff (40%). With the ONI-only forecast, 2027 Q1 was red (38.3%): with both policies at the defaults, 7 pumps and 4 switched, average -6.9% without and -6.6% with, and pumped farmers went from -9.2% to -5.6% (2.50 to 2.60 t/ha). With the ERA5 forecast (November 2026), 2027 Q1 is yellow (40.9%, 0.9 points above the cutoff): 7 pumps are given but add nothing, nobody switches, and the average is -6.3% both with and without. Under that forecast no province with palay data is red in 2027 Q1 (only Sulu, 38.7%, which has no palay data).
  - Agusan del Sur Palay (second): irrigated share 0.493 (2025), 47 rainfed farmers. With the ERA5 forecast (November 2026), 2027 Q1 is yellow (40.9%): 9 pumps are given but add nothing, nobody switches, and the average is -6.4% both with and without (rainfed -7.0%, irrigated -5.9%). With the earlier ONI-only forecast, when 2027 Q1 was red, it was 9 pumps and 5 switched, average -7.3% without and -7.0% with.
  - Batanes Irrigated Palay (the no-data case): `enough_data` is false in both quarters.
- Nueva Ecija Palay is not a demo: its irrigated share is 0.997, so all 100 farmers are irrigated and no policy acts.

## 9. Limitations

- The crop gaps are national medians. They are not specific to the province.
- Layer 2's yield change % is the same for every crop, so all crop differences come from the gap table.
- The default irrigation gain comes from established irrigation systems, so it is an upper bound for pumps.
- Few red El Niño rows (100-158 per crop type), and more than half of the Palay ones come from 1998 Q1 and 2016 Q1.
- The irrigation gain is uncertain and driven by two events: the red-quarter gap between irrigated and rainfed palay (+3.6 points, p = 0.06) disappears without 1998 Q1 and 2016 Q1 (section 4). It is therefore an assumption, not a data result.
- The policy shares and the irrigation gain are assumptions. The user can change them.
- Switched farmers show corn t/ha, which is higher than rainfed palay t/ha (Antique 2027 Q1 under the ONI-only forecast, when it was red: 3.74 against 2.50; the demo depends on the forecast, see section 8). That is a different crop, not a gain. Compare crops by the yield change %, which is the same (-9.1% against -9.2%).
- Layer 2 predicts the same rain for most provinces (with the ERA5 forecast of November 2026, 71 of 86 coloured shapes have 65.7% in 2026 Q4 and 72 of 86 have 40.9% in 2027 Q1). So most provinces differ in Layer 3 only through their irrigated share and normal yields.

## 10. Open Items

- Policy timing (decided, built): the rule is "every forecast quarter after the first" (section 3).

## 11. Replay of a past El Niño (decided, status: back end and front end built)

**What it is:** the user may pick a named past event instead of the live forecast. The only choice now is "El Niño 2015-16" (key `el_nino_2015_16`). It is not a free year. It is built so another event can be added later with one entry, but no other event is added now.

**Quarters (in time order):** 2015 Q3, 2015 Q4, 2016 Q1, 2016 Q2. They come from `PAST_EVENTS` in `backend/app/layer2/map_output.py`.

**Method (same as the forecast mode; only the rain and ONI are observed instead of forecast):**

- Rain % and colour: observed (CHIRPS province rainfall). This is data.
- Yield change: the saved Layer 2 yield model, run on the observed rain % (this and last quarter) and the observed ONI (this and last quarter). Then the crop gap table is applied, as in forecast mode.
- Normal yield: the same 10-year straight line as Layer 2.
- A quarter with no observed rain or no normal has `enough_data` false.
- Irrigated share: from the event year. This means the latest complete year (same rule as section 3) up to and including 2016.
- Policy timing: the same rule, every quarter after the first. Policies act in 2015 Q4, 2016 Q1 and 2016 Q2.

**Data check (done before building):**

- In 2016 Q1, 40 of 80 provinces are red. 35 of those have Rainfed Palay data. Of those 35, Corn has no data in 2 (Surigao del Norte, Surigao del Sur), so switching is skipped there.
- 2015 Q3, 2015 Q4 and 2016 Q2 have no red provinces. So the policies change the results only in 2016 Q1.
- Rainfed Palay has no normal in 21 of 80 provinces in 2016 Q1 and 38 of 80 in 2016 Q2 (its t/ha is then empty).
- Corn is missing in 2 to 8 of 80 provinces per quarter.

**What is data and what is assumed:**

- Data: observed rain, colour, ONI, normals.
- Model: the Layer 2 yield change.
- National medians: the crop gap table.
- Stated assumptions: pump share, switch share, irrigation gain, the timing rule.

**Required wording (decided):** the replay output and the front end must say clearly that this is a scenario using assumed policy effects, that the +3.6 irrigation gain comes mostly from 1998 Q1 and 2016 Q1, and that it is not proof that pumps work. Proposed text for the `replay_note` field: "This is a replay scenario using assumed policy effects, not proof that pumps work. The +3.6-point irrigation gain was estimated mostly from 1998 Q1 and 2016 Q1, so replaying 2016 Q1 gives that assumption back."

**API (built):**

- `GET /api/simulate` has an optional `event` query parameter (a key of `REPLAY_EVENTS` in `simulate.py`). The default is none, which means the live forecast. An unknown event gives 422.
- `/api/options` has `replay_events`: a list of `{key, label}`, now `[{"key": "el_nino_2015_16", "label": "El Niño 2015-16"}]`.
- The response has `mode` ("forecast" or "replay"), `event` (the label, or null) and `replay_note` (null in forecast mode). The rest of the response is the same as in forecast mode, with the 4 event quarters.
- Replay does not use the Layer 1 forecast or the rain model. A quarter with no observed rain (this or last quarter) or no normal has `enough_data` false; with no rain its colour is grey.

**Demo numbers (Palay, both policies, default assumptions, built code):**

| Province | Irrigated share (year) | Quarter | Rain % | Colour | Without | With | Pumps | Switched |
|---|---|---|---|---|---|---|---|---|
| Antique | 0.577 (2016) | 2015 Q3 | 83.8 | green | -1.5 | -1.5 | 0 | 0 |
| | | 2015 Q4 | 50.7 | yellow | -2.9 | -2.9 | 8 | 0 |
| | | 2016 Q1 | 33.8 | red | -6.4 | -6.1 | 8 | 4 |
| | | 2016 Q2 | 89.9 | green | -7.0 | -7.0 | 8 | 0 |
| Agusan del Sur | 0.480 (2016) | 2015 Q3 | 95.0 | green | -1.7 | -1.7 | 0 | 0 |
| | | 2015 Q4 | 59.7 | yellow | -3.2 | -3.2 | 9 | 0 |
| | | 2016 Q1 | 15.7 | red | -6.4 | -6.1 | 9 | 5 |
| | | 2016 Q2 | 73.0 | yellow | -7.0 | -7.0 | 9 | 0 |

"Without" and "With" are the average yield change % over all farmers. As expected, the policies change the result only in the red quarter (2016 Q1), by +0.3 points.

**Front end (built):** the Simulation page gets a choice between the live forecast and "El Niño 2015-16". It shows the replay note clearly when replay is chosen.

**Risks and limits:**

- It is circular for the gain: 2016 Q1 is one of the two quarters the +3.6 came from.
- The 40% red cliff stays.
- Only one quarter (2016 Q1) is red.
