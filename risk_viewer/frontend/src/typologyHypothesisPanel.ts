import type { TypologyHypothesis } from "./api";

// Same order/codes as buildingInputsPanel.ts's STRUCTURAL_CLASSES: the
// full taxonomy the backend's typology_hypothesis module understands
// (backend/app/typology_hypothesis.py::KNOWN_CLASSES).
const STRUCTURAL_CLASSES = ["ADO", "CR", "M", "MCF", "MR", "MUR", "W"];

export interface TypologyHypothesisControls {
  hypothesis: TypologyHypothesis | null;
  draft: Record<string, string>;
  error: string | null;
  onApply: (proportions: Record<string, number>) => void;
  onClear: () => void;
  onDraftChange: (patch: Record<string, string>) => void;
}

function draftValue(controls: TypologyHypothesisControls, cls: string): string {
  if (cls in controls.draft) return controls.draft[cls];
  if (controls.hypothesis) return String(Math.round(controls.hypothesis.proportions[cls] * 100 || 0));
  return "";
}

export function renderTypologyHypothesisPanel(container: HTMLElement, controls: TypologyHypothesisControls): void {
  container.innerHTML = "";

  const hasPendingDraft = Object.keys(controls.draft).length > 0;

  const details = document.createElement("details");
  details.className = "scenario-controls";
  details.open = controls.hypothesis !== null || hasPendingDraft;

  const summaryEl = document.createElement("summary");
  summaryEl.textContent = controls.hypothesis ? "Expert typology hypothesis (active)" : "Expert typology hypothesis";
  details.appendChild(summaryEl);

  const body = document.createElement("div");
  body.className = "scenario-controls-body override-controls";
  details.appendChild(body);

  const hint = document.createElement("p");
  hint.className = "scenario-hint";
  hint.textContent =
    "No confirmed structural survey for this city? State your own belief about the mix of building types as " +
    "percentages and re-run the scenario against it. Each building is assigned a class so the overall mix " +
    "matches what you enter, and the added uncertainty scales with how mixed the hypothesis is: a confident " +
    "guess (e.g. 95% one type) adds little, an even split across types adds more.";
  body.appendChild(hint);

  if (controls.error) {
    const errorNotice = document.createElement("p");
    errorNotice.className = "scenario-error";
    errorNotice.textContent = controls.error;
    body.appendChild(errorNotice);
  }

  if (hasPendingDraft) {
    const pendingNotice = document.createElement("p");
    pendingNotice.className = "scenario-pending-notice";
    pendingNotice.textContent = "Not applied yet: click Apply below to run this.";
    body.appendChild(pendingNotice);
  }

  const grid = document.createElement("div");
  grid.className = "override-grid";
  body.appendChild(grid);

  const sumNote = document.createElement("p");
  sumNote.className = "scenario-hint";
  body.appendChild(sumNote);

  const inputs: Record<string, HTMLInputElement> = {};
  const updateSumNote = () => {
    const sum = STRUCTURAL_CLASSES.reduce((total, cls) => total + (Number(inputs[cls].value) || 0), 0);
    sumNote.textContent = `Total: ${sum}% (must sum to 100%)`;
  };
  for (const cls of STRUCTURAL_CLASSES) {
    const field = document.createElement("label");
    field.textContent = `${cls} (%)`;
    const input = document.createElement("input");
    input.type = "number";
    input.min = "0";
    input.max = "100";
    input.step = "1";
    input.value = draftValue(controls, cls);
    // Updates the running total directly, without going through a full
    // app-state re-render on every keystroke: same reasoning as
    // scenarioPanel.ts's numberField, a re-render here would steal focus
    // from the field the user is actively typing in. onDraftChange still
    // persists the value to app state, just doesn't itself trigger a
    // render.
    input.addEventListener("input", () => {
      controls.onDraftChange({ [cls]: input.value });
      updateSumNote();
    });
    field.appendChild(input);
    grid.appendChild(field);
    inputs[cls] = input;
  }
  updateSumNote();

  if (controls.hypothesis) {
    const info = document.createElement("p");
    info.className = "scenario-hint";
    info.textContent =
      `Active hypothesis contributes an extra typology uncertainty of β=${controls.hypothesis.typology_beta.toFixed(2)} ` +
      `to every affected building's combined uncertainty (normalized mix entropy: ${controls.hypothesis.normalized_entropy.toFixed(2)}).`;
    body.appendChild(info);
  }

  const buttonRow = document.createElement("div");
  buttonRow.className = "scenario-button-row";
  body.appendChild(buttonRow);

  const applyButton = document.createElement("button");
  applyButton.type = "button";
  applyButton.className = "primary";
  applyButton.textContent = "Apply hypothesis";
  applyButton.addEventListener("click", () => {
    const proportions: Record<string, number> = {};
    for (const cls of STRUCTURAL_CLASSES) proportions[cls] = (Number(inputs[cls].value) || 0) / 100;
    controls.onApply(proportions);
  });
  buttonRow.appendChild(applyButton);

  if (controls.hypothesis || hasPendingDraft) {
    const clearButton = document.createElement("button");
    clearButton.type = "button";
    clearButton.textContent = "Clear hypothesis";
    clearButton.addEventListener("click", controls.onClear);
    buttonRow.appendChild(clearButton);
  }

  container.appendChild(details);
}
