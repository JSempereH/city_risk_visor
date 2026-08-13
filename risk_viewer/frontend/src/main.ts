import type { Layer, LayerAttribute } from "./api";
import { fetchLayers, fetchLayerData, fetchLegend, fetchScenarios } from "./api";
import { populateAttributeSelect, populateCitySelect } from "./ui";
import { closeBuildingPanel, selectBuilding } from "./buildingController";
import { computeBbox, map, renderLayer, setBuildingClickHandler } from "./mapLayers";
import {
  hideScenarioPanelForExposureMode,
  loadRiskForCity,
  pickEpicenter,
  setEpicenterPicking,
} from "./scenarioController";
import { activeAttributes, filteredExposureData, numericRangeOf, state, type Mode } from "./state";
import "./style.css";

const API_BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "http://localhost:8001";

function applyAttributeOptionsForMode(): void {
  const attributeSelect = document.getElementById("attribute-select") as HTMLSelectElement;
  const attributes = activeAttributes();
  populateAttributeSelect(attributeSelect, attributes, selectAttribute);
  const first = attributes[0];
  if (first) {
    state.attribute = first;
    attributeSelect.value = first.name;
  }
}

function selectMode(mode: Mode): void {
  state.mode = mode;
  const subtitle = document.getElementById("mode-subtitle");
  const hint = document.getElementById("mode-hint");

  if (mode === "exposure") {
    if (subtitle) subtitle.textContent = "Exposure & typology";
    if (hint) hint.textContent = "Click a building to see its capacity & fragility curves.";
    hideScenarioPanelForExposureMode();
    setEpicenterPicking(false);
    applyAttributeOptionsForMode();
    renderLayer();
  } else {
    if (subtitle) subtitle.textContent = "Seismic risk scenario";
    if (hint) hint.textContent = "Adjustable scenario per city, see the panel above for sources and controls.";
    applyAttributeOptionsForMode();
    const citySelect = document.getElementById("city-select") as HTMLSelectElement;
    const targetCity = state.city ?? state.exposureLayer?.cities[0] ?? null;
    if (targetCity && targetCity !== state.city) {
      state.city = targetCity;
      citySelect.value = targetCity;
    }
    if (state.city) loadRiskForCity(state.city);
  }
}

function selectAttribute(attribute: LayerAttribute): void {
  state.attribute = attribute;
  renderLayer();
}

function selectCity(city: string | null): void {
  // "All cities" isn't meaningful for a per-city risk scenario, so keep
  // showing the current city's scenario and snap the dropdown back,
  // rather than silently doing nothing and leaving a stale "Running
  // scenario..." panel up with no data ever loading for it.
  if (state.mode === "risk" && city === null) {
    const citySelect = document.getElementById("city-select") as HTMLSelectElement | null;
    if (citySelect && state.city) citySelect.value = state.city;
    return;
  }

  state.city = city;
  setEpicenterPicking(false);
  if (state.mode === "exposure") {
    renderLayer();
    const filtered = filteredExposureData();
    if (filtered.features.length > 0) {
      map.fitBounds(computeBbox(filtered), { padding: 40, duration: 500 });
    }
  } else if (city) {
    loadRiskForCity(city);
  }
}

function showError(message: string): void {
  const controls = document.getElementById("controls");
  if (controls) {
    const error = document.createElement("p");
    error.className = "error";
    error.textContent = message;
    controls.appendChild(error);
  }
}

function applyNumericRanges(layer: Layer, data: GeoJSON.FeatureCollection): void {
  for (const attribute of layer.attributes) {
    if (attribute.kind === "sequential") {
      state.numericRange[attribute.name] = numericRangeOf(data, attribute.name);
    }
  }
}

async function bootstrap(): Promise<void> {
  setBuildingClickHandler(selectBuilding);

  const [layers, scenarioList] = await Promise.all([fetchLayers(), fetchScenarios()]);
  const layer: Layer | undefined = layers[0];
  if (!layer) throw new Error("No layers registered on the backend");
  state.exposureLayer = layer;
  state.scenarioList = scenarioList;

  // Start zoomed into one city rather than "All cities": san_jose has
  // the strongest data behind it of the three pilots, the only one
  // with a PSHA hazard curve validated against a published reference
  // curve (docs/psha_plan.md), plus 3 of 4 structural-typology classes
  // represented in its held-out ground truth.
  //
  // Fetched scoped to just that city first, so the map goes straight to
  // it instead of flashing a wide default view then jumping once the
  // full (every city) fetch resolves; the full dataset loads in the
  // background right after and replaces state.data once it lands, so
  // switching cities afterwards is still instant (filteredExposureData()
  // filtering client-side, no per-switch fetch).
  const DEFAULT_CITY = "san_jose";
  const initialCity = layer.cities.includes(DEFAULT_CITY) ? DEFAULT_CITY : null;

  const [data, legend] = await Promise.all([
    fetchLayerData(layer.id, initialCity ?? undefined),
    fetchLegend(layer.id),
  ]);
  state.data = data;
  state.legend = legend;
  applyNumericRanges(layer, data);

  const modeSelect = document.getElementById("mode-select") as HTMLSelectElement;
  const attributeSelect = document.getElementById("attribute-select") as HTMLSelectElement;
  const citySelect = document.getElementById("city-select") as HTMLSelectElement;

  modeSelect.addEventListener("change", () => selectMode(modeSelect.value as Mode));
  populateAttributeSelect(attributeSelect, layer.attributes, selectAttribute);
  populateCitySelect(citySelect, layer.cities, selectCity);

  const firstAttribute = layer.attributes[0];
  if (firstAttribute) {
    state.attribute = firstAttribute;
    attributeSelect.value = firstAttribute.name;
  }

  if (initialCity) {
    state.city = initialCity;
    citySelect.value = initialCity;
  }

  document.getElementById("building-panel-close")?.addEventListener("click", closeBuildingPanel);

  map.on("click", (event) => {
    if (!state.pickingEpicenter) return;
    pickEpicenter(event.lngLat.lat, event.lngLat.lng);
  });

  const initialData = state.city ? filteredExposureData() : data;
  map.fitBounds(computeBbox(initialData), { padding: 40, duration: 0 });
  renderLayer();

  if (initialCity) {
    fetchLayerData(layer.id)
      .then((fullData) => {
        state.data = fullData;
        applyNumericRanges(layer, fullData);
        if (state.mode === "exposure") renderLayer();
      })
      .catch((error: unknown) => {
        // Non-fatal: the initial city's own data is already loaded and
        // showing: worst case, switching to another city stays empty
        // until a page reload rather than the whole app failing.
        console.error("Background load of remaining cities' exposure data failed:", error);
      });
  }
}

map.on("load", () => {
  bootstrap().catch((error: unknown) => {
    console.error(error);
    const message = error instanceof Error ? error.message : String(error);
    showError(`Failed to load data from ${API_BASE}: ${message}. Is the backend running?`);
  });
});
