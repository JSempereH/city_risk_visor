#!/usr/bin/env python3
"""Bakes the 12 (city, scenario) combinations reachable through the UI's
normal "Hazard model" controls (each city's deterministic default plus
its 3 PSHA return periods) into app/data/precomputed/*.json, so a
deployed instance serves them instantly instead of paying their 15-90s
compute cost on first request (see app/precomputed.py, which reads these
files back). Meant to run as a Docker build step, not part of local dev.

Usage (from backend/): uv run python scripts/precompute.py
"""

from __future__ import annotations

import json

from app.hazard import psha
from app.hazard.scenario import PROBABILISTIC_RETURN_PERIODS_YEARS, SCENARIOS, probabilistic_scenario
from app.precomputed import PRECOMPUTED_DIR, scenario_key
from app.risk.api import scenario_summary_to_json, scenario_to_feature_collection
from app.risk.service import run_scenario


def main() -> None:
    PRECOMPUTED_DIR.mkdir(parents=True, exist_ok=True)

    combos = []
    for city, default_scenario in SCENARIOS.items():
        combos.append((scenario_key(city, None), default_scenario))
        # Only cities with an actual precomputed PSHA curve (see
        # psha.PSHA_SUPPORTED_CITIES) support probabilistic scenarios --
        # e.g. la_guaira doesn't have one yet, only its deterministic
        # default above.
        if city not in psha.PSHA_SUPPORTED_CITIES:
            continue
        for years in PROBABILISTIC_RETURN_PERIODS_YEARS:
            combos.append((scenario_key(city, years), probabilistic_scenario(city, years)))

    for key, scenario in combos:
        print(f"precomputing {key}...", flush=True)
        summary = run_scenario(scenario)
        (PRECOMPUTED_DIR / f"{key}__summary.json").write_text(
            json.dumps(scenario_summary_to_json(summary))
        )
        (PRECOMPUTED_DIR / f"{key}__risk.json").write_text(
            json.dumps(scenario_to_feature_collection(summary))
        )

    print(f"Precomputed {len(combos)} scenarios into {PRECOMPUTED_DIR}")


if __name__ == "__main__":
    main()
