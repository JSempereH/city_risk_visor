"""Color constants for the `/legend` endpoint.

Mirrors `frontend/src/colors.ts`. Duplicated here as plain data (not
imported) since the frontend and backend are separate toolchains.

Two separate 4-hue palettes, not one reused everywhere: structural
system and roof material used to share CATEGORICAL_PALETTE, which made
"blue" mean a different thing depending on which attribute was active
when coloring the map. STRUCTURAL_SYSTEM_PALETTE now belongs only to
`structural_system_class`; CATEGORICAL_PALETTE remains the default for
every other categorical attribute (roof material, code quality). Each
was validated independently (not merged into one bigger set) since
finding 8 mutually all-pairs-safe hues at once wasn't possible: yellow,
green and red collide with each other and with orange under simulated
color-vision deficiency (see the dataviz skill's own reference palette,
which caps blue/orange/aqua as the only trio proven all-pairs-safe in
both modes). Checked with this project's `validate_palette.py` (bundled
`dataviz` skill), `--pairs all` mode (any two adjacent, not just
neighbors in a fixed order, since building polygons of any two
categories can sit next to each other on the map) against this app's
dark surface:
`validate_palette.py "#3987e5,#d95926,#199e70,#e055c0" --mode dark
--surface "#0a0c0f" --pairs all`.

STRUCTURAL_SYSTEM_PALETTE takes its hue family from
github.com/RELNO/gridnberg's route-comparison colors (cyan/orange/
magenta on a dark map) plus a violet 4th slot, kept close to
gridnberg's own bright, glossy values rather than stepped down to this
skill's usual L 0.48-0.67 band: a first pass that stayed inside that
band read as muted rather than the vivid look asked for. The lightness
check FAILs as a result (an intentional, informed override of that one
advisory check, not an oversight) — CVD separation, the normal-vision
floor, and contrast, the checks that actually gate legibility, all pass
clean:
`validate_palette.py "#22c3f0,#ff8a5c,#c93a95,#8f7ff5" --mode dark
--surface "#0a0c0f" --pairs all`.

Every categorical attribute this app renders today except one has at
most four values, so four hues would be enough for it. structural_system
_class is the exception: once MUR/MCF/MR were split out of the generic
"M" bucket (see data_loader.py's STRUCTURAL_SYSTEM_REPLACEMENTS),
Guatemala alone has 6 real values (ADO/CR/M/MCF/MR/MUR). Rather than
silently folding 2 legitimate, user-requested distinctions into a shared
OTHER_COLOR, STRUCTURAL_SYSTEM_PALETTE was extended from 4 to 7 hues
(keeping the original 4 in their original slots, so no existing city's
colors shift). 7 mutually CVD-safe hues isn't achievable (this skill's
own reference notes blue/orange/aqua as the only trio proven safe in
both modes); the 3 new hues (gold, green, rust) land in the tool's
documented "6-8 floor band", legal only with secondary encoding — this
app's legend already pairs every swatch with a text label
(ui.ts::renderCategoricalLegend), so that condition is met. Checked with
`validate_palette.py "#22c3f0,#ff8a5c,#c93a95,#8f7ff5,#f2d43d,#4fd17a,
#b5651d" --mode dark --surface "#0a0c0f" --pairs all`: passes chroma
floor, normal-vision floor and surface contrast; fails the lightness
band (same intentional override as the original 4, see below) and CVD
separation (the floor-band tradeoff just described).

Every other categorical attribute this app renders (code quality, roof
material) stays on CATEGORICAL_PALETTE's 4 hues. A new city that
introduces a 5th value for one of those folds any values past the 4th
into OTHER_COLOR rather than silently repeating a hue, per the same
dataviz-skill rule ("a 9th series is never a generated hue, it folds
into 'Other'"), and logs a warning so this becomes a fold-in-more-hues
decision instead of a silent, misleading map legend.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CATEGORICAL_PALETTE = [
    "#3987e5",  # slot 1 - blue
    "#d95926",  # slot 2 - orange
    "#199e70",  # slot 3 - aqua
    "#e055c0",  # slot 4 - magenta
]

# structural_system_class only (see module docstring) — deliberately its
# own hue set, not CATEGORICAL_PALETTE, so the two attributes never look
# like they share a legend.
STRUCTURAL_SYSTEM_PALETTE = [
    "#22c3f0",  # slot 1 - cyan (gridnberg "distance")
    "#ff8a5c",  # slot 2 - orange (gridnberg "accessible")
    "#c93a95",  # slot 3 - magenta (gridnberg "comfort")
    "#8f7ff5",  # slot 4 - violet
    "#f2d43d",  # slot 5 - gold
    "#4fd17a",  # slot 6 - green
    "#b5651d",  # slot 7 - rust
]

UNLABELED_COLOR = "#9e9d94"
OTHER_COLOR = "#c9c7ba"


def categorical_legend(
    values: list[str],
    unlabeled_value: str | None = None,
    palette: list[str] = CATEGORICAL_PALETTE,
) -> dict[str, str]:
    legend: dict[str, str] = {}
    palette_values = [v for v in values if v != unlabeled_value]
    overflow = palette_values[len(palette) :]
    if overflow:
        logger.warning(
            "categorical_legend: %d value(s) beyond the %d-hue palette folded into OTHER_COLOR: %s",
            len(overflow),
            len(palette),
            overflow,
        )
    for index, value in enumerate(palette_values):
        legend[value] = palette[index] if index < len(palette) else OTHER_COLOR
    if unlabeled_value is not None and unlabeled_value in values:
        legend[unlabeled_value] = UNLABELED_COLOR
    return legend
