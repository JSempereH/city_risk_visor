import type { VulnerabilityOverrides } from "./api";
import { createDropdown } from "./ui";

export interface BuildingSummary {
  id: string;
  city: string;
  n_floors: number | null;
  height: number | null;
  structural_system: string | null;
  structural_system_class: string;
  structural_system_estimated: boolean;
  // A genuine per-building record -- NOT just "not ML-estimated", which
  // is also true for a city-wide fallback assumption applied where even
  // the typology ensemble had no per-building prediction to fall back on
  // (e.g. lomas_centinela's ~54 year-less buildings). See mapLayers.ts's
  // own isConfirmedStructuralSystem for the fuller reasoning; this panel
  // uses the same flag so it never reads as more certain than the map.
  structural_system_confirmed: boolean;
  code_quality: string;
}

const STRUCTURAL_CLASSES = ["ADO", "CR", "M", "MCF", "MR", "MUR", "W"];
const CODE_QUALITIES = ["pre_code", "low_code", "medium_code", "high_code"];

function structuralSystemCell(building: BuildingSummary): string {
  if (building.structural_system_confirmed) {
    return `${building.structural_system_class} (raw: ${building.structural_system ?? "N/A"})`;
  }
  if (building.structural_system_estimated) {
    return (
      `${building.structural_system_class} ` +
      `<span class="estimated-badge" title="No recorded structural system for this building. ` +
      `Filled in from a model's prediction instead.">estimated</span>`
    );
  }
  return (
    `${building.structural_system_class} ` +
    `<span class="estimated-badge" title="No confirmed structural system for this building or model ` +
    `prediction to fall back on. Uses a documented, neighborhood-wide assumption instead.">assumed</span>`
  );
}

export function renderBuildingSummary(container: HTMLElement, building: BuildingSummary): void {
  container.innerHTML = `
    <h2>${building.id}</h2>
    <table class="building-summary">
      <tr><th>City</th><td>${building.city}</td></tr>
      <tr><th>Floors</th><td>${building.n_floors ?? "N/A"}</td></tr>
      <tr><th>Height (m)</th><td>${building.height === null ? "N/A" : building.height.toFixed(1)}</td></tr>
      <tr><th>Structural system</th><td>${structuralSystemCell(building)}</td></tr>
    </table>
  `;
}

/**
 * Persistent "what if" controls: overriding any field recomputes the
 * capacity/fragility result for a hypothetical building without touching
 * the stored data. Blank/"Actual" means "use the real recorded value".
 * Lives in the Curves tab's sidebar (see buildingController.ts and
 * .curves-tab-sidebar/.override-grid in style.css) — a single narrow
 * column, not the 2-column grid a wider placement could afford, since
 * the whole point of putting it beside the charts is to keep it compact
 * enough to leave the charts most of the width.
 *
 * The structural-type/code-quality fields use this app's own styled
 * dropdown (ui.ts::createDropdown), matching the city/attribute
 * dropdowns elsewhere, instead of a native <select> which read as an
 * inconsistent control. createDropdown() needs to be called again on
 * the SAME container element every time its value/options should
 * change (that's how it cleans up its own previous document click
 * listener, see containerCleanup in ui.ts) -- this function is called
 * fresh on every override change (buildingController.ts's
 * onOverrideChange), so the skeleton (including the two dropdown
 * sub-containers) is only built once per building and reused across
 * calls, rather than recreated from scratch each time, which would
 * leak one listener per change instead of replacing it.
 */
export function renderOverrideControls(
  container: HTMLElement,
  building: BuildingSummary,
  current: VulnerabilityOverrides,
  onChange: (overrides: VulnerabilityOverrides) => void,
): void {
  const emit = (patch: Partial<VulnerabilityOverrides>) => {
    onChange({ ...current, ...patch });
  };

  let classDropdownEl = container.querySelector<HTMLElement>('[data-role="structural-type-dropdown"]');
  let floorsInput = container.querySelector<HTMLInputElement>('[data-role="floors-input"]');
  let qualityDropdownEl = container.querySelector<HTMLElement>('[data-role="code-quality-dropdown"]');
  let resetButton = container.querySelector<HTMLButtonElement>('[data-role="reset-button"]');

  if (!classDropdownEl || !floorsInput || !qualityDropdownEl || !resetButton) {
    container.innerHTML = "";
    container.className = "override-controls";

    const heading = document.createElement("h3");
    heading.textContent = "Override inputs";
    container.appendChild(heading);

    const grid = document.createElement("div");
    grid.className = "override-grid";
    container.appendChild(grid);

    const classField = document.createElement("label");
    classField.textContent = "Structural type";
    classDropdownEl = document.createElement("div");
    classDropdownEl.dataset.role = "structural-type-dropdown";
    classField.appendChild(classDropdownEl);
    grid.appendChild(classField);

    const floorsField = document.createElement("label");
    floorsField.textContent = "Floors";
    floorsInput = document.createElement("input");
    floorsInput.dataset.role = "floors-input";
    floorsInput.type = "number";
    floorsInput.min = "1";
    floorsField.appendChild(floorsInput);
    grid.appendChild(floorsField);

    const qualityField = document.createElement("label");
    qualityField.textContent = "Code quality";
    qualityDropdownEl = document.createElement("div");
    qualityDropdownEl.dataset.role = "code-quality-dropdown";
    qualityField.appendChild(qualityDropdownEl);
    grid.appendChild(qualityField);

    resetButton = document.createElement("button");
    resetButton.type = "button";
    resetButton.dataset.role = "reset-button";
    resetButton.className = "override-reset";
    resetButton.textContent = "Reset to actual";
    resetButton.addEventListener("click", () => onChange({}));
    container.appendChild(resetButton);
  }

  createDropdown(
    classDropdownEl,
    // The actual class appears once, labeled "(actual)" in place rather
    // than as a second, separately-pinned entry with the same value --
    // it used to show up twice (its own "Actual (X)" entry, plus X again
    // in the plain list below), which read as two different choices for
    // what was really the same one.
    STRUCTURAL_CLASSES.map((cls) => ({
      value: cls === building.structural_system_class ? "" : cls,
      label: cls === building.structural_system_class ? `${cls} (actual)` : cls,
    })),
    (value) => emit({ structural_system_class: value || undefined }),
  ).setValue(current.structural_system_class ?? "");

  floorsInput.placeholder = building.n_floors !== null ? String(building.n_floors) : "N/A";
  floorsInput.value = current.n_floors !== undefined ? String(current.n_floors) : "";
  floorsInput.onchange = () => emit({ n_floors: floorsInput!.value === "" ? undefined : Number(floorsInput!.value) });

  createDropdown(
    qualityDropdownEl,
    // Same "actual appears once, not twice" fix as the structural-type
    // dropdown above.
    CODE_QUALITIES.map((cq) => ({
      value: cq === building.code_quality ? "" : cq,
      label: cq === building.code_quality ? `${cq} (actual)` : cq,
    })),
    (value) => emit({ code_quality: value || undefined }),
  ).setValue(current.code_quality ?? "");

  const hasAnyOverride = Object.values(current).some((v) => v !== undefined);
  resetButton.classList.toggle("hidden", !hasAnyOverride);
}
