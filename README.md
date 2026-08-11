# city_risk_visor

This repo tracks [`risk_viewer/`](risk_viewer/README.md), a per-building
seismic risk viewer (exposure, structural typology, capacity/fragility
curves, hazard, and risk, for San Jose, Guatemala City, and Santo
Domingo). See `risk_viewer/README.md` for what it does and how to run
it.

Sibling directories that may exist alongside this repo locally
(`footprint_attributes/`, `FragilityCurves/`, `ml_structural_system/`)
are separate projects, consumed by `risk_viewer` as external data or
dependencies. They are not part of this repo (see `.gitignore`) and are
not included in a fresh clone.
