import type { VulnerabilityOverrides } from "./api";

export interface BuildingSummary {
  id: string;
  city: string;
  n_floors: number | null;
  height: number | null;
  structural_system: string | null;
  structural_system_class: string;
  structural_system_estimated: boolean;
  code_quality: string;
}

const STRUCTURAL_CLASSES = ["ADO", "CR", "M", "W"];
const CODE_QUALITIES = ["pre_code", "low_code", "medium_code", "high_code"];

function structuralSystemCell(building: BuildingSummary): string {
  if (building.structural_system_estimated) {
    return (
      `${building.structural_system_class} ` +
      `<span class="estimated-badge" title="No recorded structural system for this building. ` +
      `Filled in from a model's prediction instead.">estimated</span>`
    );
  }
  return `${building.structural_system_class} (raw: ${building.structural_system ?? "N/A"})`;
}

export function renderBuildingSummary(container: HTMLElement, building: BuildingSummary): void {
  container.innerHTML = `
    <h2>${building.id}</h2>
    <table class="building-summary">
      <tr><th>City</th><td>${building.city}</td></tr>
      <tr><th>Floors</th><td>${building.n_floors ?? "N/A"}</td></tr>
      <tr><th>Height (m)</th><td>${building.height ?? "N/A"}</td></tr>
      <tr><th>Structural system</th><td>${structuralSystemCell(building)}</td></tr>
    </table>
  `;
}

/**
 * Persistent "what if" controls: overriding any field recomputes the
 * capacity/fragility result for a hypothetical building without touching
 * the stored data. Blank/"Actual" means "use the real recorded value".
 */
export function renderOverrideControls(
  container: HTMLElement,
  building: BuildingSummary,
  current: VulnerabilityOverrides,
  onChange: (overrides: VulnerabilityOverrides) => void,
): void {
  container.innerHTML = "";
  container.className = "override-controls";

  const heading = document.createElement("h3");
  heading.textContent = "Override inputs";
  container.appendChild(heading);

  const grid = document.createElement("div");
  grid.className = "override-grid";
  container.appendChild(grid);

  const emit = (patch: Partial<VulnerabilityOverrides>) => {
    onChange({ ...current, ...patch });
  };

  const classField = document.createElement("label");
  classField.textContent = "Structural type";
  const classSelect = document.createElement("select");
  classSelect.appendChild(new Option(`Actual (${building.structural_system_class})`, ""));
  for (const cls of STRUCTURAL_CLASSES) classSelect.appendChild(new Option(cls, cls));
  classSelect.value = current.structural_system_class ?? "";
  classSelect.addEventListener("change", () =>
    emit({ structural_system_class: classSelect.value || undefined }),
  );
  classField.appendChild(classSelect);
  grid.appendChild(classField);

  const floorsField = document.createElement("label");
  floorsField.textContent = "Floors";
  const floorsInput = document.createElement("input");
  floorsInput.type = "number";
  floorsInput.min = "1";
  floorsInput.placeholder = building.n_floors !== null ? String(building.n_floors) : "N/A";
  floorsInput.value = current.n_floors !== undefined ? String(current.n_floors) : "";
  floorsInput.addEventListener("change", () =>
    emit({ n_floors: floorsInput.value === "" ? undefined : Number(floorsInput.value) }),
  );
  floorsField.appendChild(floorsInput);
  grid.appendChild(floorsField);

  const heightField = document.createElement("label");
  heightField.textContent = "Height (m)";
  const heightInput = document.createElement("input");
  heightInput.type = "number";
  heightInput.min = "1";
  heightInput.step = "0.5";
  heightInput.placeholder = building.height !== null ? String(building.height) : "N/A";
  heightInput.value = current.height !== undefined ? String(current.height) : "";
  heightInput.addEventListener("change", () =>
    emit({ height: heightInput.value === "" ? undefined : Number(heightInput.value) }),
  );
  heightField.appendChild(heightInput);
  grid.appendChild(heightField);

  const qualityField = document.createElement("label");
  qualityField.textContent = "Code quality";
  const qualitySelect = document.createElement("select");
  qualitySelect.appendChild(new Option(`Actual (${building.code_quality})`, ""));
  for (const cq of CODE_QUALITIES) qualitySelect.appendChild(new Option(cq, cq));
  qualitySelect.value = current.code_quality ?? "";
  qualitySelect.addEventListener("change", () =>
    emit({ code_quality: qualitySelect.value || undefined }),
  );
  qualityField.appendChild(qualitySelect);
  grid.appendChild(qualityField);

  const hasAnyOverride = Object.values(current).some((v) => v !== undefined);
  if (hasAnyOverride) {
    const resetButton = document.createElement("button");
    resetButton.type = "button";
    resetButton.className = "override-reset";
    resetButton.textContent = "Reset to actual";
    resetButton.addEventListener("click", () => onChange({}));
    container.appendChild(resetButton);
  }
}
