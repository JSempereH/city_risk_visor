import {
  clearTypologyPrior,
  fetchAvailableTypologyClasses,
  fetchTypologyPrior,
  setTypologyPrior,
  type TypologyPrior,
} from "./api";
import { selectBuilding } from "./buildingController";
import { state } from "./state";

// Called once from main.ts's bootstrap (initSettingsPanel's own param),
// so this module never imports main.ts directly -- main.ts already
// imports buildingController.ts (which this module also imports), and a
// settingsPanel -> main.ts import would create a cycle.
type DataChangedHandler = () => Promise<void>;

let onDataChanged: DataChangedHandler = async () => {};

function closePanel(): void {
  document.getElementById("settings-panel")?.classList.add("hidden");
}

function openPanel(): void {
  document.getElementById("settings-panel")?.classList.remove("hidden");
  renderSettingsPanel();
}

export function initSettingsPanel(handler: DataChangedHandler): void {
  onDataChanged = handler;
  document.getElementById("settings-toggle")?.addEventListener("click", () => {
    const panel = document.getElementById("settings-panel");
    if (panel?.classList.contains("hidden")) openPanel();
    else closePanel();
  });
  document.getElementById("settings-panel-close")?.addEventListener("click", closePanel);
}

// After the exposure data refreshes (onDataChanged), the currently open
// building panel (if any) still shows whatever it fetched before the
// prior changed -- re-selecting it from its own (now-refreshed)
// feature properties in state.data re-runs the same fetch+render path a
// real click would, so its structural type/curves catch up too.
function refreshOpenBuildingPanel(): void {
  const id = state.selectedBuildingId;
  if (!id) return;
  const feature = state.data?.features.find((f) => f.properties?.id === id);
  if (feature?.properties) selectBuilding(id, feature.properties);
}

async function applyDataChange(): Promise<void> {
  await onDataChanged();
  refreshOpenBuildingPanel();
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

async function renderSettingsPanel(): Promise<void> {
  const content = document.getElementById("settings-panel-content");
  if (!content) return;
  content.innerHTML = "";

  const heading = document.createElement("h2");
  heading.textContent = "Settings";
  content.appendChild(heading);

  const city = state.city;
  if (!city) {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = "Select a city first.";
    content.appendChild(note);
    return;
  }

  const sectionHeading = document.createElement("h3");
  sectionHeading.textContent = "Typology prior";
  content.appendChild(sectionHeading);

  const explainer = document.createElement("p");
  explainer.className = "hint";
  explainer.textContent =
    "If you know roughly how this population's building types break down, enter it below. " +
    "Only buildings the model estimated (not ones with a confirmed structural type) are adjusted, " +
    "and your percentages already account for the confirmed buildings.";
  content.appendChild(explainer);

  const loading = document.createElement("p");
  loading.className = "hint";
  loading.textContent = "Loading…";
  content.appendChild(loading);

  let classesResult, currentPrior;
  try {
    [classesResult, currentPrior] = await Promise.all([
      fetchAvailableTypologyClasses(city),
      fetchTypologyPrior(city),
    ]);
  } catch (error: unknown) {
    loading.textContent = `Failed to load: ${error instanceof Error ? error.message : String(error)}`;
    return;
  }
  loading.remove();

  const classes = classesResult.classes;
  if (classes.length === 0) {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = "This city's model has no estimated buildings to adjust.";
    content.appendChild(note);
    return;
  }

  if (!classesResult.locally_validated) {
    const caveat = document.createElement("p");
    caveat.className = "ensemble-note";
    caveat.textContent =
      "This city's model learned from other cities' buildings, not this one, so its accuracy hasn't " +
      "been checked against real examples here. Treat its estimates, and any prior you set below, as " +
      "a rough guess.";
    content.appendChild(caveat);
  }

  renderPriorForm(content, city, classes, currentPrior);
}

function renderPriorForm(
  content: HTMLElement,
  city: string,
  classes: string[],
  currentPrior: TypologyPrior | null,
): void {
  content.querySelector(".prior-form")?.remove();
  const form = document.createElement("div");
  form.className = "prior-form";
  content.appendChild(form);

  const inputs: Record<string, HTMLInputElement> = {};
  const grid = document.createElement("div");
  grid.className = "prior-class-grid";
  form.appendChild(grid);

  for (const cls of classes) {
    const label = document.createElement("label");
    label.className = "prior-class-row";
    const name = document.createElement("span");
    name.textContent = cls;
    label.appendChild(name);

    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = "100";
    input.step = "1";
    const current = currentPrior?.proportions[cls];
    input.value = current !== undefined ? String(Math.round(current * 100)) : "";
    input.placeholder = "0";
    inputs[cls] = input;
    label.appendChild(input);

    const percentSign = document.createElement("span");
    percentSign.textContent = "%";
    label.appendChild(percentSign);

    grid.appendChild(label);
  }

  const totalLine = document.createElement("p");
  totalLine.className = "prior-total-line";
  form.appendChild(totalLine);

  function updateTotal(): void {
    const total = classes.reduce((sum, cls) => sum + (Number(inputs[cls].value) || 0), 0);
    totalLine.textContent = `Total: ${total}%`;
    totalLine.classList.toggle("prior-total-warning", Math.abs(total - 100) > 0.5);
  }
  for (const cls of classes) inputs[cls].addEventListener("input", updateTotal);
  updateTotal();

  const alphaField = document.createElement("label");
  alphaField.className = "prior-alpha-field";
  alphaField.textContent = "How much to trust this over the model's own prediction";
  const alphaInput = document.createElement("input");
  alphaInput.type = "range";
  alphaInput.min = "0";
  alphaInput.max = "100";
  alphaInput.step = "5";
  alphaInput.value = currentPrior ? String(Math.round(currentPrior.alpha * 100)) : "60";
  const alphaValue = document.createElement("span");
  alphaValue.className = "prior-alpha-value";
  alphaValue.textContent = `${alphaInput.value}%`;
  alphaInput.addEventListener("input", () => {
    alphaValue.textContent = `${alphaInput.value}%`;
  });
  alphaField.appendChild(alphaInput);
  alphaField.appendChild(alphaValue);
  form.appendChild(alphaField);

  const resultArea = document.createElement("div");
  resultArea.className = "prior-result";
  form.appendChild(resultArea);

  function showError(message: string): void {
    resultArea.innerHTML = "";
    const error = document.createElement("p");
    error.className = "error";
    error.textContent = message;
    resultArea.appendChild(error);
  }

  function showFeasibility(prior: TypologyPrior): void {
    resultArea.innerHTML = "";
    if (!prior.feasibility) return;
    const { n_ground_truth, n_estimated, n_total } = prior.feasibility;
    const note = document.createElement("p");
    note.className = "hint prior-feasibility-note";
    note.textContent =
      `Applied: ${n_ground_truth} of ${n_total} buildings already had a confirmed type; ` +
      `the remaining ${n_estimated} were adjusted toward your target.`;
    resultArea.appendChild(note);
  }
  // currentPrior.feasibility is only ever present right after a
  // successful apply (see the apply button's handler below, which
  // re-renders this whole form with the just-applied response) -- shows
  // immediately instead of needing a second render pass to appear.
  if (currentPrior) showFeasibility(currentPrior);

  const buttonRow = document.createElement("div");
  buttonRow.className = "prior-button-row";
  form.appendChild(buttonRow);

  const applyButton = document.createElement("button");
  applyButton.type = "button";
  applyButton.className = "prior-apply-button";
  applyButton.textContent = "Apply";
  applyButton.addEventListener("click", async () => {
    const proportions: Record<string, number> = {};
    for (const cls of classes) {
      const value = Number(inputs[cls].value) || 0;
      if (value > 0) proportions[cls] = value / 100;
    }
    const total = Object.values(proportions).reduce((sum, v) => sum + v, 0);
    if (Math.abs(total - 1.0) > 0.005) {
      showError(`Percentages must add up to 100% (currently ${(total * 100).toFixed(0)}%).`);
      return;
    }
    applyButton.disabled = true;
    applyButton.textContent = "Applying…";
    try {
      const prior = await setTypologyPrior(city, proportions, Number(alphaInput.value) / 100);
      // Rebuilds just the form from this response directly (it already
      // has everything: proportions, alpha, feasibility) rather than
      // calling renderSettingsPanel() again -- that would re-fetch via
      // GET (which never carries feasibility, only the POST response
      // does, see api.ts's TypologyPrior docstring) and wipe the
      // feasibility note this same click just earned before it was ever
      // seen. renderPriorForm() below removes this old .prior-form
      // itself before appending the new one (see its own top).
      renderPriorForm(content, city, classes, prior);
      await applyDataChange();
    } catch (error: unknown) {
      showError(error instanceof Error ? error.message : String(error));
    } finally {
      applyButton.disabled = false;
      applyButton.textContent = "Apply";
    }
  });
  buttonRow.appendChild(applyButton);

  if (currentPrior) {
    const clearButton = document.createElement("button");
    clearButton.type = "button";
    clearButton.className = "prior-clear-button";
    clearButton.textContent = "Clear";
    clearButton.addEventListener("click", async () => {
      clearButton.disabled = true;
      try {
        await clearTypologyPrior(city);
        await applyDataChange();
        renderSettingsPanel();
      } catch (error: unknown) {
        showError(error instanceof Error ? error.message : String(error));
      } finally {
        clearButton.disabled = false;
      }
    });
    buttonRow.appendChild(clearButton);

    const activeNote = document.createElement("p");
    activeNote.className = "hint prior-active-note";
    activeNote.textContent = `A prior is currently applied for ${city} (${classes
      .filter((cls) => currentPrior.proportions[cls])
      .map((cls) => `${cls} ${formatPercent(currentPrior.proportions[cls])}`)
      .join(", ")}).`;
    form.insertBefore(activeNote, grid);
  }
}
