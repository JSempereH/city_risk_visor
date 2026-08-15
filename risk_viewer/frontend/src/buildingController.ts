import { fetchVulnerability, type VulnerabilityOverrides } from "./api";
import { renderBuildingSummary, renderOverrideControls, type BuildingSummary } from "./buildingInputsPanel";
import { renderLayer } from "./mapLayers";
import { state } from "./state";
import { renderRiskStatStrip } from "./ui";
import { renderTypologyEnsemble, renderVulnerabilityResults } from "./vulnerabilityPanel";

// Always the bottom drawer (see #building-panel in style.css) — no more
// compact side-card state to toggle between, per feedback that jumping
// from a right-side card to a bottom drawer read as inconsistent.
function openBuildingPanel(): void {
  document.getElementById("building-panel")?.classList.remove("hidden");
  // The drawer overlaps #controls rather than dodging it (see
  // style.css); fading #controls while a building is open is what keeps
  // that overlap reading as intentional instead of a layout collision.
  document.getElementById("app")?.classList.add("building-panel-open");
}

/** Wired once at bootstrap; the panel itself is (re)populated per
 * building by selectBuilding() below. */
export function initBuildingPanelControls(): void {
  document.getElementById("building-panel-close")?.addEventListener("click", closeBuildingPanel);
}

export function closeBuildingPanel(): void {
  document.getElementById("building-panel")?.classList.add("hidden");
  document.getElementById("app")?.classList.remove("building-panel-open");
  state.selectedBuildingId = null;
  renderLayer();
}

function recomputeVulnerability(
  building: BuildingSummary,
  ensembleEl: HTMLElement,
  resultsEl: HTMLElement,
  onSelectCandidate: (structuralClass: string) => void,
): void {
  resultsEl.innerHTML = "<p>Loading…</p>";
  fetchVulnerability(building.id, state.buildingOverrides)
    .then((vulnerability) => {
      renderTypologyEnsemble(ensembleEl, vulnerability.typology_ensemble, onSelectCandidate);
      renderVulnerabilityResults(resultsEl, vulnerability);
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      resultsEl.innerHTML = `<p class="error">Failed to load vulnerability data: ${message}</p>`;
    });
}

export function selectBuilding(id: string, properties: Record<string, unknown>): void {
  state.selectedBuildingId = id;
  state.buildingOverrides = {};
  renderLayer();
  openBuildingPanel();

  const content = document.getElementById("building-panel-content");
  if (!content) return;
  content.innerHTML = "";

  const summary: BuildingSummary = {
    id,
    city: String(properties.city ?? ""),
    n_floors: typeof properties.n_floors === "number" ? properties.n_floors : null,
    height: typeof properties.height === "number" ? properties.height : null,
    structural_system:
      typeof properties.structural_system === "string" ? properties.structural_system : null,
    structural_system_class: String(properties.structural_system_class ?? "unlabeled"),
    structural_system_estimated: properties.structural_system_estimated === true,
    code_quality: String(properties.code_quality ?? "unlabeled"),
  };

  // Headline numbers (risk mode only — an exposure-mode feature has none
  // of these fields) above the two columns below, see .stat-strip in
  // style.css.
  if (state.mode === "risk") {
    const statStripEl = document.createElement("div");
    content.appendChild(statStripEl);
    renderRiskStatStrip(statStripEl, properties);
  }

  // Two columns: identity/inputs on the left, the capacity/fragility
  // charts on the right (see .building-panel-body in style.css).
  const body = document.createElement("div");
  body.className = "building-panel-body";
  const left = document.createElement("div");
  left.className = "building-panel-left";
  const right = document.createElement("div");
  right.className = "building-panel-right";
  body.appendChild(left);
  body.appendChild(right);
  content.appendChild(body);

  const summaryEl = document.createElement("div");
  const ensembleEl = document.createElement("div");
  const overridesEl = document.createElement("div");
  const resultsEl = document.createElement("div");
  left.appendChild(summaryEl);
  left.appendChild(ensembleEl);
  left.appendChild(overridesEl);
  right.appendChild(resultsEl);

  renderBuildingSummary(summaryEl, summary);

  const onOverrideChange = (overrides: VulnerabilityOverrides) => {
    state.buildingOverrides = overrides;
    renderOverrideControls(overridesEl, summary, state.buildingOverrides, onOverrideChange);
    recomputeVulnerability(summary, ensembleEl, resultsEl, onSelectCandidate);
  };
  const onSelectCandidate = (structuralClass: string) =>
    onOverrideChange({ ...state.buildingOverrides, structural_system_class: structuralClass });

  renderOverrideControls(overridesEl, summary, state.buildingOverrides, onOverrideChange);
  recomputeVulnerability(summary, ensembleEl, resultsEl, onSelectCandidate);
}
