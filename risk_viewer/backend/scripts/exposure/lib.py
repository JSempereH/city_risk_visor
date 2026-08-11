"""Shared constants for the exposure-data reproduction scripts. See
scripts/exposure/README.md for sources.
"""

from __future__ import annotations

from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent
RAW_DIR = SCRIPTS_DIR / "_raw"  # downloaded HDX resources, gitignored
BACKEND_DIR = SCRIPTS_DIR.parents[1]
EXPOSURE_GPKG_PATH = BACKEND_DIR / "app" / "data" / "exposure" / "all_cities_combined.gpkg"
