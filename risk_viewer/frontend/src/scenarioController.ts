import {
  fetchDisaggregation,
  fetchHazardCurve,
  fetchScenarioRisk,
  fetchScenarioSummary,
  type Disaggregation,
  type HazardCurve,
  type ScenarioOverrides,
} from "./api";
import { computeBbox, map, renderLayer } from "./mapLayers";
import { RISK_ATTRIBUTES, numericRangeOf, pshaInfoForCity, state } from "./state";
import { renderScenarioPanel, hideScenarioPanel } from "./scenarioPanel";

function showRiskLoading(message: string): void {
  const panel = document.getElementById("scenario-panel");
  if (!panel) return;
  panel.classList.remove("hidden");
  panel.innerHTML = `<p>${message}</p>`;
}

const scenarioControlCallbacks = {
  onApply: applyScenarioOverrides,
  onReset: resetScenarioOverrides,
  onTogglePickEpicenter: toggleEpicenterPicking,
  onSelectReturnPeriod: applyReturnPeriod,
  onSwitchToDeterministic: resetScenarioOverrides,
};

function renderCurrentScenarioPanel(): void {
  const panel = document.getElementById("scenario-panel");
  if (!panel || !state.scenarioSummary || !state.city) return;
  renderScenarioPanel(panel, state.scenarioSummary, state.hazardCurve, state.disaggregation, {
    overrides: state.scenarioOverrides,
    pickingEpicenter: state.pickingEpicenter,
    psha: pshaInfoForCity(state.city),
    ...scenarioControlCallbacks,
  });
}

export function loadRiskForCity(city: string, overrides: ScenarioOverrides = {}): void {
  showRiskLoading("Running scenario… (first run per combination takes a while)");
  const hazardCurvePromise: Promise<HazardCurve | null> = overrides.return_period_years
    ? fetchHazardCurve(city, "PGA")
    : Promise.resolve(null);
  const disaggregationPromise: Promise<Disaggregation | null> = overrides.return_period_years
    ? fetchDisaggregation(city, overrides.return_period_years).catch(() => null)
    : Promise.resolve(null);
  Promise.all([
    fetchScenarioRisk(city, overrides),
    fetchScenarioSummary(city, overrides),
    hazardCurvePromise,
    disaggregationPromise,
  ])
    .then(([risk, summary, hazardCurve, disaggregation]) => {
      state.riskData = risk;
      state.scenarioSummary = summary;
      state.scenarioOverrides = overrides;
      state.hazardCurve = hazardCurve;
      state.disaggregation = disaggregation;
      state.riskNumericRange = {};
      for (const attribute of RISK_ATTRIBUTES) {
        if (attribute.kind === "sequential") {
          state.riskNumericRange[attribute.name] = numericRangeOf(risk, attribute.name);
        }
      }
      renderCurrentScenarioPanel();
      renderLayer();
      map.fitBounds(computeBbox(risk), { padding: 40, duration: 500 });
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      showRiskLoading(`Failed to load scenario: ${message}`);
    });
}

export function applyScenarioOverrides(overrides: ScenarioOverrides): void {
  if (!state.city) return;
  setEpicenterPicking(false);
  loadRiskForCity(state.city, overrides);
}

export function resetScenarioOverrides(): void {
  if (!state.city) return;
  setEpicenterPicking(false);
  loadRiskForCity(state.city, {});
}

export function applyReturnPeriod(returnPeriodYears: number): void {
  if (!state.city) return;
  setEpicenterPicking(false);
  loadRiskForCity(state.city, { return_period_years: returnPeriodYears });
}

export function setEpicenterPicking(picking: boolean): void {
  state.pickingEpicenter = picking;
  map.getCanvas().style.cursor = picking ? "crosshair" : "";
}

export function toggleEpicenterPicking(): void {
  setEpicenterPicking(!state.pickingEpicenter);
  renderCurrentScenarioPanel();
}

export function hideScenarioPanelForExposureMode(): void {
  const scenarioPanelEl = document.getElementById("scenario-panel");
  if (scenarioPanelEl) hideScenarioPanel(scenarioPanelEl);
}
