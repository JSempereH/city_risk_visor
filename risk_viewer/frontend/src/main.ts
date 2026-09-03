import type { Layer, LayerAttribute } from "./api";
import { fetchLayers, fetchLayerData, fetchLegend, fetchScenarios } from "./api";
import { createDropdown, initSegmentedControl, populateAttributeSelect, populateCitySelect, type DropdownHandle } from "./ui";
import { initBuildingPanelControls, selectBuilding } from "./buildingController";
import {
  BASEMAPS,
  DEFAULT_BASEMAP,
  computeBbox,
  map,
  renderLayer,
  resetOrientation,
  setBasemap,
  setBuildingClickHandler,
  toggle3D,
} from "./mapLayers";
import { initSettingsPanel } from "./settingsPanel";
import { initTypologyMetricsPanel } from "./typologyMetricsPanel";
import {
  hideScenarioPanelForExposureMode,
  loadRiskForCity,
  pickEpicenter,
  setEpicenterPicking,
} from "./scenarioController";
import { activeAttributes, categoricalDomainOf, filteredExposureData, numericRangeOf, state, type Mode } from "./state";
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
    hint?.classList.add("hidden");
    hideScenarioPanelForExposureMode();
    setEpicenterPicking(false);
    applyAttributeOptionsForMode();
    renderLayer();
  } else {
    if (subtitle) subtitle.textContent = "Seismic risk scenario";
    if (hint) hint.textContent = "Adjustable scenario per city, see the panel above for sources and controls.";
    hint?.classList.remove("hidden");
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

// Re-fetches the exposure layer's full (all-cities) feature collection
// and re-renders -- the same "fresh backend data replaces state.data"
// step bootstrap() already does once for the background full-dataset
// load (see below), reused here so applying/clearing a typology prior
// (settingsPanel.ts) can make the map reflect it without a page reload.
// A no-op if the exposure layer hasn't loaded yet (shouldn't happen once
// the settings panel is even openable, kept as a guard).
export async function refreshExposureData(): Promise<void> {
  const layer = state.exposureLayer;
  if (!layer) return;
  const fullData = await fetchLayerData(layer.id);
  state.data = fullData;
  applyNumericRanges(layer);
  if (state.mode === "exposure") renderLayer();
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
    } else if (attribute.kind === "categorical") {
      state.categoricalDomain[attribute.name] = categoricalDomainOf(data, attribute.name);
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
  //
  // A `?city=` in the URL (see buildingController.ts's syncSelectionToUrl,
  // which writes this same param on every building selection) overrides
  // the default -- the whole point of a shareable building link is
  // landing on the right city, not always san_jose.
  const DEFAULT_CITY = "san_jose";
  const urlParams = new URLSearchParams(window.location.search);
  const urlCity = urlParams.get("city");
  const requestedCity = urlCity && layer.cities.includes(urlCity) ? urlCity : DEFAULT_CITY;
  const initialCity = layer.cities.includes(requestedCity) ? requestedCity : null;

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
  createDropdown(
    document.getElementById("basemap-select") as HTMLElement,
    Object.entries(BASEMAPS).map(([value, { label }]) => ({ value, label })),
    setBasemap,
  ).setValue(DEFAULT_BASEMAP);

  const firstAttribute = layer.attributes[0];
  if (firstAttribute) {
    state.attribute = firstAttribute;
    attributeDropdown.setValue(firstAttribute.name);
  }

  if (initialCity) {
    cityDropdown.setValue(initialCity);
  }

  initBuildingPanelControls();
  initSettingsPanel(refreshExposureData);
  initTypologyMetricsPanel();

  document.getElementById("controls-toggle")?.addEventListener("click", () => {
    document.getElementById("controls")?.classList.toggle("collapsed");
  });

  const view3DToggle = document.getElementById("view-3d-toggle");
  view3DToggle?.addEventListener("click", () => {
    toggle3D();
    view3DToggle.classList.toggle("active", state.is3D);
  });

  document.getElementById("reorient-toggle")?.addEventListener("click", () => {
    resetOrientation();
  });

  map.on("click", (event) => {
    if (!state.pickingEpicenter) return;
    pickEpicenter(event.lngLat.lat, event.lngLat.lng);
  });

  const initialData = state.city ? filteredExposureData() : data;
  map.fitBounds(computeBbox(initialData), { padding: 40, duration: 0 });
  renderLayer();

  // `?building=` deep link (see buildingController.ts's syncSelectionToUrl):
  // ids aren't unique across cities, only within one, so this only ever
  // searches the just-loaded initialCity's own data, matching the
  // `?city=` param resolved above -- a mismatched pair (a building id
  // that doesn't belong to that city) just finds nothing and opens
  // nothing, rather than guessing.
  const urlBuildingId = urlParams.get("building");
  if (urlBuildingId) {
    const feature = data.features.find((f) => f.properties?.id === urlBuildingId);
    if (feature?.properties) {
      selectBuilding(urlBuildingId, feature.properties);
      // Without this, the map above stays framed on the whole city (the
      // fitBounds just above) and the selected building's own highlight
      // (mapLayers.ts's selectedOutlineLayers) could be anywhere in that
      // extent, effectively invisible until the visitor manually finds
      // and zooms into it themselves -- defeating the point of a link
      // meant to show one specific building. maxZoom keeps a single tiny
      // footprint's own bbox from zooming in past street level.
      map.fitBounds(computeBbox({ type: "FeatureCollection", features: [feature] }), {
        padding: 200,
        maxZoom: 19,
        duration: 0,
      });
    }
  }

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
