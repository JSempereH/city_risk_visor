# Reproducing the Vs30 and population data

`app/data/vs30/*.csv` and `app/data/population/*.csv` are precomputed
from third-party rasters, not vendored by hand; see `app/hazard/site.py`
and `app/risk/population.py`'s own docstrings for how this data is used
at request time. This directory is the pipeline that produces them.

## One-shot

```bash
cd backend
uv sync --group geodata          # rasterio, only needed for these scripts
uv run python scripts/geodata/build_vs30.py            # all 3 cities
uv run python scripts/geodata/build_population.py       # all 3 cities
```

Both accept city names as arguments to run just one
(`build_vs30.py san_jose`).

## Sources

| Data | Source | Method |
|---|---|---|
| Vs30 | USGS Global Vs30 Map (Wald & Allen, 2007; Allen & Wald, 2009), 30-arcsecond topographic-slope-based estimate, [apps.usgs.gov/shakemap_geodata/vs30/global_vs30.grd](https://apps.usgs.gov/shakemap_geodata/vs30/global_vs30.grd) (~610 MB) | Streamed via GDAL's `/vsicurl/` virtual filesystem: the USGS server supports HTTP range requests, so `build_vs30.py` only downloads the few hundred KB covering each city's building extent, never the full grid. |
| Population | WorldPop Global High Resolution Population Denominators, 2020, 100m resolution, [data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/{ISO3}](https://data.worldpop.org/GIS/Population/Global_2000_2020_Constrained/2020/BSGM/) | Per-country files (~1-2 MB) downloaded into `_raw/` (gitignored). `build_population.py` disaggregates each raster cell's population to the buildings inside it, weighted by built volume (footprint area times floor count, 1 floor assumed where none is recorded). Buildings whose own cell has no data snap to the nearest cell that does. |

Vs30 varies block to block within a city (unlike the PSHA hazard curve,
evaluated at one representative site, see `../psha/README.md`), so it's
read per building from a real global dataset. WorldPop is the standard
high-resolution population product for building-level casualty
estimation.

## A known limitation

Re-running `build_population.py` for San Jose does not reproduce the
vendored CSV byte-for-byte: about 10% of buildings land in a different
WorldPop cell than the original run assigned them to, since the exact
crop window used the first time was not preserved. Investigated, not
just noticed:

- The disaggregation weighting formula was confirmed exactly correct by
  comparing population ratios between very close building pairs against
  their footprint-area times floors ratio: exact match.
- The raw WorldPop cell values were confirmed correct by direct
  point-sampling the raster at a building's coordinate.
- City-wide totals are close (San Jose: 1432.6 to 1446.8, +1.0%).
- Guatemala and Santo Domingo's re-run matched the vendored data
  exactly (0 mismatches), since San Jose's raster tile happens to have
  more building clusters sitting close to its 100m cell boundaries.

Net effect if San Jose's population.csv is regenerated: some individual
buildings' population shifts by up to about 1 person, city-wide totals
shift by about 1%. Not a correctness bug, but not a guarantee of
bit-identical output on every re-run.
