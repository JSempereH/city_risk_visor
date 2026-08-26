from app.colors import (
    CATEGORICAL_PALETTE,
    OTHER_COLOR,
    STRUCTURAL_SYSTEM_PALETTE,
    UNLABELED_COLOR,
    categorical_legend,
)


def test_categorical_legend_assigns_fixed_hues_in_order():
    legend = categorical_legend(["ADO", "CR", "M", "W"])
    assert legend == {
        "ADO": CATEGORICAL_PALETTE[0],
        "CR": CATEGORICAL_PALETTE[1],
        "M": CATEGORICAL_PALETTE[2],
        "W": CATEGORICAL_PALETTE[3],
    }


def test_categorical_legend_folds_overflow_into_other_color():
    # A 5th category (e.g. a new city's finer structural taxonomy) must
    # not silently reuse one of the 4 palette hues.
    values = ["ADO", "CR", "M", "W", "S"]
    legend = categorical_legend(values)
    assert legend["S"] == OTHER_COLOR
    assert legend["S"] not in CATEGORICAL_PALETTE
    # The first 4 are unaffected by the overflow.
    assert legend["ADO"] == CATEGORICAL_PALETTE[0]
    assert legend["W"] == CATEGORICAL_PALETTE[3]


def test_categorical_legend_unlabeled_gets_its_own_color():
    legend = categorical_legend(["ADO", "unlabeled"], unlabeled_value="unlabeled")
    assert legend["unlabeled"] == UNLABELED_COLOR
    assert legend["unlabeled"] not in CATEGORICAL_PALETTE


def test_structural_system_palette_covers_all_masonry_subclasses():
    # Guatemala alone has 6 real structural_system_class values
    # (ADO/CR/M/MCF/MR/MUR); the whole point of the 7-hue palette (see
    # colors.py's own docstring) is that none of these legitimate,
    # user-requested distinctions silently folds into OTHER_COLOR.
    values = ["ADO", "CR", "M", "MCF", "MR", "MUR", "W"]
    legend = categorical_legend(values, palette=STRUCTURAL_SYSTEM_PALETTE)
    assert len(set(legend.values())) == 7
    assert OTHER_COLOR not in legend.values()
