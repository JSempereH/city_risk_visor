import type { Layer, LayerAttribute } from "./api";
import { fetchLayers, fetchLayerData, fetchLegend, fetchScenarios } from "./api";
import { initSegmentedControl, populateAttributeSelect, populateCitySelect, type DropdownHandle } from "./ui";
import { initBuildingPanelControls, selectBuilding } from "./buildingController";
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

// Set once each in bootstrap()/applyAttributeOptionsForMode() (the
// attribute dropdown is rebuilt with a fresh handle every mode switch,
// since its option list changes); selectMode()/selectCity() below reach
// back into these to move the dropdown's displayed value without the
// user having opened it themselves.
let attributeDropdown: DropdownHandle | null = null;
let cityDropdown: DropdownHandle | null = null;

function applyAttributeOptionsForMode(): void {
  const attributeContainer = document.getElementById("attribute-select") as HTMLElement;
  const attributes = activeAttributes();
  attributeDropdown = populateAttributeSelect(attributeContainer, attributes, selectAttribute);
  const first = attributes[0];
  if (first) {
    state.attribute = first;
    attributeDropdown.setValue(first.name);
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
    const targetCity = state.city ?? state.exposureLayer?.cities[0] ?? null;
    if (targetCity && targetCity !== state.city) {
      state.city = targetCity;
      cityDropdown?.setValue(targetCity);
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
    if (state.city) cityDropdown?.setValue(state.city);
    return;
  }

  state.city = city;
  setEpicenterPicking(false);
  if (state.mode === "exposure") {
    if (state.exposureLayer) applyNumericRanges(state.exposureLayer);
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
  const controls = document.getElementById("controls-body");
  if (controls) {
    const error = document.createElement("p");
    error.className = "error";
    error.textContent = message;
    controls.appendChild(error);
  }
}

// Always recomputed from filteredExposureData() (the currently selected
// city only, or every city if none is selected), never from a raw
// unfiltered dataset: a shared cross-city domain is exactly what let a
// taller city's buildings crush a shorter city's (lomas_centinela, almost
// entirely 1-3 floors) into one indistinguishable color. Must be called
// again on every city switch, not just once at bootstrap, see selectCity().
function applyNumericRanges(layer: Layer): void {
  const data = filteredExposureData();
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
  // state.city must be set before applyNumericRanges() so its
  // filteredExposureData() call inside actually scopes to this city,
  // not the (not-yet-set) "no city selected" case.
  if (initialCity) state.city = initialCity;
  applyNumericRanges(layer);

  initSegmentedControl(document.getElementById("mode-select") as HTMLElement, (value) => selectMode(value as Mode));
  attributeDropdown = populateAttributeSelect(
    document.getElementById("attribute-select") as HTMLElement,
    layer.attributes,
    selectAttribute,
  );
  cityDropdown = populateCitySelect(document.getElementById("city-select") as HTMLElement, layer.cities, selectCity);

  const firstAttribute = layer.attributes[0];
  if (firstAttribute) {
    state.attribute = firstAttribute;
    attributeDropdown.setValue(firstAttribute.name);
  }

  if (initialCity) {
    cityDropdown.setValue(initialCity);
  }

  initBuildingPanelControls();

  document.getElementById("controls-toggle")?.addEventListener("click", () => {
    document.getElementById("controls")?.classList.toggle("collapsed");
  });

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
        // Recomputed for whichever city is selected right now (still
        // scoped to it via filteredExposureData() inside), not the full,
        // all-cities dataset that just arrived: fullData is only needed
        // so *switching* to another city later has its data ready
        // client-side, not to widen the domain of the city on screen now.
        applyNumericRanges(layer);
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
