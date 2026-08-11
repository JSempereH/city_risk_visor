import { fetchVulnerability, type VulnerabilityOverrides } from "./api";
import { renderBuildingSummary, renderOverrideControls, type BuildingSummary } from "./buildingInputsPanel";
import { renderLayer } from "./mapLayers";
import { state } from "./state";
import { renderTypologyEnsemble, renderVulnerabilityResults } from "./vulnerabilityPanel";

function openBuildingPanel(): void {
  document.getElementById("building-panel")?.classList.remove("hidden");
}

export function closeBuildingPanel(): void {
  document.getElementById("building-panel")?.classList.add("hidden");
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

  const summaryEl = document.createElement("div");
  const ensembleEl = document.createElement("div");
  const overridesEl = document.createElement("div");
  const resultsEl = document.createElement("div");
  content.appendChild(summaryEl);
  content.appendChild(ensembleEl);
  content.appendChild(overridesEl);
  content.appendChild(resultsEl);

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
