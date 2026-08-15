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

// Outline for a building whose structural_system_class came from the
// typology classifier's own prediction rather than recorded data (see
// app/data_loader.py::_fill_unlabeled_from_ensemble). A secondary
// encoding (stroke, not fill) so the fill color keeps meaning "this
// class" regardless of confidence, and estimated buildings stay visually
// distinct from confirmed ones without a whole extra hue.
export const ESTIMATED_STROKE_COLOR = "#b8860b";

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

export function sequentialColor(value: number | null, min: number, max: number): RgbColor {
  if (value === null || Number.isNaN(value)) {
    return hexToRgb(UNLABELED_COLOR);
  }
  const steps = SEQUENTIAL_PASTEL_STEPS.map(hexToRgb);
  if (max === min) {
    return steps[steps.length - 1];
  }
  const t = Math.min(1, Math.max(0, (value - min) / (max - min)));
  const scaled = t * (steps.length - 1);
  const lowIndex = Math.floor(scaled);
  const highIndex = Math.min(steps.length - 1, lowIndex + 1);
  const frac = scaled - lowIndex;
  const [r1, g1, b1] = steps[lowIndex];
  const [r2, g2, b2] = steps[highIndex];
  return [
    Math.round(lerp(r1, r2, frac)),
    Math.round(lerp(g1, g2, frac)),
    Math.round(lerp(b1, b2, frac)),
  ];
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
// order (monotone light->dark, checked below), so it degrades to the
// single-hue case under any color-vision deficiency instead of relying
// on hue. Exact stops sampled off that reference image's own gradient
// bar (not eyeballed/invented), then nudged one step lighter at the
// dark end to clear this app's contrast floor:
// `validate_palette.py "#722877,#b82d70,#da635f,#dd9d7a" --mode dark
// --surface "#0a0c0f" --ordinal` -> ALL CHECKS PASS (hue spread 28,
// under the method's 40 ceiling for "one perceptual family").
// "none" is a neutral surface tone rather than the ramp's own lightest
// step so it reads as "nothing to show" instead of "mild damage".
export const DAMAGE_STATE_COLORS: Record<string, string> = {
  none: "#6b6f76",
  slight: "#722877",
  moderate: "#b82d70",
  extensive: "#da635f",
  complete: "#dd9d7a",
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
