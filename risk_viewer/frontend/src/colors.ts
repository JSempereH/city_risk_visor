/**
 * Categorical colors for each attribute value come from the backend's
 * `/api/layers/{id}/legend` endpoint (`app/colors.py`). This module holds
 * what the frontend computes on its own: the sequential ramp for numeric
 * attributes, the damage-state severity ramp, and hex/rgb conversion for
 * deck.gl. All ramps below are checked with the bundled `dataviz` skill's
 * `validate_palette.js` for colorblind-simulated separation.
 */

export const UNLABELED_COLOR = "#9e9d94";
export const UNLABELED_VALUE = "unlabeled";

// Glow color for a building whose structural_system_class is REAL
// recorded data (app/data_loader.py::_fill_unlabeled_from_ensemble only
// ever fills a genuine gap, never overrides a recorded one). Deliberately
// the minority gets marked, not the majority: most cities are mostly
// ML-estimated buildings, so flagging those instead reads as "the whole
// map is flagged" rather than signaling anything (see mapLayers.ts's own
// confirmed-glow layers for how this is actually drawn -- a real, if
// faked, glow, not just a stroke color, since a same-weight stroke on
// every building competed with the fill hue at this density).
export const CONFIRMED_GLOW_COLOR = "#f2fbff";

// The selected-building outline (mapLayers.ts's own getLineColor/
// getLineWidth). This app's own amber accent -- in 3D, the buildings
// layer also turns on `wireframe` (see renderLayer()), so this same
// color traces every edge of the selected building's extruded volume,
// not just a ring at its base, which is what actually made the old
// ground-level-only outline hard to see from an oblique 3D angle.
export const SELECTED_COLOR = "#e2a33f";

// Same blue hue family as the categorical palette's first slot.
const SEQUENTIAL_PASTEL_STEPS = ["#cde2fb", "#9ec5f4", "#6da7ec", "#3987e5", "#1c5cab"];

export type RgbColor = [number, number, number];

export function hexToRgb(hex: string): RgbColor {
  const clean = hex.replace("#", "");
  const value = parseInt(clean, 16);
  return [(value >> 16) & 255, (value >> 8) & 255, value & 255];
}

function lerp(a: number, b: number, t: number): number {
  return a + (b - a) * t;
}

function rampColor(steps: string[], value: number | null, min: number, max: number): RgbColor {
  if (value === null || Number.isNaN(value)) {
    return hexToRgb(UNLABELED_COLOR);
  }
  const rgbSteps = steps.map(hexToRgb);
  if (max === min) {
    return rgbSteps[rgbSteps.length - 1];
  }
  const t = Math.min(1, Math.max(0, (value - min) / (max - min)));
  const scaled = t * (rgbSteps.length - 1);
  const lowIndex = Math.floor(scaled);
  const highIndex = Math.min(rgbSteps.length - 1, lowIndex + 1);
  const frac = scaled - lowIndex;
  const [r1, g1, b1] = rgbSteps[lowIndex];
  const [r2, g2, b2] = rgbSteps[highIndex];
  return [
    Math.round(lerp(r1, r2, frac)),
    Math.round(lerp(g1, g2, frac)),
    Math.round(lerp(b1, b2, frac)),
  ];
}

export function sequentialColor(value: number | null, min: number, max: number): RgbColor {
  return rampColor(SEQUENTIAL_PASTEL_STEPS, value, min, max);
}

// This app's real "yellow": categorical slot 5 ("gold", app/colors.py),
// the color actually seen all over the map (MR/W buildings) -- not
// --amber (#e2a33f, style.css), which is a separate, more muted
// orange-leaning accent this app only ever uses for UI chrome (active
// tabs/buttons) and reads as "orange," not "yellow," next to real gold
// data. A heatmap cell fades from the panel's own background color
// (PANEL_BASE, matching --panel-solid) up to full gold at the max value,
// a plain two-color interpolation rather than an HSL sweep -- guarantees
// the highest cell is the exact, recognizable gold, with lower values
// reading as "less of it" by blending into the panel rather than drifting
// toward an unrelated hue.
const AMBER_HEATMAP_PEAK: RgbColor = [242, 212, 61]; // #f2d43d
const AMBER_HEATMAP_BASE: RgbColor = [20, 24, 29]; // --panel-solid, #14181d

export function amberSequentialColor(value: number | null, min: number, max: number): RgbColor {
  if (value === null || Number.isNaN(value)) {
    return hexToRgb(UNLABELED_COLOR);
  }
  const t = max === min ? 1 : Math.min(1, Math.max(0, (value - min) / (max - min)));
  const [r1, g1, b1] = AMBER_HEATMAP_BASE;
  const [r2, g2, b2] = AMBER_HEATMAP_PEAK;
  return [Math.round(lerp(r1, r2, t)), Math.round(lerp(g1, g2, t)), Math.round(lerp(b1, b2, t))];
}

export function sequentialLegendSteps(min: number, max: number): { value: number; color: string }[] {
  const stepCount = SEQUENTIAL_PASTEL_STEPS.length;
  return SEQUENTIAL_PASTEL_STEPS.map((color, index) => ({
    color,
    value: min + ((max - min) * index) / (stepCount - 1),
  }));
}

// Damage state is an ordinal severity scale (none < slight < moderate <
// extensive < complete). Originally a single dark-red hue (still the
// method's own default for an ordinal ramp — a good/critical multi-hue
// status scale put "slight" vs. "complete" at only deltaE 4.1 under
// simulated deuteranopia, below the floor). Replaced with a violet ->
// magenta -> coral -> peach progression sampled directly from
// github.com/RELNO/gridnberg's own slope legend (gentle -> steep), a
// perceptual multi-hue ramp in the same family as viridis/magma: hue
// shifts alongside lightness, but lightness alone still carries the
// order, so it degrades to the single-hue case under any color-vision
// deficiency instead of relying on hue. Exact stops sampled off that
// reference image's own gradient bar (not eyeballed/invented):
// `validate_palette.py "#722877,#b82d70,#da635f,#dd9d7a" --mode dark
// --surface "#0a0c0f" --ordinal` -> ALL CHECKS PASS (hue spread 28,
// under the method's 40 ceiling for "one perceptual family").
//
// Assigned darkest (violet) -> lightest (peach) as complete -> slight,
// not the other way around: "more purple = more severe" was a direct
// ask, overriding this ramp's first cut (peach = most severe, chosen
// for max contrast against the dark map/chart surfaces — see chart.ts's
// per-series glow, which still kicks in automatically here for
// "complete" since it keys off relativeLuminance(), not which state the
// color happens to be assigned to). "none" is a neutral surface tone
// rather than the ramp's own lightest step so it reads as "nothing to
// show" instead of "mild damage".
export const DAMAGE_STATE_COLORS: Record<string, string> = {
  none: "#6b6f76",
  slight: "#dd9d7a",
  moderate: "#da635f",
  extensive: "#b82d70",
  complete: "#722877",
};

export const DAMAGE_STATE_ORDER = ["none", "slight", "moderate", "extensive", "complete"] as const;

// WCAG relative luminance, used only to pick readable text for a pill/
// badge whose background is a data color (e.g. a damage-state swatch)
// rather than a fixed design token — not an accessibility contrast
// guarantee about the background color itself.
export function readableTextColor(hex: string): string {
  const [r, g, b] = hexToRgb(hex).map((c) => {
    const s = c / 255;
    return s <= 0.03928 ? s / 12.92 : ((s + 0.055) / 1.055) ** 2.4;
  });
  const luminance = 0.2126 * r + 0.7152 * g + 0.0722 * b;
  return luminance > 0.4 ? "#0b0b0b" : "#f4f4f4";
}
