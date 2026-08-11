"""Shared paths and helpers for the PSHA/disaggregation reproduction
scripts. See scripts/psha/README.md for the full pipeline and sources.
"""

from __future__ import annotations

import csv
import sqlite3
from pathlib import Path
from typing import Sequence

SCRIPTS_DIR = Path(__file__).resolve().parent
CONFIGS_DIR = SCRIPTS_DIR / "configs"
RAW_DIR = SCRIPTS_DIR / "_raw"  # downloaded source models, gitignored
DATA_DIR = SCRIPTS_DIR.parents[1] / "app" / "data" / "psha"

CITIES = ("san_jose", "guatemala", "santo_domingo")

# Must be a substring of that city's configs/{city}/job_hazard.ini
# [general] description, used to find the classical calc a
# disaggregation run should reuse via hazard_calculation_id.
CLASSICAL_DESCRIPTIONS = {
    "san_jose": "CRSHM2022 classical PSHA for San Jose",
    "guatemala": "CCA with fault-geometry source-model uncertainty, Guatemala City",
    "santo_domingo": "DOM source-model epistemic uncertainty",
}


def raw_dir(city: str) -> Path:
    return RAW_DIR / city


def config_dir(city: str) -> Path:
    return CONFIGS_DIR / city


def overlay_configs(city: str) -> None:
    """Copies this city's committed job.ini/logic-tree/site files on top
    of its downloaded raw model directory. OpenQuake resolves a job.ini's
    relative paths (source model, gsim logic tree, sites_csv) against the
    job.ini's own directory, so the two have to live side by side to run.
    """
    import shutil

    src = config_dir(city)
    dst = raw_dir(city)
    dst.mkdir(parents=True, exist_ok=True)
    for f in src.iterdir():
        if f.is_file():
            shutil.copy2(f, dst / f.name)


def latest_calc_id(description_substring: str) -> int:
    """Most recent OpenQuake job id whose description contains the given
    substring (used to find the classical calc a disaggregation run
    should reuse via hazard_calculation_id, without hardcoding calc ids).
    """
    db_path = Path.home() / "oqdata" / "db.sqlite3"
    con = sqlite3.connect(db_path)
    try:
        cur = con.execute(
            "select id from job where description like ? and status = 'complete' "
            "order by id desc limit 1",
            (f"%{description_substring}%",),
        )
        row = cur.fetchone()
    finally:
        con.close()
    if row is None:
        raise RuntimeError(
            f"No complete OpenQuake job found with description containing {description_substring!r}. "
            "Run run_classical.py for this city first."
        )
    return row[0]


def write_hazard_curve_csv(calc_id: int, out_csv: Path) -> None:
    """Extracts hcurves-stats (mean/p16/p84) from a classical calc's
    datastore into this project's imt,level,mean_poe[,p16_poe,p84_poe]
    CSV format (read by app/hazard/psha.py)."""
    from openquake.commonlib import datastore

    dstore = datastore.read(calc_id)
    oq = dstore["oqparam"]
    imtls = dict(oq.imtls)
    stats = list(oq.hazard_stats())
    arr = dstore["hcurves-stats"][:]  # (n_sites, n_stats, n_imts, n_levels)
    assert arr.shape[0] == 1, f"expected 1 site, got {arr.shape[0]}"

    stat_name_map = {}
    for s in stats:
        if s == "mean":
            stat_name_map[s] = "mean"
        elif s.startswith("quantile-"):
            stat_name_map[s] = f"p{int(round(float(s.split('-')[1]) * 100))}"

    imt_names = list(imtls)
    stat_keys = sorted(set(stat_name_map.values()))
    rows: dict[tuple[str, float], dict[str, float]] = {}
    for m, imt in enumerate(imt_names):
        levels = imtls[imt]
        for si, stat in enumerate(stats):
            stat_key = stat_name_map[stat]
            for li, level in enumerate(levels):
                rows.setdefault((imt, float(level)), {})[stat_key] = float(arr[0, si, m, li])

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["imt", "level"] + [f"{k}_poe" for k in stat_keys])
        for (imt, level), by_stat in sorted(rows.items(), key=lambda kv: (kv[0][0], kv[0][1])):
            writer.writerow([imt, level] + [by_stat[k] for k in stat_keys])
    print(f"wrote {out_csv} ({len(rows)} rows, imts={imt_names}, stats={stat_keys})")


def write_disagg_csv(calc_id: int, return_periods_years: Sequence[int], out_csv: Path) -> None:
    """Extracts disagg-stats/Mag_Dist (PGA slice) from a disaggregation
    calc's datastore into return_period_years,mag_bin,dist_bin,fraction
    long-format CSV (read by app/hazard/psha.py::disaggregation(), which
    parses mag_bin/dist_bin as plain floats, bin *centers*, not
    "lo-hi" range strings).
    """
    from openquake.commonlib import datastore

    dstore = datastore.read(calc_id)
    oq = dstore["oqparam"]
    imt_names = list(oq.imtls)
    pga_idx = imt_names.index("PGA")

    mag_edges = dstore["disagg-bins/Mag"][:]
    dist_edges = dstore["disagg-bins/Dist"][:]
    arr = dstore["disagg-stats/Mag_Dist"][:]  # (n_sites, n_mag, n_dist, n_imts, n_poes, n_stats)
    assert arr.shape[0] == 1, f"expected 1 site, got {arr.shape[0]}"

    out_csv.parent.mkdir(parents=True, exist_ok=True)
    with open(out_csv, "w", newline="") as f:
        writer = csv.writer(f)
        writer.writerow(["return_period_years", "mag_bin", "dist_bin", "fraction"])
        for pi, years in enumerate(return_periods_years):
            matrix = arr[0, :, :, pga_idx, pi, 0]
            total = matrix.sum()
            for mi in range(matrix.shape[0]):
                mag_bin = (float(mag_edges[mi]) + float(mag_edges[mi + 1])) / 2
                for di in range(matrix.shape[1]):
                    fraction = float(matrix[mi, di] / total) if total > 0 else 0.0
                    if fraction <= 0:
                        continue
                    dist_bin = (float(dist_edges[di]) + float(dist_edges[di + 1])) / 2
                    writer.writerow([years, mag_bin, dist_bin, fraction])
    print(f"wrote {out_csv} for return periods {return_periods_years}")
