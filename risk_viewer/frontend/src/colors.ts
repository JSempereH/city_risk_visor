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
// extensive < complete), encoded as a single-hue, monotone-lightness ramp
// per the dataviz method's ordinal rule, rather than a multi-hue
// good-to-critical status scale. Checked directly: a good (green) to
// critical (red) status scale puts the two most consequential states
// (slight vs. complete) at only deltaE 4.1 under simulated deuteranopia,
// below the method's floor. A single hue avoids relying on hue
// discrimination at all, so severity still reads correctly under any type
// of color vision deficiency. "none" is a neutral surface tone rather than
// the ramp's lightest step so it reads as "nothing to show" instead of
// "mild damage".
export const DAMAGE_STATE_COLORS: Record<string, string> = {
  none: "#e5e3dd",
  slight: "#ed756e",
  moderate: "#b64340",
  extensive: "#800613",
  complete: "#520000",
};

export const DAMAGE_STATE_ORDER = ["none", "slight", "moderate", "extensive", "complete"] as const;
