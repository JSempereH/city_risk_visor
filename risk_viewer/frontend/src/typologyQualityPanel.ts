import { CONFIRMED_GLOW_COLOR } from "./colors";

export function renderTypologyQuality(container: HTMLElement, city: string | null, attributeName: string | undefined): void {
  if (!city || attributeName !== "structural_system_class") {
    container.innerHTML = "";
    return;
  }
  container.innerHTML = "";
  const estimatedHint = document.createElement("p");
  estimatedHint.className = "scenario-hint";
  estimatedHint.innerHTML =
    `Buildings with a <span style="color:${CONFIRMED_GLOW_COLOR};font-weight:600;">glowing white</span> outline ` +
    `have a confirmed structural system.`;
  container.appendChild(estimatedHint);
}
