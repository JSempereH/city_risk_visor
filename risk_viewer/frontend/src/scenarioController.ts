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
  onDraftChange: updateScenarioDraft,
  onTogglePickEpicenter: toggleEpicenterPicking,
  onSelectReturnPeriod: applyReturnPeriod,
  onSwitchToDeterministic: resetScenarioOverrides,
};

function renderCurrentScenarioPanel(): void {
  const panel = document.getElementById("scenario-panel");
  if (!panel || !state.scenarioSummary || !state.city) return;
  renderScenarioPanel(panel, state.scenarioSummary, state.hazardCurve, state.disaggregation, {
    overrides: state.scenarioOverrides,
    draft: state.scenarioDraft,
    error: state.scenarioError,
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
      // The applied values now match what's shown (summary.scenario.*),
      // and there's nothing left unapplied to restore across a
      // re-render, so both reset here rather than lingering from before
      // this successful run.
      state.scenarioDraft = {};
      state.scenarioError = null;
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
      // Deliberately not showRiskLoading(...): that fully replaces the
      // panel with a bare paragraph, losing the form the user would
      // need to fix a bad value and retry. Re-rendering the normal
      // panel with an error notice keeps the previous (still valid)
      // scenario and controls in place, and leaves the draft (whatever
      // was typed or picked) untouched so nothing has to be re-entered.
      state.scenarioError = message;
      if (state.scenarioSummary) {
        renderCurrentScenarioPanel();
      } else {
        showRiskLoading(`Failed to load scenario: ${message}`);
      }
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
  state.scenarioDraft = {};
  state.scenarioError = null;
  loadRiskForCity(state.city, {});
}

export function applyReturnPeriod(returnPeriodYears: number): void {
  if (!state.city) return;
  setEpicenterPicking(false);
  // A return period replaces magnitude/depth/epicenter entirely (see
  // the backend's "cannot combine" validation), so any pending draft
  // for those fields no longer applies to this mode.
  state.scenarioDraft = {};
  state.scenarioError = null;
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

// Called from the map's click handler (main.ts) while picking mode is
// on. Only updates the draft and re-renders the form, it does not run
// the scenario, so it never overwrites a magnitude/depth the user
// already typed but hadn't applied yet (see state.ts::scenarioDraft).
export function pickEpicenter(lat: number, lon: number): void {
  state.scenarioDraft = { ...state.scenarioDraft, epicenter_lat: lat, epicenter_lon: lon };
  state.scenarioError = null;
  setEpicenterPicking(false);
  renderCurrentScenarioPanel();
}

function updateScenarioDraft(patch: Partial<ScenarioOverrides>): void {
  state.scenarioDraft = { ...state.scenarioDraft, ...patch };
  state.scenarioError = null;
  // Not re-rendering here: the input the user is actively typing in
  // already shows what they typed (it's the DOM's own value), and a
  // re-render on every keystroke would steal focus/cursor position from
  // it for no benefit. The draft only needs to be *readable* for the
  // next render some other action triggers (picking a point, toggling
  // pick mode, etc.), not to itself cause one.
}

export function hideScenarioPanelForExposureMode(): void {
  const scenarioPanelEl = document.getElementById("scenario-panel");
  if (scenarioPanelEl) hideScenarioPanel(scenarioPanelEl);
}
