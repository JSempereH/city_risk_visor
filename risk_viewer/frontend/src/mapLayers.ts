import { MapLibreMap, type StyleSpecification, type LngLatBoundsLike } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import { GeoJsonLayer, ScatterplotLayer } from "@deck.gl/layers";
import { ESTIMATED_STROKE_COLOR, hexToRgb, sequentialColor, UNLABELED_COLOR } from "./colors";
import { formatTooltip, formatRiskTooltip, renderCategoricalLegend, renderSequentialLegend } from "./ui";
import { activeData, activeLegendFor, activeNumericRange, state } from "./state";
import { renderTypologyQuality } from "./typologyQualityPanel";

// CARTO Positron: a light, near-grayscale basemap built from OSM data,
// designed for data overlays (unlike a desaturation filter forced onto
// the standard colorful OSM tiles, which reads as muddy). Free, no API
// key needed. https://github.com/CartoDB/basemap-styles
const OSM_STYLE: StyleSpecification = {
  version: 8,
  sources: {
    osm: {
      type: "raster",
      tiles: ["https://basemaps.cartocdn.com/light_all/{z}/{x}/{y}{r}.png"],
      tileSize: 256,
      attribution: "&copy; OpenStreetMap contributors &copy; CARTO",
    },
  },
  layers: [{ id: "osm", type: "raster", source: "osm" }],
};

export const map = new MapLibreMap({
  container: "map",
  style: OSM_STYLE,
  center: [-82, 13],
  zoom: 4,
});

const overlay = new MapboxOverlay({ layers: [] });
map.addControl(overlay);

// MapLibre sizes its internal <canvas> from the #map container's actual
// pixel box at construction time and doesn't re-measure it on its own
// for every layout change (window-level trackResize alone can miss a
// container resize that isn't itself a window resize, e.g. DevTools
// docking/undocking or a late web-font-driven reflow). Without this,
// the canvas can end up stuck at a stale, too-small size while #map's
// CSS box (position:absolute; inset:0) is already full-height, which
// reads as the map being cut off partway down the page.
const mapContainer = document.getElementById("map");
if (mapContainer) {
  new ResizeObserver(() => map.resize()).observe(mapContainer);
}

export function computeBbox(collection: GeoJSON.FeatureCollection): LngLatBoundsLike {
  let minX = Infinity;
  let minY = Infinity;
  let maxX = -Infinity;
  let maxY = -Infinity;

  const visit = (coords: unknown): void => {
    if (Array.isArray(coords) && typeof coords[0] === "number") {
      const [x, y] = coords as [number, number];
      if (x < minX) minX = x;
      if (x > maxX) maxX = x;
      if (y < minY) minY = y;
      if (y > maxY) maxY = y;
    } else if (Array.isArray(coords)) {
      for (const c of coords) visit(c);
    }
  };

  for (const feature of collection.features) {
    if (feature.geometry && "coordinates" in feature.geometry) {
      visit(feature.geometry.coordinates);
    }
  }
  return [
    [minX, minY],
    [maxX, maxY],
  ];
}

function isSelected(feature: GeoJSON.Feature): boolean {
  return feature.properties?.id === state.selectedBuildingId;
}

// Only meaningful while coloring by structural system: a building's
// structural_system_estimated flag says whether the classifier ensemble
// filled in a missing class, not whether e.g. its floor count is a guess.
function isEstimatedStructuralSystem(feature: GeoJSON.Feature): boolean {
  return state.attribute?.name === "structural_system_class" && feature.properties?.structural_system_estimated === true;
}

function getFillColor(feature: GeoJSON.Feature): [number, number, number, number] {
  const attribute = state.attribute;
  if (!attribute) return [...hexToRgb(UNLABELED_COLOR), 200];

  const value = feature.properties?.[attribute.name];
  const alpha = isEstimatedStructuralSystem(feature) ? 130 : 200;
  if (attribute.kind === "categorical") {
    const attributeLegend = activeLegendFor(attribute.name);
    const hex = attributeLegend[value as string] ?? UNLABELED_COLOR;
    return [...hexToRgb(hex), alpha];
  }
  const [min, max] = activeNumericRange(attribute.name);
  return [...sequentialColor(typeof value === "number" ? value : null, min, max), alpha];
}

function getLineColor(feature: GeoJSON.Feature): [number, number, number, number] {
  if (isSelected(feature)) return [11, 11, 11, 255];
  if (isEstimatedStructuralSystem(feature)) return [...hexToRgb(ESTIMATED_STROKE_COLOR), 220];
  return [40, 40, 40, 180];
}

function getLineWidth(feature: GeoJSON.Feature): number {
  if (isSelected(feature)) return 3;
  return isEstimatedStructuralSystem(feature) ? 2 : 1;
}

function epicenterLayer(): ScatterplotLayer | null {
  if (state.mode !== "risk" || !state.scenarioSummary) return null;
  const { epicenter_lat, epicenter_lon } = state.scenarioSummary.scenario;
  return new ScatterplotLayer({
    id: "epicenter",
    data: [{ position: [epicenter_lon, epicenter_lat] }],
    getPosition: (d) => d.position,
    getFillColor: [235, 104, 52, 230], // categorical slot 2 (orange), distinct from any damage-state fill
    getLineColor: [11, 11, 11, 255],
    stroked: true,
    lineWidthUnits: "pixels",
    getLineWidth: 2,
    radiusUnits: "pixels",
    getRadius: 8,
    pickable: false,
  });
}

type BuildingClickHandler = (id: string, properties: Record<string, unknown>) => void;
let onBuildingClick: BuildingClickHandler = () => {};

/** Set once during bootstrap, so renderLayer() itself stays a plain
 * zero-argument function every caller can use the same way. */
export function setBuildingClickHandler(handler: BuildingClickHandler): void {
  onBuildingClick = handler;
}

export function renderLegend(): void {
  const container = document.getElementById("legend");
  const attribute = state.attribute;
  if (!container || !attribute) return;
  if (attribute.kind === "categorical") {
    renderCategoricalLegend(container, attribute.label, activeLegendFor(attribute.name));
  } else {
    const [min, max] = activeNumericRange(attribute.name);
    renderSequentialLegend(container, attribute.label, min, max);
  }

  const qualityContainer = document.getElementById("typology-quality");
  if (qualityContainer) {
    renderTypologyQuality(qualityContainer, state.city, state.attribute?.name);
  }
}

export function renderLayer(): void {
  const geoJsonLayer = new GeoJsonLayer({
    id: "buildings",
    data: activeData(),
    filled: true,
    stroked: true,
    pickable: true,
    getFillColor,
    getLineColor,
    getLineWidth,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 1,
    updateTriggers: {
      getFillColor: [state.mode, state.attribute?.name, state.legend, state.numericRange, state.riskNumericRange],
      getLineColor: [state.selectedBuildingId],
      getLineWidth: [state.selectedBuildingId],
    },
    onClick: (info) => {
      if (state.pickingEpicenter) return;
      const id = info.object?.properties?.id;
      if (typeof id === "string") onBuildingClick(id, info.object.properties);
    },
  });
  const epicenter = epicenterLayer();
  overlay.setProps({
    layers: epicenter ? [geoJsonLayer, epicenter] : [geoJsonLayer],
    getTooltip: ({ object, layer }) => {
      if (!object || layer?.id !== "buildings") return null;
      const html = state.mode === "risk" ? formatRiskTooltip(object.properties ?? {}) : formatTooltip(object.properties ?? {});
      return { html, className: "deck-tooltip" };
    },
  });
  renderLegend();
}
