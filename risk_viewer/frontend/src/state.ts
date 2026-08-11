import type {
  Disaggregation,
  HazardCurve,
  Layer,
  LayerAttribute,
  Legend,
  Scenario,
  ScenarioOverrides,
  ScenarioSummary,
  VulnerabilityOverrides,
} from "./api";
import { DAMAGE_STATE_COLORS } from "./colors";

export type NumericRange = [number, number];
export type Mode = "exposure" | "risk";

export const RISK_ATTRIBUTES: LayerAttribute[] = [
  { name: "expected_damage_state", label: "Expected damage state", kind: "categorical" },
  { name: "demand_sd_mm", label: "Spectral demand Sd (mm)", kind: "sequential" },
  { name: "population_night", label: "Population (night)", kind: "sequential" },
  { name: "casualties_night_total", label: "Expected casualties (night)", kind: "sequential" },
  { name: "total_beta", label: "Combined uncertainty (β)", kind: "sequential" },
];

export const RISK_CATEGORICAL_LEGEND: Record<string, Record<string, string>> = {
  expected_damage_state: DAMAGE_STATE_COLORS,
};

export interface AppState {
  mode: Mode;
  attribute: LayerAttribute | null;
  city: string | null;
  exposureLayer: Layer | null;
  data: GeoJSON.FeatureCollection | null;
  legend: Legend | null;
  numericRange: Record<string, NumericRange>;
  riskData: GeoJSON.FeatureCollection | null;
  riskNumericRange: Record<string, NumericRange>;
  scenarioSummary: ScenarioSummary | null;
  scenarioOverrides: ScenarioOverrides;
  scenarioList: Scenario[];
  // The full precomputed PGA hazard curve (mean/p16/p84), fetched
  // alongside the summary only for probabilistic scenarios; null in
  // deterministic mode or before the first PSHA scenario loads.
  hazardCurve: HazardCurve | null;
  // The controlling magnitude/distance for this scenario's return period
  // (see docs/disaggregation_plan.md), fetched alongside hazardCurve.
  // null in deterministic mode, before the first PSHA scenario loads, or
  // if disaggregation isn't available for this city/return period.
  disaggregation: Disaggregation | null;
  pickingEpicenter: boolean;
  selectedBuildingId: string | null;
  buildingOverrides: VulnerabilityOverrides;
}

export const state: AppState = {
  mode: "exposure",
  attribute: null,
  city: null,
  exposureLayer: null,
  data: null,
  legend: null,
  numericRange: {},
  riskData: null,
  riskNumericRange: {},
  scenarioSummary: null,
  scenarioOverrides: {},
  scenarioList: [],
  hazardCurve: null,
  disaggregation: null,
  pickingEpicenter: false,
  selectedBuildingId: null,
  buildingOverrides: {},
};

export function activeAttributes(): LayerAttribute[] {
  return state.mode === "risk" ? RISK_ATTRIBUTES : state.exposureLayer?.attributes ?? [];
}

export function activeLegendFor(attributeName: string): Record<string, string> {
  if (state.mode === "risk") return RISK_CATEGORICAL_LEGEND[attributeName] ?? {};
  return state.legend?.[attributeName] ?? {};
}

export function activeNumericRange(attributeName: string): NumericRange {
  const source = state.mode === "risk" ? state.riskNumericRange : state.numericRange;
  return source[attributeName] ?? [0, 1];
}

export function filteredExposureData(): GeoJSON.FeatureCollection {
  if (!state.data) return { type: "FeatureCollection", features: [] };
  if (!state.city) return state.data;
  return {
    type: "FeatureCollection",
    features: state.data.features.filter((feature) => feature.properties?.city === state.city),
  };
}

export function activeData(): GeoJSON.FeatureCollection {
  if (state.mode === "risk") return state.riskData ?? { type: "FeatureCollection", features: [] };
  return filteredExposureData();
}

export function pshaInfoForCity(city: string | null): { available: boolean; returnPeriods: number[] } {
  const entry = state.scenarioList.find((s) => s.city === city);
  return { available: entry?.psha_available ?? false, returnPeriods: entry?.psha_return_periods_years ?? [] };
}

export function numericRangeOf(collection: GeoJSON.FeatureCollection, attribute: string): NumericRange {
  let min = Infinity;
  let max = -Infinity;
  for (const feature of collection.features) {
    const value = feature.properties?.[attribute];
    if (typeof value === "number") {
      if (value < min) min = value;
      if (value > max) max = value;
    }
  }
  return min === Infinity ? [0, 1] : [min, max];
}
