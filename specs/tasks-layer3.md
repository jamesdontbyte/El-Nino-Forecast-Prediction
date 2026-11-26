# Tasks: Layer 3 (policy simulation)

Work top to bottom. Tick each box when done. Details are in specs/layer3-simulation.md.

## 1. Decisions
- [x] Policies: irrigation support and crop switching only. No subsidy, no insurance.
- [x] Units: yield only (% of normal and t/ha). No pesos.
- [x] Agents: about 100 farmers with a fixed seed, and one local government.
- [x] Both policies apply in 2027 Q1 only (built; replaced by the timing rule in section 6).
- [x] Both on: irrigation goes first, then rainfed farmers without a pump may switch.
- [x] Crop switching is kept even though the past data shows no gain.
- [x] Pump share: default 20% of rainfed palay farmers, a stated assumption. The user can change it (`pump_share`, 0 to 1).
- [x] Switch share: default 10% of rainfed palay farmers, red quarters only, a stated assumption. The user can change it (`switch_share`, 0 to 1).
- [x] Irrigation gain: an assumption, default +3.6 points in red quarters, labelled "estimated from two strong El Niños, not statistically firm". The user can change it (`irrigation_gain`).
- [x] Irrigated share rule: the latest year where all 4 quarters have palay area.
- [x] Irrigation gain rules: no gain in yellow and green, pumped farmers keep the Rainfed Palay normal, range 0 to 10.
- [x] Policy timing: policies act in every forecast quarter after the first.
- [x] Replay of a past El Niño: only "El Niño 2015-16" (`el_nino_2015_16`), chosen by name, built so one entry adds another.
- [x] Replay irrigated share: from the event year (latest complete year up to and including 2016).

## 2. Crop gap table
- [x] Rebuild the crop gap table with the 2-of-3-months El Niño quarter rule.
- [x] Write the numbers into the spec, section 4.
- [x] notebooks/06_crop_gap_check.py: bootstrap and rank test for Irrigated Palay and Corn against Rainfed Palay in red quarters, with and without 1998 Q1 and 2016 Q1.
- [x] User review of the table before the simulation uses it (approved).

## 3. Simulation
- [x] backend/app/simulation/simulate.py: farmers, local government, run with and without policies.
- [x] backend/tests/test_simulation.py (18 tests): rule tests with hand-made inputs, including: same inputs twice give identical output, changing a share or the irrigation gain changes the result, and the gain changes nothing in yellow and green quarters.

## 4. API
- [x] backend/app/api/simulation.py: GET /api/simulate with optional pump_share and switch_share (0 to 1) and irrigation_gain (0 to 10), else 422, included in backend/main.py.
- [x] backend/tests/test_api_simulation.py (11 tests), including 422 for out-of-range values and the irrigation gain note in the output.

## 5. Checks
- [x] ruff and pytest from backend/ (106 passed).
- [x] Start the server, /health returns ok.
- [x] /api/simulate for Antique Palay (main demo), Agusan del Sur Palay, and Batanes Irrigated Palay (no-data case).

## 6. Improvements: timing rule and 2015-16 replay
- [x] Spec and task list updated with the decisions (timing rule, replay of El Niño 2015-16, event-year irrigated share).
- [x] Timing rule: policies act in every forecast quarter after the first.
- [x] Replay builder and optional `event` on /api/simulate, with tests.
- [x] Front end: replay choice and the replay note on the Simulation page.
- [ ] Yellow-gap bootstrap in notebooks/06_crop_gap_check.py; numbers reported, no code change unless option B (graded irrigation gain) is approved.
- [ ] Checks (ruff, pytest, type check, lint, build, /health) and demo numbers in the spec.
