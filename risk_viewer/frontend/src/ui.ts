import type { LayerAttribute } from "./api";
import { sequentialLegendSteps, UNLABELED_COLOR, UNLABELED_VALUE } from "./colors";

export function populateAttributeSelect(
  select: HTMLSelectElement,
  attributes: LayerAttribute[],
  onChange: (attribute: LayerAttribute) => void,
): void {
  select.innerHTML = "";
  for (const attribute of attributes) {
    const option = document.createElement("option");
    option.value = attribute.name;
    option.textContent = attribute.label;
    select.appendChild(option);
  }
  select.addEventListener("change", () => {
    const attribute = attributes.find((a) => a.name === select.value);
    if (attribute) onChange(attribute);
  });
}

export function populateCitySelect(
  select: HTMLSelectElement,
  cities: string[],
  onChange: (city: string | null) => void,
): void {
  select.innerHTML = "";
  const allOption = document.createElement("option");
  allOption.value = "";
  allOption.textContent = "All cities";
  select.appendChild(allOption);
  for (const city of cities) {
    const option = document.createElement("option");
    option.value = city;
    option.textContent = city.replace(/_/g, " ");
    select.appendChild(option);
  }
  select.addEventListener("change", () => {
    onChange(select.value || null);
  });
}

export function renderCategoricalLegend(
  container: HTMLElement,
  attributeLabel: string,
  colors: Record<string, string>,
): void {
  const entries = Object.entries(colors).sort(([a], [b]) => {
    if (a === UNLABELED_VALUE) return 1;
    if (b === UNLABELED_VALUE) return -1;
    return a.localeCompare(b);
  });
  container.innerHTML = `<h2>${attributeLabel}</h2>`;
  const list = document.createElement("ul");
  list.className = "legend-list";
  for (const [value, color] of entries) {
    const item = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.backgroundColor = color;
    const label = document.createElement("span");
    label.textContent = value === UNLABELED_VALUE ? "unlabeled" : value;
    item.appendChild(swatch);
    item.appendChild(label);
    list.appendChild(item);
  }
  container.appendChild(list);
}

export function renderSequentialLegend(
  container: HTMLElement,
  attributeLabel: string,
  min: number,
  max: number,
): void {
  container.innerHTML = `<h2>${attributeLabel}</h2>`;
  const steps = sequentialLegendSteps(min, max);
  const list = document.createElement("ul");
  list.className = "legend-list";
  for (const step of steps) {
    const item = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.backgroundColor = step.color;
    const label = document.createElement("span");
    label.textContent = step.value.toFixed(1);
    item.appendChild(swatch);
    item.appendChild(label);
    list.appendChild(item);
  }
  const nullItem = document.createElement("li");
  const nullSwatch = document.createElement("span");
  nullSwatch.className = "legend-swatch";
  nullSwatch.style.backgroundColor = UNLABELED_COLOR;
  const nullLabel = document.createElement("span");
  nullLabel.textContent = "no data";
  nullItem.appendChild(nullSwatch);
  nullItem.appendChild(nullLabel);
  list.appendChild(nullItem);
  container.appendChild(list);
}

const PROPERTY_LABELS: Record<string, string> = {
  id: "ID",
  city: "City",
  n_floors: "Floors",
  height: "Height (m)",
  year: "Year built",
  code_quality: "Code quality",
  roof_material: "Roof material",
  structural_system: "Structural system (raw)",
  structural_system_class: "Structural system",
};

export function formatTooltip(properties: Record<string, unknown>): string {
  const rows = Object.entries(properties)
    // structural_system_estimated rides along as a plain suffix on
    // structural_system_class's own row below, not a separate row.
    .filter(([key, value]) => key !== "structural_system_estimated" && (typeof value !== "object" || value === null))
    .map(([key, value]) => {
      const label = PROPERTY_LABELS[key] ?? key;
      let displayValue = value === null || value === undefined || value === "" ? "N/A" : String(value);
      if (key === "structural_system_class" && properties.structural_system_estimated === true) {
        displayValue += " (estimated)";
      }
      return `<tr><th>${label}</th><td>${displayValue}</td></tr>`;
    })
    .join("");
  return `<table>${rows}</table>`;
}

const CURVE_SOURCE_LABELS: Record<string, string> = {
  ml_capacity_model: "ML model",
  gem_global_vulnerability: "GEM model",
  published_fallback: "Published fallback",
};

const RISK_TOOLTIP_FIELDS: [string, string, (v: unknown) => string][] = [
  ["id", "ID", String],
  ["city", "City", String],
  ["structural_system_class", "Structural system", String],
  ["curve_source", "Curve source", (v) => CURVE_SOURCE_LABELS[v as string] ?? "N/A"],
  ["expected_damage_state", "Expected damage state", String],
  ["demand_sd_mm", "Demand Sd (mm)", (v) => (typeof v === "number" ? v.toFixed(1) : "N/A")],
  [
    "performance_point_method",
    "Performance point",
    (v) => (v === "atc40" ? "ATC-40 (nonlinear)" : v === "elastic" ? "Elastic" : "N/A"),
  ],
  ["ductility", "Ductility (μ)", (v) => (typeof v === "number" ? v.toFixed(2) : "N/A")],
  ["population_night", "Population (night)", (v) => (typeof v === "number" ? v.toFixed(1) : "N/A")],
  ["casualties_night_total", "Expected casualties (night)", (v) => (typeof v === "number" ? v.toFixed(2) : "N/A")],
  ["casualties_night_severity_4", "Fatalities (night)", (v) => (typeof v === "number" ? v.toFixed(3) : "N/A")],
  ["total_beta", "Combined uncertainty (β)", (v) => (typeof v === "number" ? v.toFixed(2) : "N/A")],
];

export function formatRiskTooltip(properties: Record<string, unknown>): string {
  if (properties.risk_available === false) {
    return `<table><tr><th>ID</th><td>${String(properties.id ?? "N/A")}</td></tr><tr><th colspan="2">${String(
      properties.risk_reason ?? "No risk estimate available",
    )}</td></tr></table>`;
  }
  const rows = RISK_TOOLTIP_FIELDS.map(([key, label, format]) => {
    const value = properties[key];
    let displayValue = value === null || value === undefined ? "N/A" : format(value);
    if (key === "structural_system_class" && properties.structural_system_estimated === true) {
      displayValue += " (estimated)";
    }
    return `<tr><th>${label}</th><td>${displayValue}</td></tr>`;
  }).join("");
  return `<table>${rows}</table>`;
}
