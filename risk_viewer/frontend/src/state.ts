import type {
  Disaggregation,
  HazardCurve,
  Layer,
  LayerAttribute,
  Legend,
  Scenario,
  ScenarioOverrides,
  ScenarioSummary,
  TypologyHypothesis,
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
  // Custom-scenario form values the user has typed or picked on the map
  // but not yet applied (see scenarioController.ts's pickEpicenter()):
  // kept separate from scenarioOverrides (the last *applied* values) so
  // a re-render triggered by picking an epicenter doesn't wipe out a
  // magnitude/depth the user already typed but hadn't clicked "Apply"
  // for yet.
  scenarioDraft: ScenarioOverrides;
  // Set when the last apply/reset/return-period attempt failed (see
  // scenarioController.ts's loadRiskForCity), cleared on the next
  // successful load or as soon as the user edits the draft again.
  scenarioError: string | null;
  selectedBuildingId: string | null;
  buildingOverrides: VulnerabilityOverrides;
  // The active expert typology hypothesis for the current city, if any
  // (see backend/app/typology_hypothesis.py), fetched alongside the
  // scenario so it stays in sync across reloads/city switches: this is
  // process-lifetime backend state, not something the frontend owns.
  typologyHypothesis: TypologyHypothesis | null;
  // Percentage strings (not yet applied) the user is typing into the
  // hypothesis form, keyed by structural class. Separate from the
  // applied typologyHypothesis for the same reason scenarioDraft is
  // separate from scenarioOverrides: an in-progress edit shouldn't be
  // discarded by a re-render triggered by something else.
  typologyHypothesisDraft: Record<string, string>;
  typologyHypothesisError: string | null;
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
  scenarioDraft: {},
  scenarioError: null,
  selectedBuildingId: null,
  buildingOverrides: {},
  typologyHypothesis: null,
  typologyHypothesisDraft: {},
  typologyHypothesisError: null,
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

function percentileOf(sortedValues: number[], p: number): number {
  if (sortedValues.length === 1) return sortedValues[0];
  const rank = (p / 100) * (sortedValues.length - 1);
  const lowerIndex = Math.floor(rank);
  const upperIndex = Math.ceil(rank);
  if (lowerIndex === upperIndex) return sortedValues[lowerIndex];
  const weight = rank - lowerIndex;
  return sortedValues[lowerIndex] * (1 - weight) + sortedValues[upperIndex] * weight;
}

// Percentile-clamped, not literal min/max: a single very-tall outlier
// building must not stretch the whole color domain so far that every
// ordinary 2/3/5-floor building collapses into one indistinguishable
// color near the bottom of the ramp (the exact symptom reported for
// lomas_centinela, whose buildings are almost all 1-3 floors). Values
// outside [lowerPercentile, upperPercentile] still render, just clamped
// to the ramp's own end color (see sequentialColor's t clamp to [0,1]),
// so an outlier reads as "at least this extreme" rather than distorting
// the scale for everyone else.
export function numericRangeOf(
  collection: GeoJSON.FeatureCollection,
  attribute: string,
  lowerPercentile = 5,
  upperPercentile = 95,
): NumericRange {
  const values: number[] = [];
  for (const feature of collection.features) {
    const value = feature.properties?.[attribute];
    if (typeof value === "number" && !Number.isNaN(value)) {
      values.push(value);
    }
  }
  if (values.length === 0) return [0, 1];
  values.sort((a, b) => a - b);
  const min = percentileOf(values, lowerPercentile);
  const max = percentileOf(values, upperPercentile);
  if (min === max) {
    // Every value inside the clamped band is identical (a small city, or
    // an attribute with little spread): fall back to the true min/max so
    // there is still some differentiation instead of one flat color.
    return [values[0], values[values.length - 1]];
  }
  return [min, max];
}

/** True if some feature's value for this attribute exceeds the given
 * (already percentile-clamped) domain max, i.e. the legend's top step is
 * "this value or more", not a literal maximum. Used to render a "+" on
 * the legend so clamping stays honest instead of silently implying the
 * displayed max is the true max. */
export function isClampedAbove(collection: GeoJSON.FeatureCollection, attribute: string, domainMax: number): boolean {
  for (const feature of collection.features) {
    const value = feature.properties?.[attribute];
    if (typeof value === "number" && value > domainMax) return true;
  }
  return false;
}
