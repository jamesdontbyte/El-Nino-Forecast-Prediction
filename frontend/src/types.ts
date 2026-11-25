// Shapes of the JSON the back end returns. Field names match the Python routes in backend/app/api/.
import type { FeatureCollection, Geometry } from "geojson";

// GET /api/options
export interface Options {
  provinces: string[];
  crops: string[];
}

// GET /api/forecast
export type EventStatus = "El Nino" | "Neutral" | "La Nina";
export type Strength = "weak" | "moderate" | "strong";

export interface ForecastMonth {
  month: string; // "YYYY-MM"
  oni: number;
  lower: number;
  upper: number;
}

export interface Forecast {
  event_underway: boolean;
  event_status: EventStatus[]; // one per forecast_series month
  start_month: string | null; // observed start if underway, else the predicted start, else null
  duration_months: { low: number; high: number; text: string } | null; // null when no event is underway
  duration_open_ended: boolean; // false when no event is underway
  strength: Strength | null;
  forecast_series: ForecastMonth[];
  model_used: string;
}

// GET /api/impact
export type Colour = "green" | "yellow" | "red" | "grey";

export interface ImpactQuarter {
  quarter: string; // "2026 Q4"
  oni: number;
  oni_prev: number;
  rain_pct: number;
  colour: Colour;
  enough_data: boolean;
  // The three below are null when enough_data is false.
  yield_change_pct: number | null;
  normal_yield_t_per_ha: number | null;
  predicted_yield_t_per_ha: number | null;
}

export interface Impact {
  province: string;
  crop: string;
  models_used: { rain: string; yield: string };
  quarters: ImpactQuarter[];
}

// GET /api/map
export type MapViewName =
  | "prediction"
  | "normal"
  | "el_nino_2015_16"
  | "el_nino_2023_24";

export interface MapShape {
  map_psgc: string; // 10-digit code, matches the shapes from /api/shapes
  province: string | null; // null for NCR, City of Isabela and the Special Geographic Area
  rain_pct: number | null;
  colour: Colour;
}

export interface MapQuarter {
  quarter: string;
  oni: number;
  oni_prev: number;
  // year is null when no past year fits this quarter (for example el_nino_2023_24 in a Q2).
  views: Record<MapViewName, { year: number | null; shapes: MapShape[] }>;
}

// GET /api/shapes
export type Shapes = FeatureCollection<
  Geometry,
  { map_psgc: string; name: string }
>;

// GET /api/simulate
export interface SimulationGroup {
  group: string;
  farmers: number;
  yield_change_pct: number;
  yield_t_per_ha: number | null;
}

export interface SimulationOutcome {
  avg_yield_change_pct: number;
  groups: SimulationGroup[];
}

export interface SimulationQuarter {
  quarter: string;
  rain_pct: number;
  colour: Colour;
  enough_data: boolean;
  // without and with are null when enough_data is false.
  without: SimulationOutcome | null;
  with: (SimulationOutcome & { pumps_given: number; switched: number }) | null;
  notes: string[];
}

export interface Simulation {
  province: string;
  crop: string;
  policies: { irrigation: boolean; switching: boolean };
  farmers: number;
  seed: number;
  irrigated_share: number | null; // only set for the crop "Palay"
  pump_share: number;
  switch_share: number;
  irrigation_gain: number;
  quarters: SimulationQuarter[];
  assumptions: { name: string; value: number; note: string }[];
  disclaimer: string;
}
