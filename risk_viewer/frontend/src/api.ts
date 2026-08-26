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

export interface GemReferenceEntry {
  structural_system_class: string;
  fixed_period_s: number;
  assumptions: Record<string, string>;
  fragility_curves: FragilityCurveData[];
}

export interface TypologyEnsemble {
  model_predictions: Record<string, string>;
  majority_vote: string;
  ensemble_pred: string;
  agreement_ratio: number;
  normalized_entropy: number;
  is_contested: boolean;
  candidate_classes: string[];
  // Class -> soft-ensemble probability; doesn't necessarily sum to 1.0
  // (threshold-adjusted, not raw predict_proba -- see loader.py's own
  // EnsembleInfo.class_probabilities docstring). Empty object for a
  // predictions.csv that predates this field.
  class_probabilities: Record<string, number>;
  // False for a city whose classifier was trained on OTHER cities' data
  // with no local examples to check it against (e.g. lomas_centinela's
  // pooled model) -- see backend's get_ensemble_quality_metrics.
  locally_validated: boolean;
}

// The prior-adjusted posterior for this building (see
// backend/app/typology_prior.py), present only when it's ML-estimated
// AND covered by an active prior for its city -- structural_system_class
// shown elsewhere already reflects this posterior's argmax (unless
// overridden via the query params), this is the full distribution/
// uncertainty behind that choice.
export interface TypologyPriorResult {
  posterior_class_probabilities: Record<string, number>;
  posterior_normalized_entropy: number;
}

// PROVISIONAL: the ml_capacity_model GPR's own masonry-trained capacity
// curve, rescaled for a GEM-tier building whose class the GPR was never
// trained on (see backend/app/vulnerability/service.py's own
// ApproxMlCapacity docstring for the class_ratio derivation). Never this
// building's actual result -- curve_source stays "gem_global_vulnerability"
// and its own published curve is what drives the real fragility curves --
// just an optional secondary overlay the Curves tab can show alongside
// it, with a real predictive-uncertainty band (sa_g_std) GEM's own
// deterministic curve doesn't carry. null for every tier except
// gem_global_vulnerability with a known floor count (the GPR needs real
// geometry to run on at all).
export interface ApproxMlCapacity {
  direction_used: "X" | "Y";
  sd_mm: number[];
  sa_g: number[];
  sa_g_std: number[];
  class_ratio: number;
}

interface VulnerabilityOverrideInfo {
  overridden: OverriddenFlags;
  effective_inputs: EffectiveInputs;
  typology_ensemble: TypologyEnsemble | null;
  typology_prior: TypologyPriorResult | null;
  approx_ml_capacity: ApproxMlCapacity | null;
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
  // Only meaningful (non-null) for curve_source "gem_global_vulnerability";
  // see vulnerabilityPanel.ts's PGA_PROXY_PERIOD_S for what it's used for.
  fixed_period_s: number | null;
  // PROVISIONAL masonry-quality correction actually applied (see
  // service.py's _QUALITY_FACTOR_BY_CODE_QUALITY); 1.0 means none.
  quality_factor: number;
  // The published GEM curve(s) for this building's own class, shown as a
  // reference regardless of which tier actually won (curve_source) --
  // see service.py::_compute_gem_reference. null only when no GEM curve
  // exists at all for this class (e.g. "unlabeled" never reaches here
  // since it's never `available: true`, but kept nullable defensively).
  // For structural_system_class "M" this is the 3-entry MUR/MCF/MR family.
  gem_reference: GemReferenceEntry[] | null;
}

/** Tier 1: a real capacity curve, predicted by the ML model (masonry only). */
export interface VulnerabilityFromMlModel extends VulnerabilityAvailableBase {
  curve_source: "ml_capacity_model";
  direction_used: "X" | "Y";
  capacity_curve: CapacityCurve;
  spectral_capacity_curve: SpectralCapacityCurve;
  bilinear: BilinearCapacity;
}

/** Tier 2: fragility AND capacity curve both from the GEM global
 * vulnerability model (always real, published data -- see
 * gem_capacity.py). capacity_curve stays null: GEM's published curve is
 * already spectral, with no building-level (roof-drift/base-shear)
 * equivalent to report there, only spectral_capacity_curve/bilinear.
 * direction_used stays null too: the published curve isn't direction-
 * dependent, unlike the ml_capacity_model tier's own X/Y curves. */
export interface VulnerabilityFromGem extends VulnerabilityAvailableBase {
  curve_source: "gem_global_vulnerability";
  direction_used: null;
  capacity_curve: null;
  spectral_capacity_curve: SpectralCapacityCurve;
  bilinear: BilinearCapacity;
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

async function extractErrorDetail(response: Response, path: string): Promise<string> {
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
  return detail ?? `Request to ${path} failed: ${response.status}`;
}

async function getJson<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`);
  if (!response.ok) throw new Error(await extractErrorDetail(response, path));
  return response.json() as Promise<T>;
}

async function postJson<T>(path: string, body: unknown): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
  });
  if (!response.ok) throw new Error(await extractErrorDetail(response, path));
  return response.json() as Promise<T>;
}

async function deleteRequest<T>(path: string): Promise<T> {
  const response = await fetch(`${API_BASE}${path}`, { method: "DELETE" });
  if (!response.ok) throw new Error(await extractErrorDetail(response, path));
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

// Expert-specified structural-typology hypothesis for a city (see
// backend/app/typology_hypothesis.py): overrides every building's
// structural_system_class for that city's risk computation, sampled to
// match the given proportions, until cleared.
export interface TypologyHypothesis {
  city: string;
  proportions: Record<string, number>;
  seed: number;
  normalized_entropy: number;
  typology_beta: number;
  fingerprint: string;
}

export function fetchTypologyHypothesis(city: string): Promise<TypologyHypothesis | null> {
  return getJson<TypologyHypothesis | null>(`/api/cities/${encodeURIComponent(city)}/typology_hypothesis`);
}

export function setTypologyHypothesis(
  city: string,
  proportions: Record<string, number>,
  seed = 0,
): Promise<TypologyHypothesis> {
  return postJson<TypologyHypothesis>(`/api/cities/${encodeURIComponent(city)}/typology_hypothesis`, {
    proportions,
    seed,
  });
}

export function clearTypologyHypothesis(city: string): Promise<{ city: string; cleared: boolean }> {
  return deleteRequest<{ city: string; cleared: boolean }>(
    `/api/cities/${encodeURIComponent(city)}/typology_hypothesis`,
  );
}

// Expert-specified structural-typology *prior* for a city (see
// backend/app/typology_prior.py). Deliberately NOT the same mechanism as
// TypologyHypothesis above: a prior only ever adjusts ML-estimated
// buildings (structural_system_estimated), never buildings with a real
// recorded structural_system, and the given proportions are for the
// WHOLE population (ground truth included), not just the estimated
// share -- see that module's own docstring.
export interface TypologyPriorFeasibility {
  ground_truth_counts: Record<string, number>;
  n_ground_truth: number;
  n_estimated: number;
  n_total: number;
  prior_within_estimated: Record<string, number>;
}

export interface TypologyPrior {
  city: string;
  proportions: Record<string, number>;
  alpha: number;
  fingerprint: string;
  // Only present on the response to setTypologyPrior(), not on a plain
  // fetchTypologyPrior() (the backend doesn't re-derive/store this).
  feasibility?: TypologyPriorFeasibility;
}

export function fetchAvailableTypologyClasses(
  city: string,
): Promise<{ city: string; classes: string[]; locally_validated: boolean }> {
  return getJson<{ city: string; classes: string[]; locally_validated: boolean }>(
    `/api/cities/${encodeURIComponent(city)}/typology_prior/available_classes`,
  );
}

export function fetchTypologyPrior(city: string): Promise<TypologyPrior | null> {
  return getJson<TypologyPrior | null>(`/api/cities/${encodeURIComponent(city)}/typology_prior`);
}

export function setTypologyPrior(city: string, proportions: Record<string, number>, alpha: number): Promise<TypologyPrior> {
  return postJson<TypologyPrior>(`/api/cities/${encodeURIComponent(city)}/typology_prior`, { proportions, alpha });
}

export function clearTypologyPrior(city: string): Promise<{ city: string; cleared: boolean }> {
  return deleteRequest<{ city: string; cleared: boolean }>(`/api/cities/${encodeURIComponent(city)}/typology_prior`);
}

