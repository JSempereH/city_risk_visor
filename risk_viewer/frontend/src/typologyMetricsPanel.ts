import { fetchEnsembleQuality, fetchFeatureImportance, type EnsembleQuality, type FeatureImportance } from "./api";
import { amberSequentialColor, readableTextColor } from "./colors";
import { state } from "./state";

type Tab = "quality" | "features";

// Persists across opens (not reset per-open): switching cities or
// reopening the panel keeps whichever tab the user was last looking at,
// the same convenience as e.g. the mode-select tab staying put.
let activeTab: Tab = "quality";

function closePanel(): void {
  document.getElementById("typology-metrics-panel")?.classList.add("hidden");
}

function formatPercent(value: number): string {
  return `${(value * 100).toFixed(1)}%`;
}

function formatCi(ci: { lower: number; upper: number }): string {
  return `${formatPercent(ci.lower)}–${formatPercent(ci.upper)}`;
}

function statsTable(quality: EnsembleQuality): HTMLTableElement {
  const table = document.createElement("table");
  table.className = "scenario-stats";

  function row(label: string, value: string, sub?: string): void {
    const tr = document.createElement("tr");
    const th = document.createElement("th");
    th.textContent = label;
    const td = document.createElement("td");
    td.textContent = value;
    tr.appendChild(th);
    tr.appendChild(td);
    table.appendChild(tr);
    if (sub) {
      const subTr = document.createElement("tr");
      subTr.className = "scenario-stats-sub";
      const subTh = document.createElement("th");
      const subTd = document.createElement("td");
      subTd.textContent = sub;
      subTr.appendChild(subTh);
      subTr.appendChild(subTd);
      table.appendChild(subTr);
    }
  }

  if (quality.accuracy !== null) row("Accuracy", formatPercent(quality.accuracy));
  if (quality.ensemble_f1_macro !== null) {
    row(
      "F1 (macro)",
      formatPercent(quality.ensemble_f1_macro),
      quality.ensemble_f1_macro_ci ? `95% CI: ${formatCi(quality.ensemble_f1_macro_ci)}` : undefined,
    );
  }
  if (quality.ensemble_f1_weighted !== null) row("F1 (weighted)", formatPercent(quality.ensemble_f1_weighted));
  row(
    "Held-out sample",
    `${quality.n_held_out_test} of ${quality.n_predictions_csv}`,
    "genuinely unseen by training, not the full predictions file",
  );
  row(
    "Inter-model agreement",
    quality.inter_model_fleiss_kappa.toFixed(2),
    `Fleiss' κ, 95% CI: ${formatCi(quality.inter_model_fleiss_kappa_ci)}`,
  );
  return table;
}

// The app's own amber ramp (colors.ts::amberSequentialColor), not the
// map's blue one -- this panel is app chrome, not a map data layer, and
// amber is this app's own accent (the active mode pill, the 3D toggle
// when on). A heavily-populated cell still reads as "more" the same way
// a numeric map attribute does, just in the app's own color language.
function confusionMatrixTable(quality: EnsembleQuality): HTMLElement | null {
  const matrix = quality.confusion_matrix;
  if (!matrix) return null;
  const classes = quality.classes;
  const max = Math.max(1, ...matrix.flat());

  const wrap = document.createElement("div");
  wrap.className = "confusion-matrix-wrap";

  const heading = document.createElement("p");
  heading.className = "confusion-matrix-heading";
  heading.textContent = "Confusion matrix (rows: true class, columns: predicted class)";
  wrap.appendChild(heading);

  const table = document.createElement("table");
  table.className = "confusion-matrix";

  const headRow = document.createElement("tr");
  headRow.appendChild(document.createElement("th"));
  for (const cls of classes) {
    const th = document.createElement("th");
    th.textContent = cls;
    headRow.appendChild(th);
  }
  table.appendChild(headRow);

  matrix.forEach((rowCounts, i) => {
    const tr = document.createElement("tr");
    const rowHeader = document.createElement("th");
    rowHeader.textContent = classes[i];
    rowHeader.scope = "row";
    tr.appendChild(rowHeader);
    rowCounts.forEach((count) => {
      const td = document.createElement("td");
      const [r, g, b] = amberSequentialColor(count, 0, max);
      const hex = `#${[r, g, b].map((c) => c.toString(16).padStart(2, "0")).join("")}`;
      td.style.backgroundColor = hex;
      td.style.color = readableTextColor(hex);
      td.textContent = String(count);
      tr.appendChild(td);
    });
    table.appendChild(tr);
  });
  wrap.appendChild(table);
  return wrap;
}

// SHAP/built-in consensus ranking (ml_structural_system::explainability,
// see risk_viewer_feature_importance.py for how this was computed against
// each city's already-trained models) as a horizontal bar list, longest
// (most consistently important) bar first. mean_rank isn't a 0-1
// importance score, so bar length is scaled relative to this city's own
// best/worst shown rank, not an absolute magnitude comparable across
// cities.
function featureImportanceList(fi: FeatureImportance): HTMLElement {
  const wrap = document.createElement("div");
  wrap.className = "feature-importance-wrap";

  const heading = document.createElement("p");
  heading.className = "confusion-matrix-heading";
  heading.textContent =
    `Consensus ranking across the ensemble's 3 models (n=${fi.n_samples} samples). ` +
    `Longer bar = more consistently important.`;
  wrap.appendChild(heading);

  const ranks = fi.consensus_ranking.map((f) => f.mean_rank);
  const minRank = Math.min(...ranks);
  const maxRank = Math.max(...ranks);

  const list = document.createElement("div");
  list.className = "feature-importance-list";
  fi.consensus_ranking.forEach((f, i) => {
    const row = document.createElement("div");
    row.className = "feature-importance-row";

    const label = document.createElement("span");
    label.className = "feature-importance-label";
    label.textContent = `${i + 1}. ${f.feature}`;
    label.title = f.feature;
    row.appendChild(label);

    const track = document.createElement("div");
    track.className = "feature-importance-bar-track";
    const bar = document.createElement("div");
    bar.className = "feature-importance-bar";
    const t = maxRank === minRank ? 1 : 1 - (f.mean_rank - minRank) / (maxRank - minRank);
    bar.style.width = `${Math.max(8, t * 100)}%`;
    track.appendChild(bar);
    row.appendChild(track);

    list.appendChild(row);
  });
  wrap.appendChild(list);
  return wrap;
}

function renderTabs(city: string): HTMLElement {
  const tabs = document.createElement("div");
  tabs.className = "typology-metrics-tabs";

  function tabButton(tab: Tab, label: string): HTMLButtonElement {
    const button = document.createElement("button");
    button.type = "button";
    button.textContent = label;
    button.className = tab === activeTab ? "active" : "";
    button.addEventListener("click", () => {
      if (activeTab === tab) return;
      activeTab = tab;
      renderPanel(city);
    });
    return button;
  }

  tabs.appendChild(tabButton("quality", "Model quality"));
  tabs.appendChild(tabButton("features", "Feature importance"));
  return tabs;
}

async function renderQualityTab(content: HTMLElement, city: string): Promise<void> {
  const loading = document.createElement("p");
  loading.className = "hint";
  loading.textContent = "Loading…";
  content.appendChild(loading);

  let quality: EnsembleQuality;
  try {
    quality = await fetchEnsembleQuality(city);
  } catch (error: unknown) {
    // The backend's own 404 detail already says plainly there's no
    // held-out quality data for this city (e.g. Lomas del Centinela,
    // whose ensemble has no local ground truth to score against).
    loading.textContent = error instanceof Error ? error.message : String(error);
    return;
  }
  loading.remove();

  if (!quality.has_ground_truth) {
    const note = document.createElement("p");
    note.className = "hint";
    note.textContent = `${city} has no held-out ground truth to score this classifier against.`;
    content.appendChild(note);
    return;
  }

  content.appendChild(statsTable(quality));
  const matrixEl = confusionMatrixTable(quality);
  if (matrixEl) content.appendChild(matrixEl);
}

async function renderFeaturesTab(content: HTMLElement, city: string): Promise<void> {
  const loading = document.createElement("p");
  loading.className = "hint";
  loading.textContent = "Loading…";
  content.appendChild(loading);

  let importance: FeatureImportance;
  try {
    importance = await fetchFeatureImportance(city);
  } catch (error: unknown) {
    loading.textContent = error instanceof Error ? error.message : String(error);
    return;
  }
  loading.remove();
  content.appendChild(featureImportanceList(importance));
}

async function renderPanel(city: string): Promise<void> {
  const content = document.getElementById("typology-metrics-panel-content");
  if (!content) return;
  content.innerHTML = "";

  const heading = document.createElement("h2");
  heading.textContent = "Structural typology";
  content.appendChild(heading);

  const subtitle = document.createElement("p");
  subtitle.className = "hint";
  subtitle.textContent = city;
  content.appendChild(subtitle);

  content.appendChild(renderTabs(city));

  if (activeTab === "quality") await renderQualityTab(content, city);
  else await renderFeaturesTab(content, city);
}

function openPanel(city: string): void {
  document.getElementById("typology-metrics-panel")?.classList.remove("hidden");
  renderPanel(city);
}

export function initTypologyMetricsPanel(): void {
  document.getElementById("typology-metrics-toggle")?.addEventListener("click", () => {
    const panel = document.getElementById("typology-metrics-panel");
    if (!state.city) return;
    if (panel?.classList.contains("hidden")) openPanel(state.city);
    else closePanel();
  });
  document.getElementById("typology-metrics-panel-close")?.addEventListener("click", closePanel);
}

/** Shows/enables the toggle button only when there's a specific city
 * selected and the map is actually colored by structural system --
 * otherwise "model quality" has no clear subject (matches
 * typologyQualityPanel.ts's own gating for the glowing-outline hint). */
export function updateTypologyMetricsAvailability(city: string | null, attributeName: string | undefined): void {
  const button = document.getElementById("typology-metrics-toggle");
  if (!button) return;
  const available = Boolean(city) && attributeName === "structural_system_class";
  button.classList.toggle("hidden", !available);
  if (!available) closePanel();
}
