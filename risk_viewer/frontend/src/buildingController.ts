import { fetchVulnerability, type VulnerabilityOverrides } from "./api";
import { renderBuildingSummary, renderOverrideControls, type BuildingSummary } from "./buildingInputsPanel";
import { renderLayer } from "./mapLayers";
import { state } from "./state";
import { createTabs, renderRiskStatStrip } from "./ui";
import { renderTypologyEnsemble, renderVulnerabilityCurves, renderVulnerabilitySummary } from "./vulnerabilityPanel";

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
  overviewResultsEl: HTMLElement,
  curvesEl: HTMLElement,
  onSelectCandidate: (structuralClass: string) => void,
): void {
  overviewResultsEl.innerHTML = "<p>Loading…</p>";
  curvesEl.innerHTML = "";
  fetchVulnerability(building.id, state.buildingOverrides)
    .then((vulnerability) => {
      renderTypologyEnsemble(ensembleEl, vulnerability.typology_ensemble, onSelectCandidate, vulnerability.typology_prior);
      renderVulnerabilitySummary(overviewResultsEl, vulnerability);
      renderVulnerabilityCurves(curvesEl, vulnerability);
    })
    .catch((error: unknown) => {
      const message = error instanceof Error ? error.message : String(error);
      overviewResultsEl.innerHTML = `<p class="error">Failed to load vulnerability data: ${message}</p>`;
    });
}

// Overview / Curves: splits what used to be one long stack (stats,
// identity, model agreement, override inputs, source badge, charts,
// assumptions, all visible at once) into 2 tabs, so a single click only
// ever shows one section's worth of content instead of needing its own
// scroll before you've even opened anything. Model agreement stays on
// Overview with the identity/stats: it's read at the same time as "what
// is this building actually". Override inputs live on Curves instead,
// as a sidebar beside the charts (see .curves-tab-layout in style.css)
// rather than on Overview: their whole point is to see how changing an
// input moves the curves, so they need to be next to the curves, not a
// tab-switch away from them. See ui.ts::createTabs()'s own docstring, and
// #building-panel's fixed (not max-) height in style.css, for why
// switching tabs doesn't resize the panel.
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
    structural_system_confirmed: properties.structural_system_confirmed === true,
    code_quality: String(properties.code_quality ?? "unlabeled"),
  };

  const tabsEl = document.createElement("div");
  content.appendChild(tabsEl);
  const tabs = createTabs(tabsEl, [
    { id: "overview", label: "Overview" },
    { id: "curves", label: "Curves" },
  ]);

  // Overview: headline numbers (risk mode only — an exposure-mode
  // feature has none of these fields), identity, which method produced
  // the result, and model agreement (see .stat-strip in style.css).
  if (state.mode === "risk") {
    const statStripEl = document.createElement("div");
    tabs.panels.overview.appendChild(statStripEl);
    renderRiskStatStrip(statStripEl, properties);
  }
  const summaryEl = document.createElement("div");
  tabs.panels.overview.appendChild(summaryEl);
  renderBuildingSummary(summaryEl, summary);
  const overviewResultsEl = document.createElement("div");
  tabs.panels.overview.appendChild(overviewResultsEl);
  const ensembleEl = document.createElement("div");
  tabs.panels.overview.appendChild(ensembleEl);

  // Curves: the charts on the left, override inputs as a compact
  // vertical sidebar on the right, so changing an input and seeing its
  // effect on the curves happens in the same glance instead of needing
  // a tab switch back to Overview. Model agreement's "see this model's
  // curve" buttons (rendered into ensembleEl above) feed the same
  // overrides state as this sidebar.
  const curvesLayout = document.createElement("div");
  curvesLayout.className = "curves-tab-layout";
  tabs.panels.curves.appendChild(curvesLayout);
  const curvesEl = document.createElement("div");
  curvesEl.className = "curves-tab-main";
  curvesLayout.appendChild(curvesEl);
  const overridesEl = document.createElement("div");
  overridesEl.className = "curves-tab-sidebar";
  curvesLayout.appendChild(overridesEl);

  const onOverrideChange = (overrides: VulnerabilityOverrides) => {
    state.buildingOverrides = overrides;
    renderOverrideControls(overridesEl, summary, state.buildingOverrides, onOverrideChange);
    recomputeVulnerability(summary, ensembleEl, overviewResultsEl, curvesEl, onSelectCandidate);
  };
  const onSelectCandidate = (structuralClass: string) =>
    onOverrideChange({ ...state.buildingOverrides, structural_system_class: structuralClass });

  renderOverrideControls(overridesEl, summary, state.buildingOverrides, onOverrideChange);
  recomputeVulnerability(summary, ensembleEl, overviewResultsEl, curvesEl, onSelectCandidate);
}
