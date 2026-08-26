"""Downloads each city's published source model into scripts/psha/_raw/
(gitignored: these are third-party, non-trivially-sized model archives,
not something this repo vendors). See README.md for licenses.

Usage: uv run python scripts/psha/fetch_sources.py [city ...]
(no args = all three cities)
"""

from __future__ import annotations

import io
import json
import sys
import tempfile
import urllib.request
import zipfile
from pathlib import Path

from lib import CITIES, raw_dir


def _download(url: str) -> bytes:
    # Mendeley (unlike the GEM cloud share) rejects requests with no
    # User-Agent header.
    req = urllib.request.Request(url, headers={"User-Agent": "risk_viewer-psha-fetch/1.0"})
    with urllib.request.urlopen(req, timeout=120) as resp:
        return resp.read()


def _extract_zip(data: bytes, dest: Path) -> None:
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(io.BytesIO(data)) as zf:
        zf.extractall(dest)


def fetch_san_jose() -> None:
    """CRSHM2022 (Hidalgo-Leiva et al. 2022), unmodified base model, via
    Arroyo (2025)'s Mendeley supplement, CC BY 4.0.
    https://doi.org/10.17632/7x8xv2yf23.2, CRSHM2022 subfolder.
    """
    dest = raw_dir("san_jose")
    if dest.exists() and any(dest.iterdir()):
        print(f"san_jose: {dest} already populated, skipping")
        return
    dataset_slug, version = "7x8xv2yf23", "2"
    folders = json.loads(
        _download(f"https://data.mendeley.com/public-api/datasets/{dataset_slug}/folders/{version}")
    )
    folder = next(f for f in folders if f["name"] == "CRSHM2022")
    files = json.loads(
        _download(
            f"https://data.mendeley.com/public-api/datasets/{dataset_slug}/files"
            f"?folder_id={folder['id']}&version={version}"
        )
    )
    dest.mkdir(parents=True, exist_ok=True)
    for entry in files:
        url = entry["content_details"]["download_url"]
        (dest / entry["filename"]).write_bytes(_download(url))
        print(f"san_jose: fetched {entry['filename']}")


def fetch_guatemala() -> None:
    """GEM Caribbean & Central America (CCA) regional model, v2026.0.0,
    CC BY-NC-SA 4.0. https://hazard.openquake.org/gem/models/CCA
    (public Nextcloud share). Restricted at run time to Guatemala/CAM-
    tagged sources, see configs/guatemala/ and README.md.
    """
    dest = raw_dir("guatemala")
    if dest.exists() and any(dest.iterdir()):
        print(f"guatemala: {dest} already populated, skipping")
        return
    data = _download("https://cloud.openquake.org/s/32sonTGybwxettb/download?path=%2F&files=job.zip")
    _extract_zip(data, dest)
    print(f"guatemala: extracted to {dest}")


def fetch_santo_domingo() -> None:
    """GEM Dominican Republic Hazard Model (TREQ project; Johnson et al.
    2024's own OpenQuake input), v2021.2.0, CC BY-SA 4.0.
    https://cloud.openquake.org/s/PZ3yydAyy6XZR3X (public Nextcloud
    share, downloaded whole as its own "download entire share" zip).
    """
    dest = raw_dir("santo_domingo")
    if dest.exists() and any(dest.iterdir()):
        print(f"santo_domingo: {dest} already populated, skipping")
        return
    data = _download("https://cloud.openquake.org/s/PZ3yydAyy6XZR3X/download")
    _extract_zip(data, dest)
    # The share's zip has a top-level v2021.2.0/ folder; flatten it so
    # raw_dir("santo_domingo") is directly the model root, matching the
    # other two cities' layout.
    nested = dest / "v2021.2.0"
    if nested.is_dir():
        for item in nested.iterdir():
            item.rename(dest / item.name)
        nested.rmdir()
    print(f"santo_domingo: extracted to {dest}")


def fetch_lomas_centinela() -> None:
    """GEM Mexico (MEX) national hazard model, v2025.0.0, CC BY-NC-SA 4.0.
    https://hazard.openquake.org/gem/models/MEX (public Nextcloud share
    at https://cloud.openquake.org/s/xqHswGaHQYJYXb8, "Open Version
    Download"). Single source-model branch (no fault-geometry-style
    epistemic choice to restrict, unlike Guatemala's CCA model); run at
    reduced logic-tree sampling instead, see configs/lomas_centinela/
    and README.md.

    The share's zip nests a second zip one level down
    (v2025.0.0/job.zip, alongside a README/LICENSE): that inner zip is
    the actual model root (ssmLT_clean.xml, gmmLT_clean.xml, ssm/, ...),
    so it gets extracted directly into `dest`, flattening both levels,
    the same as santo_domingo's single level of flattening below.
    """
    dest = raw_dir("lomas_centinela")
    if dest.exists() and any(dest.iterdir()):
        print(f"lomas_centinela: {dest} already populated, skipping")
        return
    data = _download("https://cloud.openquake.org/s/xqHswGaHQYJYXb8/download")
    with tempfile.TemporaryDirectory() as tmp:
        tmp_path = Path(tmp)
        _extract_zip(data, tmp_path)
        inner_zips = list(tmp_path.glob("*/job.zip"))
        if len(inner_zips) != 1:
            raise RuntimeError(
                f"lomas_centinela: expected exactly one */job.zip in the downloaded share, found {inner_zips}"
            )
        _extract_zip(inner_zips[0].read_bytes(), dest)
    print(f"lomas_centinela: extracted to {dest}")


FETCHERS = {
    "san_jose": fetch_san_jose,
    "guatemala": fetch_guatemala,
    "santo_domingo": fetch_santo_domingo,
    "lomas_centinela": fetch_lomas_centinela,
}


def main() -> None:
    cities = sys.argv[1:] or list(CITIES)
    for city in cities:
        FETCHERS[city]()


if __name__ == "__main__":
    main()
