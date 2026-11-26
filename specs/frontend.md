# Front End Plan

**Status:** approved plan, being built. Progress is tracked in `specs/tasks-frontend.md`.

## 1. Stack

- **Build tool:** Vite, React + TypeScript template.
- **Styling:** Tailwind CSS v4 through the `@tailwindcss/vite` plugin. `src/index.css` holds `@import "tailwindcss";`.
- **Map:** Leaflet with react-leaflet. Use react-leaflet v5 if the template gives React 19, v4 for React 18.
- **Linter:** oxlint, which the Vite template ships instead of ESLint. Config in `.oxlintrc.json`, run with `npm run lint`.
- **Look:** plain and simple. White cards on a light grey background, one blue accent, Tailwind's default classes.
- **Routing:** none. Three tabs switched with `useState`.
- **Dev server:** the Vite proxy sends `/api` and `/health` to `http://127.0.0.1:8000`, so the back end needs no CORS setup. The port must match the one uvicorn runs on.
- Rule from CLAUDE.md: React only sends inputs and shows results. No ML or data processing in the front end.

## 2. Folder structure

```
frontend/
  index.html, package.json, vite.config.ts, tsconfig*.json, .oxlintrc.json   (from the template)
  src/
    main.tsx                    mounts App, imports leaflet/dist/leaflet.css
    App.tsx                     header, 3 tabs, shared province + crop choice, loads /api/options
    index.css                   @import "tailwindcss";
    api.ts                      one fetch helper + one function per route
    types.ts                    TypeScript types for each JSON response
    colours.ts                  dryness colour hex values and labels, shared by the Impact cards and the map
    pages/ForecastPage.tsx      Layer 1
    pages/ImpactPage.tsx        Layer 2
    pages/SimulationPage.tsx    Layer 3
    components/ProvinceCropPicker.tsx   two dropdowns, used by Impact and Simulation
    components/DrynessMap.tsx           Leaflet map
```

## 3. API calls per page

The fetch helper in `api.ts` throws the back end's `detail` text on any non-2xx response. Every page shows a loading message, and shows the error text in red (422 bad input, 503 model or data file missing). Query strings are built with `URLSearchParams`, because crop names have spaces (for example `Irrigated Palay`).

### App
- `GET /api/options` once: `{provinces, crops}` for the dropdowns.
- The chosen province and crop live in App, so Impact and Simulation share them.
- Nothing is chosen at start. The dropdowns show "Choose a province" and "Choose a crop" until the user picks.

### ForecastPage (Layer 1)
- `GET /api/forecast` once.
- Shows `event_underway`, `start_month`, `strength`, `duration_months.text` with a note when `duration_open_ended` is true, and `model_used`.
- Table of `forecast_series` (month, oni, lower to upper) with the matching `event_status` for each month.
- When no event is underway, `duration_months` is null and `duration_open_ended` is false. Show "No event underway" instead of the duration.
  - If `start_month` and `strength` are not null in that case, they belong to a predicted event. Show them as "Predicted El Niño: starts <start_month>, <strength>". If they are null, no event is predicted.

### ImpactPage (Layer 2)
- Until both a province and a crop are chosen, the cards area shows "Choose a province and crop" and `/api/impact` is not called.
- `GET /api/impact?province=&crop=` each time the choice changes. An ignore flag in the `useEffect` cleanup stops an older response from overwriting a newer one.
- Two quarter cards (2026 Q4, 2027 Q1): `rain_pct`, `colour`, `yield_change_pct`, `normal_yield_t_per_ha` vs `predicted_yield_t_per_ha`. Show "not enough data" when `enough_data` is false.
- Map: `GET /api/map` and `GET /api/shapes` once each, kept in state.
  - Controls: quarter (2026 Q4 / 2027 Q1) and view (`prediction`, `normal`, `el_nino_2015_16`, `el_nino_2023_24`).
  - Colour each shape from a lookup `map_psgc -> colour` (green, yellow, red, grey). The map loads and is coloured even before a choice. The chosen province gets a thick outline once one is picked.
  - Colour names map to Tailwind's standard shades, written as hex because Leaflet needs colour values, not class names: green `#22c55e` (green-500), yellow `#facc15` (yellow-400), red `#dc2626` (red-600), grey `#9ca3af` (gray-400).
  - Tooltip: the name from the GeoJSON `adm2_en` (the API's `province` is empty for NCR, City of Isabela and the Special Geographic Area) and `rain_pct`.
  - react-leaflet's `<GeoJSON>` does not restyle on prop change, so give it `key={quarter + view}`.
  - The map container needs an explicit height (for example `h-[500px]`), or it is blank.
  - Caveat under the map: colours show only the central forecast, and the 2027 Q1 red count is likely exaggerated (see `specs/layer2-impact.md`, limitations).
  - **Map upgrade (2026-11-26; details in `specs/layer2-impact.md`, section 11):** built: picking a province zooms the map to it (`ZoomToProvince` in `DrynessMap.tsx`, using react-leaflet's `useMap` and `fitBounds`); no choice shows the whole country. Planned, not built: then the map adds the 1,642 municipalities from new routes, each coloured by its own rainfall, with province borders from `/api/shapes` as a thin outline. Yield stays per province and is labelled "province estimate"; the cards' rain is labelled "province rainfall".
- **OSM tiles:** an OpenStreetMap tile layer as the background, with the attribution "© OpenStreetMap contributors" linking to https://www.openstreetmap.org/copyright. The coloured provinces come from `/api/shapes`, not the tiles, so the map still works offline. Without internet, only the background is missing.

### SimulationPage (Layer 3)
- Checkboxes: `irrigation`, `switching`. Optional number inputs: `pump_share` (0 to 1, default 0.2), `switch_share` (0 to 1, default 0.1), `irrigation_gain` (0 to 10, default 3.6).
- A **Run** button calls `GET /api/simulate?province=&crop=&irrigation=&switching=&...`. It is disabled until both a province and a crop are chosen. A run takes about 4 seconds, so show a loading message.
- When the province or crop changes, clear the shown results. The user presses Run again, so old results never appear next to a different province.
- Per quarter, "without" and "with" side by side: `avg_yield_change_pct`, the `groups` table, `pumps_given`, `switched`, `notes`. Handle `enough_data` false.
- `irrigated_share` can be null. Show it only when present.
- Bottom: the `assumptions` list and the `disclaimer`.

## 4. Back-end addition: GET /api/shapes

The map output has colours by `map_psgc` but no geometry. The 88 province shapes are 18 GeoJSON files (5.4 MB) in `data/raw/philippines/regions/medres/`, which is gitignored.

- New route `GET /api/shapes` returns one GeoJSON FeatureCollection of all 88 shapes.
- Built once (on first request or at startup) and kept in memory, not rebuilt per request.
- Each feature keeps only two properties: `map_psgc` (the 10-digit string, `String(adm2_psgc)` padded to 10 digits with leading zeros, so it matches `/api/map`) and `name` (`adm2_en`). In the files, `adm2_psgc` is a number without the leading zero.
- Coordinates are rounded to 3 decimals (about 110 m, not visible at province zoom).
- Responses are gzipped with Starlette's built-in `GZipMiddleware` (no new dependency).
- Measured size: 5.4 MB raw, 2.3 MB after rounding, about 455 KB rounded and gzipped.
- Missing files give the same 503 as the other Layer 2 routes.
- Test: 88 features, every `map_psgc` is 10 characters and matches the `/api/map` codes.
- Spec update when built: add the route to `specs/layer2-impact.md`.

## 5. Build order

1. Scaffold with Vite, add Tailwind and the proxy.
2. `types.ts` and `api.ts`.
3. ForecastPage.
4. ProvinceCropPicker and the Impact cards.
5. `/api/shapes` with its test, then DrynessMap.
6. SimulationPage.
7. Checks: `npx tsc -b`, `npm run lint`, `npm run build`, plus the back-end checks in CLAUDE.md.

## 6. Limitations

- OSM tiles need internet. The map still shows the coloured provinces without them.
- The OSM tile servers are for light use only. Fine for a class demo, not for heavy traffic.
- Rounding to 3 decimals slightly roughens coastlines.
- Package versions are pinned to exact versions in `frontend/package.json`. Update them on purpose, not by accident.
