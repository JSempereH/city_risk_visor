export interface LayerAttribute {
  name: string;
  label: string;
  kind: "categorical" | "sequential";
}

export interface Layer {
  id: string;
  label: string;
  description: string;
  attributes: LayerAttribute[];
  cities: string[];
}

export type Legend = Record<string, Record<string, string>>;

export interface CapacityCurve {
  displacement_mm: number[];
  v_over_w: number[];
  v_over_w_std: number[];
}

export interface SpectralCapacityCurve {
  sd_mm: number[];
  sa_g: number[];
  sa_g_std: number[];
}

export interface BilinearCapacity {
  sdy_mm: number;
  say_g: number;
  sdu_mm: number;
  sau_g: number;
}

export type DamageState = "slight" | "moderate" | "extensive" | "complete";

export interface FragilityCurveData {
  damage_state: DamageState;
  median_sd_mm: number;
  beta: number;
  sd_mm: number[];
  probability: number[];
}

export interface EffectiveInputs {
  structural_system_class: string;
  n_floors: number | null;
  height: number | null;
  code_quality: string;
}

export interface OverriddenFlags {
  structural_system_class: boolean;
  n_floors: boolean;
  height: boolean;
  code_quality: boolean;
}

export interface TypologyEnsemble {
  model_predictions: Record<string, string>;
  majority_vote: string;
  ensemble_pred: string;
  agreement_ratio: number;
  normalized_entropy: number;
  is_contested: boolean;
  candidate_classes: string[];
}

interface VulnerabilityOverrideInfo {
  overridden: OverriddenFlags;
  effective_inputs: EffectiveInputs;
  typology_ensemble: TypologyEnsemble | null;
}

export interface VulnerabilityUnavailable extends VulnerabilityOverrideInfo {
  available: false;
  reason: string;
}

interface VulnerabilityAvailableBase extends VulnerabilityOverrideInfo {
  available: true;
  reason: null;
  assumptions: Record<string, string>;
  fragility_curves: FragilityCurveData[];
}

/** Tier 1: a real capacity curve, predicted by the ML model (masonry only). */
export interface VulnerabilityFromMlModel extends VulnerabilityAvailableBase {
  curve_source: "ml_capacity_model";
  direction_used: "X" | "Y";
  capacity_curve: CapacityCurve;
  spectral_capacity_curve: SpectralCapacityCurve;
  bilinear: BilinearCapacity;
}

/** Tier 2: no capacity curve, fragility from the GEM global vulnerability model. */
export interface VulnerabilityFromGem extends VulnerabilityAvailableBase {
  curve_source: "gem_global_vulnerability";
  direction_used: null;
  capacity_curve: null;
  spectral_capacity_curve: null;
  bilinear: null;
}

/** Tier 3: no capacity curve, generic published-typology fragility only. */
export interface VulnerabilityFromPublishedFallback extends VulnerabilityAvailableBase {
  curve_source: "published_fallback";
  direction_used: null;
  capacity_curve: null;
  spectral_capacity_curve: null;
  bilinear: null;
}

export type VulnerabilityAvailable =
  | VulnerabilityFromMlModel
  | VulnerabilityFromGem
  | VulnerabilityFromPublishedFallback;

export type Vulnerability = VulnerabilityAvailable | VulnerabilityUnavailable;

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8001";

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) {
    // FastAPI's HTTPException puts the actual reason (e.g. "magnitude
    // must be between 4.5 and 9.0") in the response body's `detail`
    // field, not the status line -- surface that instead of just the
    // status code, or an invalid input silently reads as "backend is
    // broken" instead of "try a different value".
    let detail: string | undefined;
    try {
      const body = await response.json();
      detail = typeof body?.detail === "string" ? body.detail : undefined;
    } catch {
      // Response wasn't JSON (e.g. a proxy error page); fall through to
      // the generic message below.
    }
    throw new Error(detail ?? `Request to ${path} failed: ${response.status}`);
  }
  return response.json() as Promise<T>;
}

export function fetchLayers(): Promise<Layer[]> {
  return getJson<Layer[]>("/api/layers");
}

export function fetchLayerData(layerId: string, city?: string): Promise<GeoJSON.FeatureCollection> {
  const query = city ? `?city=${encodeURIComponent(city)}` : "";
  return getJson<GeoJSON.FeatureCollection>(`/api/layers/${layerId}/data${query}`);
}

export function fetchLegend(layerId: string): Promise<Legend> {
  return getJson<Legend>(`/api/layers/${layerId}/legend`);
}

export interface VulnerabilityOverrides {
  structural_system_class?: string;
  n_floors?: number;
  height?: number;
  code_quality?: string;
}

export function fetchVulnerability(
  buildingId: string,
  overrides: VulnerabilityOverrides = {},
): Promise<Vulnerability> {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(overrides)) {
    if (value !== undefined && value !== "") params.set(key, String(value));
  }
  const query = params.toString();
  return getJson<Vulnerability>(
    `/api/buildings/${encodeURIComponent(buildingId)}/vulnerability${query ? `?${query}` : ""}`,
  );
}

export type ScenarioMode = "deterministic" | "probabilistic";

export interface Scenario {
  city: string;
  label: string;
  magnitude: number;
  depth_km: number;
  epicenter_lat: number;
  epicenter_lon: number;
  tectonic_regime: "crustal" | "interface" | "intraslab";
  source_note: string;
  // Present on /api/scenarios (the per-city list): whether this city has
  // a precomputed PSHA hazard curve, and which return periods it offers.
  psha_available?: boolean;
  psha_return_periods_years?: number[];
  // Present on /api/scenarios/{city}/summary's nested `scenario`: which
  // mode produced this particular result. magnitude/depth_km/epicenter_*
  // above are inert placeholders when mode is "probabilistic", see
  // backend/app/hazard/scenario.py's Scenario.mode docstring.
  mode?: ScenarioMode;
  return_period_years?: number | null;
}

export interface ScenarioSummary {
  city: string;
  scenario: Scenario;
  n_buildings: number;
  n_available: number;
  damage_state_counts: Record<string, number>;
  total_population_day: number;
  total_population_night: number;
  total_casualties_day: number;
  total_casualties_day_fatalities: number;
  total_casualties_night: number;
  total_casualties_night_fatalities: number;
  monte_carlo: {
    n_samples: number;
    casualties_day: PercentileBand;
    casualties_night: PercentileBand;
    fatalities_day: PercentileBand;
    fatalities_night: PercentileBand;
  };
  // PGA (g) at mean/p16/p84 across the GMPE logic tree: the hazard
  // curve's own epistemic spread, present only for probabilistic
  // scenarios. null for deterministic ones.
  hazard_percentiles: Record<string, number> | null;
}

export interface PercentileBand {
  p10: number;
  p50: number;
  p90: number;
  mean: number;
}

export interface ScenarioOverrides {
  magnitude?: number;
  depth_km?: number;
  epicenter_lat?: number;
  epicenter_lon?: number;
  return_period_years?: number;
}

function scenarioQuery(overrides: ScenarioOverrides): string {
  const params = new URLSearchParams();
  for (const [key, value] of Object.entries(overrides)) {
    if (value !== undefined) params.set(key, String(value));
  }
  const query = params.toString();
  return query ? `?${query}` : "";
}

export function fetchScenarios(): Promise<Scenario[]> {
  return getJson<Scenario[]>("/api/scenarios");
}

export function fetchScenarioSummary(
  city: string,
  overrides: ScenarioOverrides = {},
): Promise<ScenarioSummary> {
  return getJson<ScenarioSummary>(
    `/api/scenarios/${encodeURIComponent(city)}/summary${scenarioQuery(overrides)}`,
  );
}

export function fetchScenarioRisk(
  city: string,
  overrides: ScenarioOverrides = {},
): Promise<GeoJSON.FeatureCollection> {
  return getJson<GeoJSON.FeatureCollection>(
    `/api/scenarios/${encodeURIComponent(city)}/risk${scenarioQuery(overrides)}`,
  );
}

export interface HazardCurve {
  city: string;
  imt: string;
  investigation_time_years: number;
  levels: number[];
  mean: number[];
  p16?: number[];
  p84?: number[];
}

export function fetchHazardCurve(city: string, imt = "PGA"): Promise<HazardCurve> {
  return getJson<HazardCurve>(
    `/api/scenarios/${encodeURIComponent(city)}/hazard_curve?imt=${encodeURIComponent(imt)}`,
  );
}

export interface DisaggregationBin {
  mag_bin: number;
  dist_bin: number;
  fraction: number;
}

export interface Disaggregation {
  city: string;
  return_period_years: number;
  imt: string;
  mean_magnitude: number;
  mean_distance_km: number;
  bins: DisaggregationBin[];
}

export function fetchDisaggregation(city: string, returnPeriodYears: number): Promise<Disaggregation> {
  return getJson<Disaggregation>(
    `/api/scenarios/${encodeURIComponent(city)}/disaggregation?return_period_years=${returnPeriodYears}`,
  );
}

