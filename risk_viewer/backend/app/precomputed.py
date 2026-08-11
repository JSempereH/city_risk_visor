"""Loads scenario results precomputed at Docker build time (see
scripts/precompute.py) for the fixed menu of (city, scenario)
combinations the UI's normal controls can reach: each city's
deterministic default plus its 3 PSHA return periods, 12 total. Serving
these from a static in-memory dict means a freshly (re)started container
answers them instantly, without recomputing the underlying 15-90s
hazard -> vulnerability -> damage -> casualty chain (app/risk/service.py).

Falls back to returning None (a cache miss) if the precomputed files
aren't present, e.g. in local dev, where nothing runs scripts/
precompute.py and every scenario is instead computed live via
run_scenario_coalesced(), same as before this module existed. The
Custom Scenario path (arbitrary magnitude/depth/epicenter) is never
precomputable, since its parameter space isn't enumerable, and always
goes through that live path regardless.
"""

from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path
from typing import Any, Optional

PRECOMPUTED_DIR = Path(__file__).resolve().parent / "data" / "precomputed"


def scenario_key(city: str, return_period_years: int | None) -> str:
    return f"{city}__{return_period_years}yr" if return_period_years is not None else f"{city}__deterministic"


@lru_cache(maxsize=2)
def _load_bytes(kind: str) -> dict[str, bytes]:
    """kind is "summary" or "risk". Loaded once per process lifetime --
    these files are only ever written at build time, never at runtime.
    Kept as raw JSON bytes (not parsed dicts) so a hit can be returned as
    a Response directly, without FastAPI's jsonable_encoder + json.dumps
    re-serializing an already-JSON-safe result on every request (the risk
    endpoint's payload is 0.7-2.5MB per city; re-encoding it added ~1s per
    request even though the value never changes for the process lifetime)."""
    result: dict[str, bytes] = {}
    if not PRECOMPUTED_DIR.exists():
        return result
    suffix = f"__{kind}.json"
    for path in PRECOMPUTED_DIR.glob(f"*{suffix}"):
        key = path.name[: -len(suffix)]
        result[key] = path.read_bytes()
    return result


def get_precomputed_summary_bytes(city: str, return_period_years: int | None) -> Optional[bytes]:
    return _load_bytes("summary").get(scenario_key(city, return_period_years))


def get_precomputed_risk_bytes(city: str, return_period_years: int | None) -> Optional[bytes]:
    return _load_bytes("risk").get(scenario_key(city, return_period_years))


def get_precomputed_summary(city: str, return_period_years: int | None) -> Optional[dict[str, Any]]:
    raw = get_precomputed_summary_bytes(city, return_period_years)
    return json.loads(raw) if raw is not None else None


def get_precomputed_risk(city: str, return_period_years: int | None) -> Optional[dict[str, Any]]:
    raw = get_precomputed_risk_bytes(city, return_period_years)
    return json.loads(raw) if raw is not None else None


def precomputed_scenario_count() -> int:
    """For the /api/health check: distinguishes "process is up" from
    "the build-time precompute step actually ran and produced results"."""
    return len(_load_bytes("summary"))
