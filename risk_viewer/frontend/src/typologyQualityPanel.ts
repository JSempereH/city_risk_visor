import { ESTIMATED_STROKE_COLOR } from "./colors";

export function renderTypologyQuality(container: HTMLElement, city: string | null, attributeName: string | undefined): void {
  if (!city || attributeName !== "structural_system_class") {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = "";
  const estimatedHint = document.createElement("p");
  estimatedHint.className = "scenario-hint";
  estimatedHint.innerHTML =
    `Buildings outlined in <span style="color:${ESTIMATED_STROKE_COLOR};font-weight:600;">amber</span> have no ` +
    `recorded structural system: the class shown for them is a model's prediction, not confirmed data.`;
  container.appendChild(estimatedHint);
}
