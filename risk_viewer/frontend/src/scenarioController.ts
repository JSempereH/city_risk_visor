import {
  clearTypologyHypothesis,
  fetchDisaggregation,
  fetchHazardCurve,
  fetchScenarioRisk,
  fetchScenarioSummary,
  fetchTypologyHypothesis,
  setTypologyHypothesis,
  type Disaggregation,
  type HazardCurve,
  type ScenarioOverrides,
} from "./api";
import { computeBbox, map, renderLayer, startEpicenterPulse, stopEpicenterPulse } from "./mapLayers";
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

const typologyHypothesisControlCallbacks = {
  onApply: applyTypologyHypothesis,
  onClear: clearActiveTypologyHypothesis,
  onDraftChange: updateTypologyHypothesisDraft,
};

function renderCurrentScenarioPanel(): void {
  const panel = document.getElementById("scenario-panel");
  if (!panel || !state.scenarioSummary || !state.city) return;
  renderScenarioPanel(
    panel,
    state.scenarioSummary,
    state.hazardCurve,
    state.disaggregation,
    {
      overrides: state.scenarioOverrides,
      draft: state.scenarioDraft,
      error: state.scenarioError,
      pickingEpicenter: state.pickingEpicenter,
      psha: pshaInfoForCity(state.city),
      ...scenarioControlCallbacks,
    },
    {
      hypothesis: state.typologyHypothesis,
      draft: state.typologyHypothesisDraft,
      error: state.typologyHypothesisError,
      ...typologyHypothesisControlCallbacks,
    },
  );
}

// Bumped at the start of every loadRiskForCity() call; a response only
// gets applied if it's still the most recent request when it resolves.
// Fixes a real race: switching to risk mode (which loads its own
// default city) and picking a different city right after fires two
// overlapping requests, and without this guard whichever one's network
// response happened to land last would win, regardless of which was
// requested last -- so a slower first response could overwrite the
// second, correct one after the fact.
let riskRequestSeq = 0;

export function loadRiskForCity(city: string, overrides: ScenarioOverrides = {}): void {
  const requestSeq = ++riskRequestSeq;
  // Rings stay invisible (not started) if there's no epicenter on screen
  // yet to pulse from -- e.g. the very first scenario load of the
  // session, before any scenarioSummary exists -- see mapLayers.ts's
  // epicenterPosition()/pulseRingLayers().
  startEpicenterPulse();
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
    // Re-synced on every load (city switch, override apply/reset, or a
    // hypothesis apply/clear itself), since the hypothesis is process-
    // lifetime backend state per city, not something this frontend owns:
    // see backend/app/typology_hypothesis.py::set_hypothesis()'s
    // docstring.
    fetchTypologyHypothesis(city),
  ])
    .then(([risk, summary, hazardCurve, disaggregation, typologyHypothesis]) => {
      if (requestSeq !== riskRequestSeq) return; // a newer request has since been issued
      stopEpicenterPulse();
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
      state.typologyHypothesis = typologyHypothesis;
      state.typologyHypothesisDraft = {};
      state.typologyHypothesisError = null;
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
      if (requestSeq !== riskRequestSeq) return; // a newer request has since been issued
      stopEpicenterPulse();
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

function applyTypologyHypothesis(proportions: Record<string, number>): void {
  if (!state.city) return;
  const city = state.city;
  setTypologyHypothesis(city, proportions)
    .then(() => {
      // Re-runs the scenario against the newly active hypothesis (the
      // whole point, see typologyHypothesisPanel.ts's hint text): the
      // backend has already stored it, this just fetches the updated
      // result and re-syncs state.typologyHypothesis from the same
      // fetchTypologyHypothesis() call loadRiskForCity always makes.
      loadRiskForCity(city, state.scenarioOverrides);
    })
    .catch((error: unknown) => {
      // Deliberately does not touch state.typologyHypothesis or reload
      // the scenario: an invalid hypothesis (e.g. proportions not
      // summing to 1) was never accepted by the backend, so the
      // previous (still valid) result and draft stay in place, same
      // pattern as loadRiskForCity's own error handling above.
      state.typologyHypothesisError = error instanceof Error ? error.message : String(error);
      renderCurrentScenarioPanel();
    });
}

function clearActiveTypologyHypothesis(): void {
  if (!state.city) return;
  const city = state.city;
  clearTypologyHypothesis(city)
    .then(() => loadRiskForCity(city, state.scenarioOverrides))
    .catch((error: unknown) => {
      state.typologyHypothesisError = error instanceof Error ? error.message : String(error);
      renderCurrentScenarioPanel();
    });
}

function updateTypologyHypothesisDraft(patch: Record<string, string>): void {
  state.typologyHypothesisDraft = { ...state.typologyHypothesisDraft, ...patch };
  state.typologyHypothesisError = null;
  // Not re-rendering here, same reasoning as updateScenarioDraft()
  // below: the field being typed into already shows what was typed, and
  // typologyHypothesisPanel.ts updates its own running-total note
  // directly rather than through a full re-render.
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
  // Move the map's epicenter marker to the picked point right away,
  // rather than leaving it at the last *applied* location until the
  // scenario re-runs (see mapLayers.ts::epicenterLayer()).
  renderLayer();
}

function updateScenarioDraft(patch: Partial<ScenarioOverrides>): void {
  state.scenarioDraft = { ...state.scenarioDraft, ...patch };
  state.scenarioError = null;
  // Not re-rendering the scenario panel here: the input the user is
  // actively typing in already shows what they typed (it's the DOM's
  // own value), and a re-render on every keystroke would steal focus/
  // cursor position from it for no benefit. The draft only needs to be
  // *readable* for the next panel render some other action triggers
  // (picking a point, toggling pick mode, etc.), not to itself cause one.
  //
  // The map is a different story: it has no focus/cursor state to lose,
  // so a typed epicenter_lat/epicenter_lon can move the pin live too.
  if ("epicenter_lat" in patch || "epicenter_lon" in patch) renderLayer();
}

export function hideScenarioPanelForExposureMode(): void {
  const scenarioPanelEl = document.getElementById("scenario-panel");
  if (scenarioPanelEl) hideScenarioPanel(scenarioPanelEl);
}
