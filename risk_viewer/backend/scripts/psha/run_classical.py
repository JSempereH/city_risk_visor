"""Runs the classical PSHA calculation for one city (its full published
logic tree, or the documented CAM-restricted subset for Guatemala, see
README.md) and writes app/data/psha/{city}.csv.

Assumes fetch_sources.py has already populated scripts/psha/_raw/{city}/.

Usage (from backend/): uv run python scripts/psha/run_classical.py <city>
"""

from __future__ import annotations

import os
import sys
from pathlib import Path

from lib import DATA_DIR, config_dir, overlay_configs, raw_dir, write_hazard_curve_csv


def main(city: str) -> None:
    if not (config_dir(city) / "job_hazard.ini").exists():
        raise SystemExit(f"No configs/{city}/job_hazard.ini, unknown city?")
    if not raw_dir(city).exists():
        raise SystemExit(f"{raw_dir(city)} missing, run fetch_sources.py {city} first")

    overlay_configs(city)
    cwd = os.getcwd()
    os.chdir(raw_dir(city))
    try:
        from openquake.calculators import base

        calc = base.run_calc("job_hazard.ini")
    finally:
        os.chdir(cwd)

    calc_id = calc.datastore.calc_id
    print(f"{city}: classical calc complete, calc_id={calc_id}")
    write_hazard_curve_csv(calc_id, DATA_DIR / f"{city}.csv")


if __name__ == "__main__":
    if len(sys.argv) != 2:
        raise SystemExit(f"usage: {Path(__file__).name} <san_jose|guatemala|santo_domingo>")
    main(sys.argv[1])
