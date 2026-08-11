"""Color constants for the `/legend` endpoint.

Mirrors `frontend/src/colors.ts`. Duplicated here as plain data (not
imported) since the frontend and backend are separate toolchains.

Four hues from the same reference categorical family used across
`ml_structural_system/ml_structural_system/viz.py` (blue, orange, aqua,
violet), reduced from that module's full eight-hue set to the four that
pass pairwise colorblind-simulated separation (Machado, Oliveira & Fernandes,
2009) when any two can sit side by side, which is how they are used here
(building polygons of different categories are adjacent on the map, unlike
a bar chart where only neighbors in a fixed order touch). Checked with
this project's `validate_palette.js` (bundled `dataviz` skill) in
`--pairs all` mode. Every categorical attribute this app renders today
(structural system, code quality, roof material) has at most four values,
so four hues are enough. A new city that introduces a 5th value for one
of these (e.g. a finer structural-typology taxonomy) folds any values past
the 4th into OTHER_COLOR rather than silently repeating a hue, per the
same dataviz-skill rule ("a 9th series is never a generated hue, it
folds into 'Other'"), and logs a warning so this becomes a fold-in-more-
hues decision instead of a silent, misleading map legend.
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

CATEGORICAL_PALETTE = [
    "#2a78d6",  # slot 1 - blue
    "#eb6834",  # slot 2 - orange
    "#1baf7a",  # slot 3 - aqua
    "#4a3aa7",  # slot 4 - violet
]

UNLABELED_COLOR = "#9e9d94"
OTHER_COLOR = "#c9c7ba"


def categorical_legend(values: list[str], unlabeled_value: str | None = None) -> dict[str, str]:
    legend: dict[str, str] = {}
    palette_values = [v for v in values if v != unlabeled_value]
    overflow = palette_values[len(CATEGORICAL_PALETTE) :]
    if overflow:
        logger.warning(
            "categorical_legend: %d value(s) beyond the %d-hue palette folded into OTHER_COLOR: %s",
            len(overflow),
            len(CATEGORICAL_PALETTE),
            overflow,
        )
    for index, value in enumerate(palette_values):
        legend[value] = CATEGORICAL_PALETTE[index] if index < len(CATEGORICAL_PALETTE) else OTHER_COLOR
    if unlabeled_value is not None and unlabeled_value in values:
        legend[unlabeled_value] = UNLABELED_COLOR
    return legend
