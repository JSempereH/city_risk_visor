"""Runs the disaggregation calculation for one city, reusing its already-
completed classical PSHA calc (found automatically by description, see
lib.CLASSICAL_DESCRIPTIONS) so it doesn't re-integrate the source model
from scratch. Writes app/data/psha/{city}_disagg.csv. See
docs/disaggregation_plan.md for the method and the job.ini gotchas this
script already encodes (IMT list must match the reused precalc's own;
mag/distance/coordinate bin widths and num_epsilon_bins are all required
together).

Usage (from backend/): uv run python scripts/psha/run_disagg.py <city>
"""

from __future__ import annotations

import configparser
import os
import sys
from pathlib import Path

from lib import CLASSICAL_DESCRIPTIONS, DATA_DIR, latest_calc_id, raw_dir, write_disagg_csv

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))  # backend/, for `app`

MAG_BIN_WIDTH = 0.5
DISTANCE_BIN_WIDTH = 20.0
COORDINATE_BIN_WIDTH = 1.0
NUM_EPSILON_BINS = 1  # this implementation doesn't disaggregate by epsilon


def _reused_imtls_str(calc_id: int) -> str:
    """The reused classical calc's own IMT/level grid, expanded to plain
    floats. Read from its datastore (post-parsing), not re-serialised
    from the job.ini's own text: that text can use the `logscale(...)`
    shorthand, which doesn't survive being read back out with
    configparser and re-embedded in a second job.ini (confirmed by
    running this, not just reading the openquake source)."""
    from openquake.commonlib import datastore

    imtls = dict(datastore.read(calc_id)["oqparam"].imtls)
    return "{" + ", ".join(f'"{k}": {[float(x) for x in v]}' for k, v in imtls.items()) + "}"


def _target_poes(city: str) -> tuple[list[float], tuple[int, ...]]:
    from app.hazard import psha
    from app.hazard.scenario import PROBABILISTIC_RETURN_PERIODS_YEARS

    years = PROBABILISTIC_RETURN_PERIODS_YEARS
    investigation_time = psha.INVESTIGATION_TIME_YEARS_BY_CITY[city]
    return [psha.return_period_to_target_poe(y, investigation_time) for y in years], years


def main(city: str) -> None:
    calc_id = latest_calc_id(CLASSICAL_DESCRIPTIONS[city])
    poes, return_periods = _target_poes(city)

    # The reused precalc's own IMT list must be reproduced exactly (see
    # module docstring), read from the classical calc's own datastore,
    # not its job.ini's text (see _reused_imtls_str).
    imtls_line = _reused_imtls_str(calc_id)
    classical_ini = configparser.ConfigParser()
    classical_ini.read(raw_dir(city) / "job_hazard.ini")
    sites_csv = classical_ini["geometry"]["sites_csv"]

    job_disagg = raw_dir(city) / "job_disagg.ini"
    job_disagg.write_text(
        "[general]\n"
        f"description = Disaggregation for {city}, PGA at {len(return_periods)} return periods\n"
        "calculation_mode = disaggregation\n\n"
        # Site info isn't inherited from the reused classical calc, even
        # via hazard_calculation_id, and must be repeated here or oqparam
        # validation fails ("infer the geometry only if exactly one of
        # sites, sites_csv, ... is set").
        "[geometry]\n"
        f"sites_csv = {sites_csv}\n\n"
        "[calculation]\n"
        f"intensity_measure_types_and_levels = {imtls_line}\n"
        f"poes_disagg = {' '.join(str(p) for p in poes)}\n"
        f"mag_bin_width = {MAG_BIN_WIDTH}\n"
        f"distance_bin_width = {DISTANCE_BIN_WIDTH}\n"
        f"coordinate_bin_width = {COORDINATE_BIN_WIDTH}\n"
        f"num_epsilon_bins = {NUM_EPSILON_BINS}\n"
    )

    cwd = os.getcwd()
    os.chdir(raw_dir(city))
    try:
        from openquake.calculators import base

        calc = base.run_calc("job_disagg.ini", hazard_calculation_id=calc_id)
    finally:
        os.chdir(cwd)

    disagg_calc_id = calc.datastore.calc_id
    print(f"{city}: disaggregation complete, calc_id={disagg_calc_id} (reused classical calc_id={calc_id})")
    write_disagg_csv(disagg_calc_id, return_periods, DATA_DIR / f"{city}_disagg.csv")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(__file__).name} <san_jose|guatemala|santo_domingo>")
    main(sys.argv[1])
