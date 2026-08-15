import type { LayerAttribute } from "./api";
import { DAMAGE_STATE_COLORS, readableTextColor, sequentialLegendSteps, UNLABELED_COLOR, UNLABELED_VALUE } from "./colors";

export interface DropdownOption {
  value: string;
  label: string;
}

export interface DropdownHandle {
  setValue: (value: string) => void;
  getValue: () => string;
}

// One open dropdown at a time: each instance registers its own closer here
// so a click on dropdown B can close an already-open dropdown A, without
// every instance needing to know about every other one.
const openDropdownClosers = new Set<() => void>();

function closeOtherDropdowns(except: () => void): void {
  for (const close of openDropdownClosers) {
    if (close !== except) close();
  }
}

/**
 * A styleable stand-in for a native <select>: same "one value from a
 * list" job, but the dropdown list is DOM/CSS (see .dropdown-list in
 * style.css) instead of the browser's own popup, which can't be
 * restyled to match the panel's dark glass look.
 */
export function createDropdown(
  container: HTMLElement,
  options: DropdownOption[],
  onChange: (value: string) => void,
): DropdownHandle {
  container.innerHTML = "";
  container.classList.add("dropdown");

  const toggle = document.createElement("button");
  toggle.type = "button";
  toggle.className = "dropdown-toggle";
  toggle.setAttribute("aria-haspopup", "listbox");
  toggle.setAttribute("aria-expanded", "false");

  const valueEl = document.createElement("span");
  valueEl.className = "dropdown-value";
  toggle.appendChild(valueEl);

  const caret = document.createElementNS("http://www.w3.org/2000/svg", "svg");
  caret.setAttribute("class", "dropdown-caret");
  caret.setAttribute("width", "10");
  caret.setAttribute("height", "6");
  caret.setAttribute("viewBox", "0 0 10 6");
  caret.setAttribute("aria-hidden", "true");
  const caretPath = document.createElementNS("http://www.w3.org/2000/svg", "path");
  caretPath.setAttribute("d", "M1 1l4 4 4-4");
  caretPath.setAttribute("fill", "none");
  caretPath.setAttribute("stroke", "currentColor");
  caretPath.setAttribute("stroke-width", "1.5");
  caret.appendChild(caretPath);
  toggle.appendChild(caret);

  const list = document.createElement("ul");
  list.className = "dropdown-list";
  list.setAttribute("role", "listbox");
  list.hidden = true;

  container.appendChild(toggle);
  container.appendChild(list);

  let current = options[0]?.value ?? "";

  const close = () => {
    list.hidden = true;
    container.removeAttribute("data-open");
    toggle.setAttribute("aria-expanded", "false");
  };
  const open = () => {
    closeOtherDropdowns(close);
    list.hidden = false;
    container.setAttribute("data-open", "");
    toggle.setAttribute("aria-expanded", "true");
  };
  openDropdownClosers.add(close);

  function renderOptions(): void {
    list.innerHTML = "";
    for (const option of options) {
      const item = document.createElement("li");
      item.setAttribute("role", "option");
      item.tabIndex = 0;
      item.textContent = option.label;
      if (option.value === current) {
        item.classList.add("selected");
        item.setAttribute("aria-selected", "true");
      }
      const select = () => {
        current = option.value;
        valueEl.textContent = option.label;
        renderOptions();
        close();
        toggle.focus();
        onChange(option.value);
      };
      item.addEventListener("click", select);
      item.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          select();
        }
      });
      list.appendChild(item);
    }
  }

  toggle.addEventListener("click", () => {
    if (list.hidden) open();
    else close();
  });
  document.addEventListener("click", (event) => {
    if (!container.contains(event.target as Node)) close();
  });
  toggle.addEventListener("keydown", (event) => {
    if (event.key === "Escape") close();
  });

  renderOptions();
  const initial = options.find((o) => o.value === current);
  valueEl.textContent = initial?.label ?? "";

  return {
    setValue(value: string) {
      current = value;
      const option = options.find((o) => o.value === value);
      valueEl.textContent = option?.label ?? value;
      renderOptions();
    },
    getValue: () => current,
  };
}

/** A horizontal, mutually-exclusive button group (e.g. Layer:
 * Exposure/Risk) — the segmented-control equivalent of a radio group. */
export function initSegmentedControl(
  container: HTMLElement,
  onSelect: (value: string) => void,
): { setValue: (value: string) => void } {
  const buttons = Array.from(container.querySelectorAll<HTMLButtonElement>("button[data-value]"));
  for (const button of buttons) {
    button.addEventListener("click", () => {
      if (button.classList.contains("active")) return;
      for (const other of buttons) other.classList.remove("active");
      button.classList.add("active");
      onSelect(button.dataset.value ?? "");
    });
  }
  return {
    setValue(value: string) {
      for (const button of buttons) button.classList.toggle("active", button.dataset.value === value);
    },
  };
}

export function populateAttributeSelect(
  container: HTMLElement,
  attributes: LayerAttribute[],
  onChange: (attribute: LayerAttribute) => void,
): DropdownHandle {
  return createDropdown(
    container,
    attributes.map((a) => ({ value: a.name, label: a.label })),
    (value) => {
      const attribute = attributes.find((a) => a.name === value);
      if (attribute) onChange(attribute);
    },
  );
}

export function populateCitySelect(
  container: HTMLElement,
  cities: string[],
  onChange: (city: string | null) => void,
): DropdownHandle {
  return createDropdown(
    container,
    cities.map((c) => ({ value: c, label: c.replace(/_/g, " ") })),
    (value) => onChange(value || null),
  );
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
  clampedAbove = false,
): void {
  container.innerHTML = `<h2>${attributeLabel}</h2>`;
  const steps = sequentialLegendSteps(min, max);
  const list = document.createElement("ul");
  list.className = "legend-list";
  steps.forEach((step, index) => {
    const item = document.createElement("li");
    const swatch = document.createElement("span");
    swatch.className = "legend-swatch";
    swatch.style.backgroundColor = step.color;
    const label = document.createElement("span");
    // The top step means "this value or more" whenever the domain was
    // clamped below the true max (see state.ts::isClampedAbove), so it
    // stays honest instead of silently implying this is the true max.
    const isTopStep = index === steps.length - 1;
    label.textContent = isTopStep && clampedAbove ? `${step.value.toFixed(1)}+` : step.value.toFixed(1);
    item.appendChild(swatch);
    item.appendChild(label);
    list.appendChild(item);
  });
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
      let displayValue =
        value === null || value === undefined || value === ""
          ? "N/A"
          : key === "height" && typeof value === "number"
            ? value.toFixed(1)
            : String(value);
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

const DAMAGE_STATE_PILL_LABELS: Record<string, string> = {
  none: "None",
  slight: "Slight",
  moderate: "Moderate",
  extensive: "Extensive",
  complete: "Complete",
};

/**
 * Headline numbers laid out horizontally above the building panel's two
 * columns (see .stat-strip in style.css) — expected damage plus day AND
 * night population/casualties, the figures worth reading at a glance
 * before the attribute table and charts below. Risk-mode only: these
 * fields (see app/risk/api.py's per-building properties) don't exist on
 * an exposure-mode feature.
 */
export function renderRiskStatStrip(container: HTMLElement, properties: Record<string, unknown>): void {
  container.innerHTML = "";
  container.className = "stat-strip";
  if (properties.risk_available === false) return;

  const num = (value: unknown): number | null => (typeof value === "number" ? value : null);
  const fmt = (value: unknown, digits = 0): string => {
    const n = num(value);
    return n === null ? "N/A" : n.toFixed(digits);
  };

  const damageState = typeof properties.expected_damage_state === "string" ? properties.expected_damage_state : null;
  if (damageState) {
    const tile = document.createElement("div");
    tile.className = "stat-tile stat-tile-damage";
    const pillColor = DAMAGE_STATE_COLORS[damageState] ?? UNLABELED_COLOR;
    const pill = document.createElement("span");
    pill.className = "damage-pill";
    pill.style.background = pillColor;
    pill.style.color = readableTextColor(pillColor);
    pill.textContent = DAMAGE_STATE_PILL_LABELS[damageState] ?? damageState;
    const label = document.createElement("span");
    label.className = "stat-label";
    label.textContent = "Expected damage";
    tile.appendChild(pill);
    tile.appendChild(label);
    container.appendChild(tile);
  }

  const tiles: { value: string; unit?: string; label: string }[] = [
    { value: fmt(properties.demand_sd_mm, 1), unit: "mm", label: "Demand Sd" },
    { value: fmt(properties.population_day), label: "Population (day)" },
    { value: fmt(properties.population_night), label: "Population (night)" },
    { value: fmt(properties.casualties_day_total, 2), label: "Casualties (day)" },
    { value: fmt(properties.casualties_night_total, 2), label: "Casualties (night)" },
  ];
  for (const { value, unit, label } of tiles) {
    const tile = document.createElement("div");
    tile.className = "stat-tile";
    const valueEl = document.createElement("span");
    valueEl.className = "stat-value";
    valueEl.textContent = value;
    if (unit) {
      const unitEl = document.createElement("span");
      unitEl.className = "stat-unit";
      unitEl.textContent = unit;
      valueEl.appendChild(unitEl);
    }
    const labelEl = document.createElement("span");
    labelEl.className = "stat-label";
    labelEl.textContent = label;
    tile.appendChild(valueEl);
    tile.appendChild(labelEl);
    container.appendChild(tile);
  }
}
