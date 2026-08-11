# Brief: automated per-city input acquisition for a seismic risk viewer

Copy this document as the task brief for a separate coding agent, in a
separate repository, whose job is to build a reusable tool: given a city
name and country, produce the input datasets a per-building seismic risk
viewer needs to add that city. Written to be self-contained: the agent
building this tool will not have access to the risk viewer's own
conversation history or codebase beyond what's quoted here.

## What the consuming system needs

The risk viewer (a FastAPI + MapLibre app, not part of this task)
computes per-building seismic risk: capacity curves, ATC-40 nonlinear
demand, fragility curves, HAZUS casualty rates, all evaluated per
individual building, not per grid cell or administrative area. It
already has this working for 3 pilot cities and a documented, reusable
pipeline for two pieces already solved and generic to any city
worldwide (do not rebuild these):

- **Vs30** (site amplification): streamed from the USGS Global Vs30 Map
  (30-arcsecond global coverage) via GDAL's HTTP range-request
  streaming, no full-grid download needed.
- **Population**: WorldPop's Global High Resolution Population
  Denominators (2020, 100m resolution), disaggregated to individual
  buildings by built volume (footprint area times floor count).

What this tool needs to solve instead, the two genuinely unsolved
problems:

### 1. Real per-building footprint geometry and basic attributes

Not a statistical or aggregated exposure model. Output must be one
polygon per real building, at minimum with a stable building ID,
footprint geometry (a real polygon, not a point or grid-cell centroid),
number of floors (or a defensible estimate), and height (or a
defensible estimate) where obtainable.

Research and evaluate public sources yourself: coverage and quality
vary hugely by city. Candidates worth investigating: OpenStreetMap
building footprints (excellent in some cities, sparse in others);
Microsoft's Global ML Building Footprints and Google's Open Buildings
(satellite-derived, near-global, no attributes beyond geometry);
floor-count/height estimation from satellite imagery, LiDAR-derived
surface models, or shadow-length analysis; national cadastral/GIS
open-data portals where they exist. State clearly, per city, which
source(s) you used and their real coverage: a tool that silently
returns a sparse dataset without saying so is worse than one that says
plainly that coverage is incomplete.

### 2. Structural-typology classification (the hardest part)

Every building needs a `structural_system` label, or a real distribution
over candidate labels with a confidence score, not a fabricated single
answer: the primary construction material or lateral-load-resisting
system, mapped into a standard taxonomy (GEM Building Taxonomy v4.0's
macro-classes, or a compatible national convention).

This is a real, currently unsolved research problem, not a lookup. No
global dataset gives free, building-level structural-typology ground
truth (GEM's own global exposure model is aggregated to grid cells or
admin units and says so in its own documentation). Plausible approaches
worth evaluating, none a sure thing, be honest about which you tried and
how well each performed with a real held-out accuracy number, not a
claimed one:

- A locally sourced labeled sample (a census, a university study, a
  post-earthquake reconnaissance report such as StEER/GEER on
  DesignSafe-CI) used to train a classifier over the full footprint set:
  the approach the risk viewer's own pilot cities already use (an
  ensemble of LogisticRegression/RandomForest/XGBoost trained on labeled
  zones, inferring the rest). A labeled sample of even a few hundred
  buildings per city is enough to bootstrap this.
- Computer-vision classification from satellite or street-level imagery
  (an active, uncertain research area, report real validation numbers).
- OpenStreetMap tags (`building:material`, `building:levels`) where
  present: typically sparse, but free and worth checking before
  investing in anything heavier.

Every building's typology label must carry an explicit confidence or
uncertainty signal (a probability distribution over classes, or at
minimum a score): the consuming system propagates uncertainty honestly
throughout (Monte Carlo casualty bands, logic-tree epistemic bands,
GPR predictive std for capacity curves), and a label presented as
ground truth when it is actually a guess would break that pattern.

## A related sub-task: seismic source model discovery

Not the same kind of problem, but worth including if practical: given a
country or region, find a publicly available seismic source model and
ground-motion-prediction-equation logic tree in OpenQuake-compatible
format (NRML XML), suitable for a classical PSHA run. GEM Foundation's
regional/national hazard models are the most common source; national
seismological institutes sometimes publish their own. Report the
license terms found (some restrict commercial reuse) and whether the
model needs restricting to a sub-region to stay computationally
tractable (a real problem the risk viewer hit: an unrestricted regional
mosaic model exploded to 48 billion realizations before being scoped
down).

## Output format

Whatever format is easiest to produce reliably (GeoPackage is a
reasonable default for the footprint layer), but be explicit and
consistent about the schema, and keep confidence/uncertainty fields
separate from point-estimate fields.

## What "done" looks like

Given a city name, the tool should produce: a footprint dataset with
real building geometry and best-effort floor/height attributes; a
structural-typology label with confidence per building; and a report of
what seismic source model, if any, was found for that country, with its
license and any restriction needed for tractability. Flag explicitly,
per city, which of these you could not obtain or could only obtain at
low confidence: a partial, honest result is far more useful than a
complete-looking one that silently guessed.
