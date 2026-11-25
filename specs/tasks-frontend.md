# Tasks: Front end

Work top to bottom. Tick each box when done. Details are in specs/frontend.md.

## 1. Scaffold
- [x] frontend/: Vite with the React + TypeScript template. Pin package versions after checking them on npm.
- [x] Tailwind CSS v4 through `@tailwindcss/vite`. `src/index.css` holds `@import "tailwindcss";`.
- [x] Leaflet and react-leaflet (v5 for React 19, v4 for React 18). `src/main.tsx` imports `leaflet/dist/leaflet.css`.
- [x] vite.config.ts: proxy `/api` and `/health` to `http://127.0.0.1:8000` (same port as uvicorn).
- [x] src/App.tsx: header and 3 tabs switched with `useState`, no router.

## 2. Types and API helper
- [x] src/types.ts: one type per JSON response (options, forecast, impact, map, shapes, simulate).
- [x] src/api.ts: one fetch helper that throws the back end's `detail` text on any non-2xx, and one function per route. Query strings built with `URLSearchParams`.
- [x] App loads `GET /api/options` once, with loading message and error text in red.

## 3. ForecastPage (Layer 1)
- [x] src/pages/ForecastPage.tsx: `GET /api/forecast` once, with loading message and error text in red.
- [x] Show `event_underway`, `start_month`, `strength`, `duration_months.text` (with a note when `duration_open_ended` is true), and `model_used`.
- [x] When `event_underway` is false: "No event underway", plus the predicted start and strength when `start_month` and `strength` are not null.
- [x] Table of `forecast_series` (month, oni, lower to upper) with each month's `event_status`.

## 4. Picker and Impact cards (Layer 2)
- [x] App keeps the chosen province and crop, shared by Impact and Simulation (moved here from step 2: TypeScript rejects state that nothing uses yet).
- [x] src/components/ProvinceCropPicker.tsx: two dropdowns from `/api/options`. Nothing chosen at start: "Choose a province" and "Choose a crop" placeholders.
- [x] src/pages/ImpactPage.tsx: "Choose a province and crop" until both are picked, with no call before that.
- [x] `GET /api/impact` on each choice change, with an ignore flag in the `useEffect` cleanup.
- [x] Two quarter cards (2026 Q4, 2027 Q1): `rain_pct`, `colour`, `yield_change_pct`, normal vs predicted yield. "Not enough data" when `enough_data` is false.
- [x] Loading message and error text in red (422, 503).

## 5. Shapes route and map
- [ ] Back end: `GET /api/shapes`, one FeatureCollection of the 88 province shapes, built once and kept in memory.
- [ ] Each feature keeps only `map_psgc` (10-digit string, padded with leading zeros) and `name` (`adm2_en`). Coordinates rounded to 3 decimals.
- [ ] `GZipMiddleware` in backend/main.py. Missing files give the same 503 as the other Layer 2 routes.
- [ ] Test: 88 features, every `map_psgc` is 10 characters and matches the `/api/map` codes.
- [ ] Add the route to specs/layer2-impact.md.
- [ ] src/components/DrynessMap.tsx: `GET /api/map` and `GET /api/shapes` once each, kept in state.
- [ ] Controls: quarter (2026 Q4 / 2027 Q1) and view (`prediction`, `normal`, `el_nino_2015_16`, `el_nino_2023_24`).
- [ ] Colour shapes from a `map_psgc -> colour` lookup, using the Tailwind hex shades in the spec. Map shows before any choice. Thick outline on the chosen province once picked. `<GeoJSON key={quarter + view}>` so it restyles.
- [ ] Tooltip: GeoJSON name and `rain_pct`.
- [ ] Explicit map height (for example `h-[500px]`).
- [ ] OSM tile layer with the attribution "© OpenStreetMap contributors" linking to https://www.openstreetmap.org/copyright.
- [ ] Caveat under the map: central forecast only, 2027 Q1 red count likely exaggerated.

## 6. SimulationPage (Layer 3)
- [ ] src/pages/SimulationPage.tsx: checkboxes `irrigation`, `switching`. Optional inputs `pump_share` (0 to 1, default 0.2), `switch_share` (0 to 1, default 0.1), `irrigation_gain` (0 to 10, default 3.6).
- [ ] Run button calls `GET /api/simulate`, with loading message and error text in red. Disabled until both a province and a crop are chosen.
- [ ] Clear the results when the province or crop changes.
- [ ] Per quarter, "without" and "with" side by side: `avg_yield_change_pct`, `groups` table, `pumps_given`, `switched`, `notes`. Handle `enough_data` false.
- [ ] Show `irrigated_share` only when not null.
- [ ] Bottom: the `assumptions` list and the `disclaimer`.

## 7. Checks
- [ ] Front end from frontend/: `npx tsc -b`, `npm run lint`, `npm run build`.
- [ ] Back end: ruff and pytest from backend/.
- [ ] Start the server, /health returns ok, and click through all 3 tabs in the dev server.
