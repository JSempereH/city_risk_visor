import { MapLibreMap, type StyleSpecification, type LngLatBoundsLike } from "maplibre-gl";
import "maplibre-gl/dist/maplibre-gl.css";
import { MapboxOverlay } from "@deck.gl/mapbox";
import type { PickingInfo } from "@deck.gl/core";
import { GeoJsonLayer, IconLayer, ScatterplotLayer } from "@deck.gl/layers";
import { CONFIRMED_GLOW_COLOR, SELECTED_COLOR, hexToRgb, sequentialColor, UNLABELED_COLOR } from "./colors";
import { formatTooltip, formatRiskTooltip, renderCategoricalLegend, renderSequentialLegend } from "./ui";
import { activeData, activeLegendFor, activeNumericRange, isClampedAbove, state } from "./state";
import { renderTypologyQuality } from "./typologyQualityPanel";
import { updateTypologyMetricsAvailability } from "./typologyMetricsPanel";

function rasterStyle(tiles: string[], attribution: string): StyleSpecification {
  return {
    version: 8,
    sources: {
      basemap: { type: "raster", tiles, tileSize: 256, attribution },
    },
    layers: [{ id: "basemap", type: "raster", source: "basemap" }],
  };
}

// OpenFreeMap's hosted vector styles (free, no API key, no rate limit:
// https://openfreemap.org). Passing the style URL directly lets MapLibre
// fetch and keep the style spec up to date rather than us vendoring it.
export const BASEMAPS: Record<string, { label: string; style: string | StyleSpecification }> = {
  positron: { label: "Positron (light)", style: "https://tiles.openfreemap.org/styles/positron" },
  dark: { label: "Dark", style: "https://tiles.openfreemap.org/styles/dark" },
  fiord: { label: "Fiord", style: "https://tiles.openfreemap.org/styles/fiord" },
  esriSatellite: {
    label: "Esri Satellite",
    style: rasterStyle(
      ["https://server.arcgisonline.com/ArcGIS/rest/services/World_Imagery/MapServer/tile/{z}/{y}/{x}"],
      "&copy; Esri, Maxar, Earthstar Geographics",
    ),
  },
  googleSatellite: {
    label: "Google Satellite",
    style: rasterStyle(
      ["https://mt0.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", "https://mt1.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", "https://mt2.google.com/vt/lyrs=s&x={x}&y={y}&z={z}", "https://mt3.google.com/vt/lyrs=s&x={x}&y={y}&z={z}"],
      "&copy; Google",
    ),
  },
  googleHybrid: {
    label: "Google Hybrid",
    style: rasterStyle(
      ["https://mt0.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", "https://mt1.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", "https://mt2.google.com/vt/lyrs=y&x={x}&y={y}&z={z}", "https://mt3.google.com/vt/lyrs=y&x={x}&y={y}&z={z}"],
      "&copy; Google",
    ),
  },
};

export const DEFAULT_BASEMAP = "dark";

export const map = new MapLibreMap({
  container: "map",
  style: BASEMAPS[DEFAULT_BASEMAP].style,
  center: [-82, 13],
  zoom: 4,
  // Mirrored back to MapLibre's own default (0.8): the earlier negation
  // (-0.8) turned out to feel backwards too, so this flips rotate
  // direction back without touching pitch (pitchSpeed) or reimplementing
  // the drag handler.
  rotateSpeed: 0.8,
});

export function setBasemap(id: string): void {
  const basemap = BASEMAPS[id];
  if (basemap) map.setStyle(basemap.style);
}

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

// Mirrors the backend's own fallback for a building missing recorded
// height/floor data (data_loader.py's METRES_PER_FLOOR /
// DEFAULT_HEIGHT_FOR_POSITION_M), so an extruded building without real
// height data still gets a plausible extrusion instead of collapsing to
// zero height.
const METRES_PER_FLOOR = 3.0;
const DEFAULT_HEIGHT_M = 6.0;

// Real building heights here (mostly 1-5 floors, ~3-15m) read as nearly
// flat next to city-scale map geometry -- exaggerated so floor-count
// differences are actually visible at typical zoom, the same trick
// city-scale 3D building viewers commonly apply since true-scale
// buildings are imperceptible from above until zoomed in close. Kept
// modest (not e.g. 4x): footprints here are often narrow rowhouse-style
// lots, and a taller multiplier turned ordinary low-rise buildings into
// visually slender towers rather than blocky buildings.
const HEIGHT_EXAGGERATION = 2;

function rawHeightMetres(feature: GeoJSON.Feature): number {
  const properties = feature.properties ?? {};
  const height = typeof properties.height === "number" ? properties.height : null;
  const floors = typeof properties.n_floors === "number" ? properties.n_floors : null;
  return height ?? (floors !== null ? floors * METRES_PER_FLOOR : null) ?? DEFAULT_HEIGHT_M;
}

// Same percentile-clamp reasoning as state.ts's numericRangeOf() for the
// color legend: one very-tall outlier building must not itself set the
// visual scale, or every ordinary low-rise building nearby reads as
// equally squat by comparison. Recomputed per render (see renderLayer)
// so it's scoped to whichever city/mode is actually on screen, not a
// fixed global ceiling.
const ELEVATION_CLAMP_PERCENTILE = 95;

function elevationClampFor(data: GeoJSON.FeatureCollection): number {
  if (data.features.length === 0) return Infinity;
  const metres = data.features.map(rawHeightMetres).sort((a, b) => a - b);
  const index = Math.floor((ELEVATION_CLAMP_PERCENTILE / 100) * (metres.length - 1));
  return metres[index];
}

let elevationClamp = Infinity;

function getElevation(feature: GeoJSON.Feature): number {
  return Math.min(rawHeightMetres(feature), elevationClamp) * HEIGHT_EXAGGERATION;
}

/** Flips between the flat top-down view and a pitched view with
 * buildings extruded to their (exaggerated) real height. Tilting the
 * camera and switching the layer to extruded happen together since an
 * extruded layer viewed straight down looks the same as a flat one.
 *
 * If a building is selected, re-frames on it in the same camera move
 * rather than just changing pitch in place: fitBounds computes a
 * pitch-0 framing, so re-tilting afterward shifts what's actually
 * visible (pitching effectively "tips" the view forward, moving a
 * point that was centered toward the bottom of the screen) -- easily
 * enough to push a single small building's own highlight
 * (selectedOutlineLayers) off-screen entirely, behind the building
 * drawer or past the frame edge. Combining the
 * pitch change with a fresh fitBounds on that one building avoids ever
 * computing a framing for the wrong pitch. */
export function toggle3D(): void {
  state.is3D = !state.is3D;
  const pitch = state.is3D ? 50 : 0;
  const selected = state.selectedBuildingId ? activeData().features.find(isSelected) : null;
  if (selected) {
    map.fitBounds(computeBbox({ type: "FeatureCollection", features: [selected] }), {
      pitch,
      padding: 200,
      maxZoom: 19,
      duration: 500,
    });
  } else {
    map.easeTo({ pitch, duration: 500 });
  }
  renderLayer();
}

/** Resets bearing to north and pitch to whatever the current 2D/3D mode's
 * own default is (see toggle3D above), without touching center/zoom --
 * for getting back to a known orientation after rotating/tilting around,
 * not for re-framing the view on the data. */
export function resetOrientation(): void {
  map.easeTo({ bearing: 0, pitch: state.is3D ? 50 : 0, duration: 500 });
}

// Only meaningful while coloring by structural system: true for a
// building whose structural_system_class is a genuine per-building
// record (backend's structural_system_confirmed, see
// data_loader.py::_compute_structural_system_confirmed) -- NOT just
// "structural_system_estimated is false", which is also false for a
// city-wide fallback assumption applied where even the typology
// ensemble had no per-building prediction to fall back on (e.g.
// lomas_centinela's ~54 year-less buildings). That fallback must never
// glow like verified data; the minority worth marking is the real
// records, not everything the ensemble didn't personally touch. See
// colors.ts::CONFIRMED_GLOW_COLOR.
function isConfirmedStructuralSystem(feature: GeoJSON.Feature): boolean {
  return state.attribute?.name === "structural_system_class" && feature.properties?.structural_system_confirmed === true;
}

function getFillColor(feature: GeoJSON.Feature): [number, number, number, number] {
  const attribute = state.attribute;
  if (!attribute) return [...hexToRgb(UNLABELED_COLOR), 200];

  const value = feature.properties?.[attribute.name];
  if (attribute.kind === "categorical") {
    const attributeLegend = activeLegendFor(attribute.name);
    const hex = attributeLegend[value as string] ?? UNLABELED_COLOR;
    return [...hexToRgb(hex), 200];
  }
  const [min, max] = activeNumericRange(attribute.name);
  return [...sequentialColor(typeof value === "number" ? value : null, min, max), 200];
}

function getLineColor(feature: GeoJSON.Feature): [number, number, number, number] {
  // Selection no longer marked here -- see selectedOutlineLayers() below,
  // a dedicated overlay instead of a per-feature color/width branch on
  // this shared layer, since the selected building needs a real halo
  // (dark stroke behind the amber one) for contrast against fills as
  // close in hue as this app's own CR/MR/W, which a same-layer accessor
  // can't produce (one getLineColor per feature, no second pass under it).
  if (isConfirmedStructuralSystem(feature)) return [...hexToRgb(CONFIRMED_GLOW_COLOR), 235];
  // A light hairline, not a dark one: against the dark basemap this is
  // what keeps every footprint reading as a distinct shape, especially
  // the darkest damage-state fills that would otherwise blend into it.
  return [235, 235, 235, 90];
}

function getLineWidth(feature: GeoJSON.Feature): number {
  return isConfirmedStructuralSystem(feature) ? 1.6 : 1;
}

// The bright core stroke above reads as "special" on its own, but deck.gl
// has no built-in bloom/glow (confirmed against its PostProcessEffect
// docs: only a brightnessContrast shader ships out of the box) -- so the
// actual glow is faked the same way hand-authored neon map styles do it
// (e.g. Mapsmith's "Darkly Neon"): stack duplicate outlines under the
// real one, each wider and fainter, so they read as a soft falloff
// instead of one hard-edged ring. Only ever built for the confirmed
// minority (see isConfirmedStructuralSystem), so this stays cheap even
// on a ~2,000-building city.
function confirmedGlowLayers(): GeoJsonLayer[] {
  if (state.attribute?.name !== "structural_system_class") return [];
  const data = activeData();
  const glowData: GeoJSON.FeatureCollection = {
    ...data,
    features: data.features.filter(isConfirmedStructuralSystem),
  };
  if (glowData.features.length === 0) return [];

  const rings: [number, number][] = [
    [13, 22],
    [8, 50],
    [4, 100],
  ]; // [lineWidth px, alpha] outermost/faintest first, so later (narrower) rings paint over them
  return rings.map(
    ([lineWidth, alpha], index) =>
      new GeoJsonLayer({
        id: `confirmed-glow-${index}`,
        data: glowData,
        filled: false,
        stroked: true,
        pickable: false,
        lineWidthUnits: "pixels",
        getLineColor: [...hexToRgb(CONFIRMED_GLOW_COLOR), alpha],
        getLineWidth: lineWidth,
      }),
  );
}

// A dedicated overlay for the one selected building, not a color/width
// branch on the shared buildings layer above: 3D needs a wide dark halo
// under the amber line for contrast against a lit extruded volume (see
// the passes below), which a single getLineColor/getLineWidth on the
// shared layer can't produce (one color per feature, no second pass
// under it). `extruded`/`wireframe` on when state.is3D mirrors the main
// buildings layer exactly (same getElevation), so both passes trace
// every edge of the actual 3D volume -- top, bottom, and every vertical
// strut -- not just a footprint ring a taller neighbor, or the
// building's own bulk from an oblique angle, could hide.
//
// `parameters: {depthTest: false}` is why this is a genuinely separate
// overlay layer rather than just being drawn after the main buildings
// layer in the array: with depth testing on, this outline's geometry
// sits exactly coincident with the selected building's own solid
// extruded faces (same footprint, same getElevation), which z-fights
// with -- and in practice mostly loses to -- that opaque geometry, so
// the outline was being computed correctly but rendered invisible
// underneath the building's own surface. Disabling depth testing here
// makes this layer composite on top unconditionally, which is exactly
// what a selection indicator should do regardless of what else occupies
// that same 3D space.
function selectedOutlineLayers(): GeoJsonLayer[] {
  if (!state.selectedBuildingId) return [];
  const data = activeData();
  const selectedData: GeoJSON.FeatureCollection = {
    ...data,
    features: data.features.filter(isSelected),
  };
  if (selectedData.features.length === 0) return [];

  // 2D: amber alone -- a flat footprint outline already reads clearly
  // on its own, and a dark halo under it just showed as an unwanted
  // black border/fringe around the amber. 3D: the halo earns its keep
  // there, tracing a whole extruded volume's edges against a lit,
  // shaded surface (not a flat fill) is a harder contrast problem, and
  // it's the same duplicate-outline trick confirmedGlowLayers uses
  // above. Both widths thicker than their 2D counterparts: struts are
  // short compared to a full footprint ring, so the same weight read
  // as thinner in 3D.
  const passes: [string, number][] = state.is3D
    ? [
        ["#0b0b0b", 15],
        [SELECTED_COLOR, 9],
      ]
    : [[SELECTED_COLOR, 3]];
  return passes.map(
    ([color, lineWidth], index) =>
      new GeoJsonLayer({
        id: `selected-outline-${index}`,
        data: selectedData,
        filled: false,
        stroked: true,
        extruded: state.is3D,
        wireframe: state.is3D,
        getElevation,
        pickable: false,
        lineWidthUnits: "pixels",
        getLineColor: [...hexToRgb(color), 255],
        getLineWidth: lineWidth,
        parameters: { depthTest: false },
      }),
  );
}

/** [lon, lat] of the epicenter currently on screen, or null if there's
 * none to show (not in risk mode, or no scenario has ever loaded yet).
 * Prefers a picked-or-typed-but-not-yet-applied epicenter (see
 * state.ts::scenarioDraft) over the last *applied* one, so clicking the
 * map moves the pin immediately instead of only after the scenario
 * re-runs and a new summary comes back. Shared by the marker itself and
 * the loading-pulse rings below so they never draw at different spots. */
function epicenterPosition(): [number, number] | null {
  if (state.mode !== "risk" || !state.scenarioSummary) return null;
  const lat = state.scenarioDraft.epicenter_lat ?? state.scenarioSummary.scenario.epicenter_lat;
  const lon = state.scenarioDraft.epicenter_lon ?? state.scenarioSummary.scenario.epicenter_lon;
  return [lon, lat];
}

// Bright warning-yellow, distinct from any damage-state fill and from
// the buildings' own amber/orange accent (CONFIRMED_GLOW_COLOR) -- reads
// as a hazard marker rather than blending in with the data underneath it.
const EPICENTER_COLOR = "#ffcc00";
const EPICENTER_STROKE = "#0b0b0b";

// A thick "+" cross rendered once as an inline SVG and handed to
// IconLayer's "auto-packing" getIcon (a url + size, no separate
// iconAtlas/iconMapping build step needed) -- reads as a deliberate map
// marker rather than just another colored circle among the buildings.
const EPICENTER_ICON_SIZE = 64;
const EPICENTER_ICON_URL = `data:image/svg+xml;utf8,${encodeURIComponent(
  `<svg xmlns="http://www.w3.org/2000/svg" width="${EPICENTER_ICON_SIZE}" height="${EPICENTER_ICON_SIZE}" viewBox="0 0 64 64">` +
    `<path d="M25,5 L39,5 L39,25 L59,25 L59,39 L39,39 L39,59 L25,59 L25,39 L5,39 L5,25 L25,25 Z" ` +
    `fill="${EPICENTER_COLOR}" stroke="${EPICENTER_STROKE}" stroke-width="3" stroke-linejoin="round"/></svg>`,
)}`;

function epicenterLayer(): IconLayer | null {
  const position = epicenterPosition();
  if (!position) return null;
  return new IconLayer({
    id: "epicenter",
    data: [{ position }],
    getPosition: (d) => d.position,
    getIcon: () => ({
      url: EPICENTER_ICON_URL,
      width: EPICENTER_ICON_SIZE,
      height: EPICENTER_ICON_SIZE,
      anchorX: EPICENTER_ICON_SIZE / 2,
      anchorY: EPICENTER_ICON_SIZE / 2,
    }),
    sizeUnits: "pixels",
    getSize: 28,
    pickable: false,
  });
}

// While a scenario is computing (see scenarioController.ts's
// loadRiskForCity), a few faint rings expand outward from the epicenter
// and fade, like a seismic-wave ping -- a lightweight signal that
// something is actively running at that specific point, not just a
// generic spinner. Deliberately its own requestAnimationFrame loop
// driving only commitLayers() (rings + the already-built static layers),
// NOT a full renderLayer() every frame: renderLayer() re-derives the
// buildings layer from scratch (including elevationClampFor's sort over
// every feature), which would be wasteful work to repeat 60 times a
// second for an animation that never touches the buildings themselves.
const PULSE_RING_COUNT = 3;
const PULSE_CYCLE_MS = 1400;
const PULSE_MAX_RADIUS_PX = 42;

let pulseAnimationFrame: number | null = null;
let pulseStartTime = 0;

function pulseRingLayers(): ScatterplotLayer[] {
  if (pulseAnimationFrame === null) return [];
  const position = epicenterPosition();
  if (!position) return [];
  const elapsed = performance.now() - pulseStartTime;
  const rings: ScatterplotLayer[] = [];
  for (let i = 0; i < PULSE_RING_COUNT; i++) {
    // Each ring is offset by a third of the cycle so they read as a
    // continuous outward pulse rather than three rings moving in lockstep.
    const phase = (((elapsed + (i * PULSE_CYCLE_MS) / PULSE_RING_COUNT) % PULSE_CYCLE_MS) / PULSE_CYCLE_MS);
    rings.push(
      new ScatterplotLayer({
        id: `epicenter-pulse-${i}`,
        data: [{ position }],
        getPosition: (d) => d.position,
        filled: false,
        stroked: true,
        radiusUnits: "pixels",
        getRadius: phase * PULSE_MAX_RADIUS_PX,
        lineWidthUnits: "pixels",
        getLineWidth: 2,
        getLineColor: [...hexToRgb(EPICENTER_COLOR), Math.round((1 - phase) * 180)],
        pickable: false,
      }),
    );
  }
  return rings;
}

/** Starts the epicenter loading-pulse animation; a no-op if it's already
 * running (loadRiskForCity can be called again -- city switch, a second
 * apply -- before the first pulse has stopped). */
export function startEpicenterPulse(): void {
  if (pulseAnimationFrame !== null) return;
  pulseStartTime = performance.now();
  const tick = (): void => {
    commitLayers();
    pulseAnimationFrame = requestAnimationFrame(tick);
  };
  pulseAnimationFrame = requestAnimationFrame(tick);
}

/** Stops the pulse and commits one more frame without it, so the rings
 * disappear immediately rather than fading out on their own schedule. */
export function stopEpicenterPulse(): void {
  if (pulseAnimationFrame === null) return;
  cancelAnimationFrame(pulseAnimationFrame);
  pulseAnimationFrame = null;
  commitLayers();
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
    const clampedAbove = isClampedAbove(activeData(), attribute.name, max);
    renderSequentialLegend(container, attribute.label, min, max, clampedAbove);
  }

  const qualityContainer = document.getElementById("typology-quality");
  if (qualityContainer) {
    renderTypologyQuality(qualityContainer, state.city, state.attribute?.name);
  }
  updateTypologyMetricsAvailability(state.city, state.attribute?.name);
}

function buildingTooltip({ object, layer, x, y, viewport }: PickingInfo) {
  if (!object || layer?.id !== "buildings") return null;
  const html = state.mode === "risk" ? formatRiskTooltip(object.properties ?? {}) : formatTooltip(object.properties ?? {});
  // deck.gl anchors the tooltip's top-left exactly at the pointer via
  // `transform: translate(x,y)` (TooltipWidget.setTooltip), so it
  // always grows down-right from the cursor by default. The real-world
  // trigger for this reading as broken (not just cramped) is the
  // bottom building-panel drawer: it sits at a HIGHER z-index than
  // the tooltip's own fixed z-index:1 (TooltipWidget's defaultStyle),
  // so hovering a building whose picked point is above but close to
  // an already-open drawer produces a tooltip that grows down UNDER
  // the drawer and gets visually hidden behind it, not clipped by the
  // window edge (the map's own div extends full-height behind the
  // drawer, so a building there is still hoverable). Flips upward
  // whenever downward growth would reach the drawer's own top edge
  // (read directly from the DOM when it's open) or, with no drawer
  // open, the window's own bottom edge -- deck.gl merges a custom
  // `style` over its own inline styles by replacing keys outright,
  // not composing them (Object.assign), so the base translate(x,y)
  // has to be reproduced here too, not just the flip.
  const ESTIMATED_TOOLTIP_HEIGHT_PX = 260;
  const panelEl = document.getElementById("building-panel");
  const panelOpen = panelEl && !panelEl.classList.contains("hidden");
  const ceilingY = panelOpen ? panelEl!.getBoundingClientRect().top : (viewport?.height ?? window.innerHeight);
  const flipUp = y + ESTIMATED_TOOLTIP_HEIGHT_PX > ceilingY;
  const transform = flipUp ? `translate(${x}px, ${y}px) translateY(-100%)` : `translate(${x}px, ${y}px)`;
  return { html, className: "deck-tooltip", style: { transform } };
}

// Everything except the loading-pulse rings: rebuilt by renderLayer()
// whenever the underlying data/view actually changes. Cached here (not
// just a local var) so the pulse animation's per-frame commitLayers()
// can re-send it unchanged every tick, without renderLayer()'s own
// per-render work (notably elevationClampFor's sort over every feature).
let staticLayers: (GeoJsonLayer | IconLayer)[] = [];

function commitLayers(): void {
  overlay.setProps({
    // Glow/buildings/marker first (static, painted under), the pulse
    // rings last so they're always on top of the marker they surround.
    layers: [...staticLayers, ...pulseRingLayers()],
    getTooltip: buildingTooltip,
  });
}

export function renderLayer(): void {
  const data = activeData();
  // Recomputed every render (cheap: one pass over the current city's
  // buildings), not just on city switch, so it also stays right if
  // renderLayer() is ever called for a reason other than a city change.
  elevationClamp = elevationClampFor(data);
  const geoJsonLayer = new GeoJsonLayer({
    id: "buildings",
    data,
    filled: true,
    stroked: true,
    pickable: true,
    extruded: state.is3D,
    getElevation,
    getFillColor,
    getLineColor,
    getLineWidth,
    lineWidthUnits: "pixels",
    lineWidthMinPixels: 1,
    updateTriggers: {
      getFillColor: [state.mode, state.attribute?.name, state.legend, state.numericRange, state.riskNumericRange],
      getLineColor: [state.attribute?.name],
      getLineWidth: [state.attribute?.name],
      getElevation: [state.mode, state.city],
    },
    onClick: (info) => {
      if (state.pickingEpicenter) return;
      const id = info.object?.properties?.id;
      if (typeof id === "string") onBuildingClick(id, info.object.properties);
    },
  });
  const glow = confirmedGlowLayers();
  const selectedOutline = selectedOutlineLayers();
  const epicenter = epicenterLayer();
  // Confirmed-glow under the buildings (see its own comment), the
  // selected-building outline on top of them, epicenter marker last
  // (always on top of everything).
  staticLayers = [...glow, geoJsonLayer, ...selectedOutline, ...(epicenter ? [epicenter] : [])];
  commitLayers();
  renderLegend();
}
