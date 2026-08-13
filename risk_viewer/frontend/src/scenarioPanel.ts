import type { Disaggregation, HazardCurve, ScenarioOverrides, ScenarioSummary } from "./api";
import { renderLineChart } from "./chart";
import { DAMAGE_STATE_COLORS, DAMAGE_STATE_ORDER } from "./colors";

const HAZARD_CURVE_MEAN_COLOR = "#0b5fa8";
const HAZARD_CURVE_BOUND_COLOR = "#a9c9ea";

export interface PshaInfo {
  available: boolean;
  returnPeriods: number[];
}

export interface ScenarioControls {
  overrides: ScenarioOverrides;
  // Typed-or-picked-but-not-yet-applied form values, see
  // state.ts::AppState.scenarioDraft's own comment for why this is
  // separate from `overrides`.
  draft: ScenarioOverrides;
  // Set when the last Apply/return-period/reset attempt failed, so the
  // panel can report it without discarding the still-valid previous
  // scenario and controls (unlike the transient full-panel "Running
  // scenario..." replacement, an error leaves the form in place so the
  // user can fix the value and retry).
  error: string | null;
  pickingEpicenter: boolean;
  psha: PshaInfo;
  onApply: (overrides: ScenarioOverrides) => void;
  onReset: () => void;
  onDraftChange: (patch: Partial<ScenarioOverrides>) => void;
  onTogglePickEpicenter: () => void;
  onSelectReturnPeriod: (years: number) => void;
  onSwitchToDeterministic: () => void;
}

const DAMAGE_STATE_LABELS: Record<string, string> = {
  none: "None",
  slight: "Slight",
  moderate: "Moderate",
  extensive: "Extensive",
  complete: "Complete",
};

const REGIME_LABELS: Record<string, string> = {
  crustal: "shallow crustal",
  interface: "subduction interface",
  intraslab: "subduction intraslab",
};

function formatNumber(value: number): string {
  return Math.round(value).toLocaleString();
}

function formatFatalities(value: number): string {
  return value < 10 ? value.toFixed(1) : Math.round(value).toLocaleString();
}

function formatRange(p10: number, p90: number, decimals: boolean): string {
  const fmt = (v: number) => (decimals ? formatFatalities(v) : formatNumber(v));
  return `${fmt(p10)} to ${fmt(p90)}`;
}

function numberField(
  grid: HTMLElement,
  label: string,
  value: number,
  attrs: { min?: number; max?: number; step?: number },
  onDraftChange?: (value: number) => void,
): HTMLInputElement {
  const field = document.createElement("label");
  field.textContent = label;
  const input = document.createElement("input");
  input.type = "number";
  input.value = String(value);
  if (attrs.min !== undefined) input.min = String(attrs.min);
  if (attrs.max !== undefined) input.max = String(attrs.max);
  if (attrs.step !== undefined) input.step = String(attrs.step);
  // Written back to the draft as the user types, not just read at
  // "Apply" time, so a re-render triggered by something else (picking
  // an epicenter on the map) can restore this value instead of
  // silently reverting it to the last-applied one.
  if (onDraftChange) {
    input.addEventListener("input", () => {
      if (input.value !== "") onDraftChange(Number(input.value));
    });
  }
  field.appendChild(input);
  grid.appendChild(field);
  return input;
}

function poeIn50Years(returnPeriodYears: number): number {
  return 1 - Math.exp(-50 / returnPeriodYears);
}

function renderModeSelector(
  container: HTMLElement,
  summary: ScenarioSummary,
  controls: ScenarioControls,
): void {
  if (!controls.psha.available) return;

  const wrap = document.createElement("div");
  wrap.className = "scenario-mode-selector";

  const label = document.createElement("span");
  label.className = "scenario-mode-label";
  label.textContent = "Hazard model:";
  wrap.appendChild(label);

  const detButton = document.createElement("button");
  detButton.type = "button";
  detButton.textContent = "Deterministic";
  if (summary.scenario.mode === "deterministic") detButton.classList.add("active");
  detButton.addEventListener("click", controls.onSwitchToDeterministic);
  wrap.appendChild(detButton);

  for (const years of controls.psha.returnPeriods) {
    const btn = document.createElement("button");
    btn.type = "button";
    btn.textContent = `PSHA, ${years}yr`;
    if (summary.scenario.mode === "probabilistic" && summary.scenario.return_period_years === years) {
      btn.classList.add("active");
    }
    btn.addEventListener("click", () => controls.onSelectReturnPeriod(years));
    wrap.appendChild(btn);
  }

  container.appendChild(wrap);
}

function formatPoe(poe: number): string {
  return poe >= 0.01 ? `${(poe * 100).toFixed(1)}%` : poe.toExponential(1);
}

function renderHazardCurveChart(container: HTMLElement, summary: ScenarioSummary, curve: HazardCurve | null): void {
  const heading = document.createElement("h3");
  heading.textContent = "Hazard curve (epistemic range)";
  container.appendChild(heading);

  const hint = document.createElement("p");
  hint.className = "scenario-hint";
  hint.textContent =
    "Each point is the probability that PGA exceeds that level within the investigation time. " +
    "It's computed once per ground-motion model (GMPE) in the logic tree: the line is the mean " +
    "across those models, and the shaded band (16th to 84th percentile) shows how much the models " +
    "disagree with each other. That disagreement is one kind of uncertainty, about which model is " +
    "correct. The Monte Carlo range shown further below is a different kind: natural randomness in " +
    "shaking and building damage for one fixed scenario. The two aren't comparable and shouldn't be " +
    "combined.";
  container.appendChild(hint);

  if (!curve || curve.p16 === undefined || curve.p84 === undefined) {
    const notice = document.createElement("p");
    notice.className = "scenario-hint";
    notice.textContent = "Hazard curve unavailable for this scenario.";
    container.appendChild(notice);
    return;
  }

  const chartEl = document.createElement("div");
  container.appendChild(chartEl);

  const epsilon = 1e-8;
  const logLevels = curve.levels.map((v) => Math.log10(v));
  const toLogPoe = (values: number[]) => values.map((v) => Math.log10(Math.max(v, epsilon)));

  const hp = summary.hazard_percentiles;

  const series = [
    { label: "p84", color: HAZARD_CURVE_BOUND_COLOR, y: toLogPoe(curve.p84) },
    { label: "mean", color: HAZARD_CURVE_MEAN_COLOR, y: toLogPoe(curve.mean) },
    { label: "p16", color: HAZARD_CURVE_BOUND_COLOR, y: toLogPoe(curve.p16) },
  ];
  const allY = series.flatMap((s) => s.y);

  renderLineChart(chartEl, {
    width: 320,
    height: 200,
    sharedX: logLevels,
    series,
    xLabel: "PGA (g)",
    yLabel: `PoE in ${curve.investigation_time_years}yr`,
    yDomain: [Math.min(...allY), Math.max(...allY)],
    xFormat: (v) => (10 ** v).toFixed(2),
    yFormat: (v) => formatPoe(10 ** v),
    markerX: hp?.mean !== undefined ? Math.log10(hp.mean) : undefined,
    band: { upperY: toLogPoe(curve.p84), lowerY: toLogPoe(curve.p16), color: HAZARD_CURVE_BOUND_COLOR },
  });
}

function renderDisaggregation(container: HTMLElement, disaggregation: Disaggregation | null): void {
  if (!disaggregation) return;

  const p = document.createElement("p");
  p.className = "scenario-hint";
  p.innerHTML =
    `<strong>Controlling event at this return period:</strong> Mw ${disaggregation.mean_magnitude.toFixed(1)} ` +
    `at ${disaggregation.mean_distance_km.toFixed(0)} km. This is the PGA-weighted mean magnitude/distance across ` +
    `every source contributing to this hazard level, not a single rupture.`;
  container.appendChild(p);
}

function renderCustomScenarioControls(
  container: HTMLElement,
  summary: ScenarioSummary,
  controls: ScenarioControls,
): void {
  const isOverridden = Object.keys(controls.overrides).length > 0;
  const hasPendingDraft = Object.keys(controls.draft).length > 0;

  const details = document.createElement("details");
  details.className = "scenario-controls";
  details.open = isOverridden || controls.pickingEpicenter || hasPendingDraft;

  const summaryEl = document.createElement("summary");
  summaryEl.textContent = isOverridden ? "Custom scenario (edited)" : "Custom scenario";
  details.appendChild(summaryEl);

  const body = document.createElement("div");
  body.className = "scenario-controls-body override-controls";
  details.appendChild(body);

  const hint = document.createElement("p");
  hint.className = "scenario-hint";
  hint.textContent =
    "Adjust magnitude, depth, or epicenter and re-run the scenario. Tectonic regime stays fixed to the source cited above.";
  body.appendChild(hint);

  if (hasPendingDraft) {
    const pendingNotice = document.createElement("p");
    pendingNotice.className = "scenario-pending-notice";
    pendingNotice.textContent = "Not applied yet: click Apply below to run this.";
    body.appendChild(pendingNotice);
  }

  const grid = document.createElement("div");
  grid.className = "override-grid";
  body.appendChild(grid);

  const magnitudeInput = numberField(
    grid,
    "Magnitude",
    controls.draft.magnitude ?? summary.scenario.magnitude,
    { min: 4.5, max: 9.0, step: 0.1 },
    (value) => controls.onDraftChange({ magnitude: value }),
  );
  const depthInput = numberField(
    grid,
    "Depth (km)",
    controls.draft.depth_km ?? summary.scenario.depth_km,
    { min: 1, max: 200, step: 1 },
    (value) => controls.onDraftChange({ depth_km: value }),
  );
  const latInput = numberField(
    grid,
    "Epicenter lat",
    controls.draft.epicenter_lat ?? Number(summary.scenario.epicenter_lat.toFixed(4)),
    { step: 0.01 },
    (value) => controls.onDraftChange({ epicenter_lat: value }),
  );
  const lonInput = numberField(
    grid,
    "Epicenter lon",
    controls.draft.epicenter_lon ?? Number(summary.scenario.epicenter_lon.toFixed(4)),
    { step: 0.01 },
    (value) => controls.onDraftChange({ epicenter_lon: value }),
  );

  const buttonRow = document.createElement("div");
  buttonRow.className = "scenario-button-row";
  body.appendChild(buttonRow);

  const pickButton = document.createElement("button");
  pickButton.type = "button";
  pickButton.textContent = controls.pickingEpicenter ? "Click the map…" : "Pick epicenter on map";
  if (controls.pickingEpicenter) pickButton.classList.add("active");
  pickButton.addEventListener("click", controls.onTogglePickEpicenter);
  buttonRow.appendChild(pickButton);

  const applyButton = document.createElement("button");
  applyButton.type = "button";
  applyButton.className = "primary";
  applyButton.textContent = "Apply";
  applyButton.addEventListener("click", () => {
    controls.onApply({
      magnitude: Number(magnitudeInput.value),
      depth_km: Number(depthInput.value),
      epicenter_lat: Number(latInput.value),
      epicenter_lon: Number(lonInput.value),
    });
  });
  buttonRow.appendChild(applyButton);

  if (isOverridden || hasPendingDraft) {
    const resetButton = document.createElement("button");
    resetButton.type = "button";
    resetButton.textContent = "Reset to default";
    resetButton.addEventListener("click", controls.onReset);
    buttonRow.appendChild(resetButton);
  }

  container.appendChild(details);
}

export function renderScenarioPanel(
  container: HTMLElement,
  summary: ScenarioSummary,
  hazardCurve: HazardCurve | null,
  disaggregation: Disaggregation | null,
  controls: ScenarioControls,
): void {
  container.classList.remove("hidden");
  container.innerHTML = "";

  const heading = document.createElement("h2");
  heading.textContent = summary.scenario.label;
  container.appendChild(heading);

  const meta = document.createElement("p");
  meta.className = "scenario-meta";
  if (summary.scenario.mode === "probabilistic" && summary.scenario.return_period_years) {
    const poePct = (poeIn50Years(summary.scenario.return_period_years) * 100).toFixed(1);
    meta.textContent = `${summary.scenario.return_period_years}-year return period · ${poePct}% probability of exceedance in 50 years`;
  } else {
    meta.textContent = `Mw ${summary.scenario.magnitude.toFixed(1)} · depth ${summary.scenario.depth_km.toFixed(0)} km · ${
      REGIME_LABELS[summary.scenario.tectonic_regime] ?? summary.scenario.tectonic_regime
    }`;
  }
  container.appendChild(meta);

  if (controls.error) {
    const errorNotice = document.createElement("p");
    errorNotice.className = "scenario-error";
    errorNotice.textContent = controls.error;
    container.appendChild(errorNotice);
  }

  const note = document.createElement("p");
  note.className = "scenario-note";
  note.textContent = summary.scenario.source_note;
  container.appendChild(note);

  const prototypeNotice = document.createElement("p");
  prototypeNotice.className = "prototype-notice";
  prototypeNotice.textContent =
    summary.scenario.mode === "probabilistic"
      ? "Probabilistic (PSHA) scenario: mean hazard curve across every combination of seismic source " +
        "and ground-motion model considered plausible for this region, not a single earthquake."
      : "Single deterministic scenario per city, using an elastic estimate of the expected ground-motion response.";
  container.appendChild(prototypeNotice);

  renderModeSelector(container, summary, controls);
  if (summary.scenario.mode === "probabilistic") {
    renderHazardCurveChart(container, summary, hazardCurve);
    renderDisaggregation(container, disaggregation);
  }

  if (summary.scenario.mode === "deterministic") {
    renderCustomScenarioControls(container, summary, controls);
  }

  const mc = summary.monte_carlo;

  const statsHeading = document.createElement("h3");
  statsHeading.textContent = "Scenario summary";
  container.appendChild(statsHeading);

  const mcNote = document.createElement("p");
  mcNote.className = "scenario-hint";
  mcNote.textContent =
    `P10 to P90 range from ${mc.n_samples}-trial Monte Carlo sampling of ground-motion and damage-state uncertainty.`;
  container.appendChild(mcNote);

  const stats = document.createElement("table");
  stats.className = "scenario-stats";
  const rows: [string, string, boolean?][] = [
    ["Buildings modelled", `${formatNumber(summary.n_available)} / ${formatNumber(summary.n_buildings)}`],
    ["Population (day)", formatNumber(summary.total_population_day)],
    ["Population (night)", formatNumber(summary.total_population_night)],
    ["Expected casualties (day)", formatNumber(summary.total_casualties_day)],
    ["P10 to P90 range", formatRange(mc.casualties_day.p10, mc.casualties_day.p90, false), true],
    ["Fatalities (day)", formatFatalities(summary.total_casualties_day_fatalities)],
    ["P10 to P90 range", formatRange(mc.fatalities_day.p10, mc.fatalities_day.p90, true), true],
    ["Expected casualties (night)", formatNumber(summary.total_casualties_night)],
    ["P10 to P90 range", formatRange(mc.casualties_night.p10, mc.casualties_night.p90, false), true],
    ["Fatalities (night)", formatFatalities(summary.total_casualties_night_fatalities)],
    ["P10 to P90 range", formatRange(mc.fatalities_night.p10, mc.fatalities_night.p90, true), true],
  ];
  for (const [label, value, sub] of rows) {
    const tr = document.createElement("tr");
    if (sub) tr.className = "scenario-stats-sub";
    const th = document.createElement("th");
    th.textContent = label;
    const td = document.createElement("td");
    td.textContent = value;
    tr.appendChild(th);
    tr.appendChild(td);
    stats.appendChild(tr);
  }
  container.appendChild(stats);

  const distHeading = document.createElement("h3");
  distHeading.textContent = "Damage state distribution";
  container.appendChild(distHeading);

  const distList = document.createElement("ul");
  distList.className = "legend-list";
  const total = summary.n_available || 1;
  for (const state of DAMAGE_STATE_ORDER) {
    const count = summary.damage_state_counts[state] ?? 0;
    const item = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.backgroundColor = DAMAGE_STATE_COLORS[state];
    const label = document.createElement("span");
    const pct = ((count / total) * 100).toFixed(0);
    label.textContent = `${DAMAGE_STATE_LABELS[state]}: ${count} (${pct}%)`;
    item.appendChild(swatch);
    item.appendChild(label);
    distList.appendChild(item);
  }
  container.appendChild(distList);
}

export function hideScenarioPanel(container: HTMLElement): void {
  container.classList.add("hidden");
  container.innerHTML = "";
}
