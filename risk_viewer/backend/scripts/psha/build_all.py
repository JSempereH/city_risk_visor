"""One-shot PSHA + disaggregation pipeline: fetch each city's published
source model, run its classical hazard calculation, then its
disaggregation, writing all of app/data/psha/*.csv from scratch. See
README.md for what each step does and why.

Runs cities SEQUENTIALLY, not concurrently: OpenQuake's classical
calculator for these regional models is memory-heavy (hundreds of MB to a
few GB while reading rupture data), and running two at once on a modest
machine can exhaust RAM: this repo's own build history includes a real
OOM crash from doing that. Budget roughly 15-60 min per city depending on
model size (San Jose/Santo Domingo faster, Guatemala's regional mosaic
slower) plus a few minutes of disaggregation per city.

Usage (from backend/):
    uv run python scripts/psha/build_all.py                 # all 3 cities
    uv run python scripts/psha/build_all.py guatemala        # one city
"""

from __future__ import annotations

import subprocess
import sys

from lib import CITIES

SCRIPT_DIR_RELATIVE = "scripts/psha"


def run(*args: str) -> None:
    subprocess.run([sys.executable, *args], check=True, cwd=".")


def main() -> None:
    cities = sys.argv[1:] or list(CITIES)
    for city in cities:
        print(f"\n=== {city}: fetching source model ===")
        run(f"{SCRIPT_DIR_RELATIVE}/fetch_sources.py", city)
        print(f"\n=== {city}: classical PSHA ===")
        run(f"{SCRIPT_DIR_RELATIVE}/run_classical.py", city)
        print(f"\n=== {city}: disaggregation ===")
        run(f"{SCRIPT_DIR_RELATIVE}/run_disagg.py", city)
    print("\nDone. Review the diffs under app/data/psha/ before committing.")


if __name__ == "__main__":
    main()
