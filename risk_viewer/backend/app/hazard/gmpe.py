"""Published Ground Motion Prediction Equations (GMPEs), via
``openquake.hazardlib`` (the GEM Foundation's open-source hazard library,
also the engine behind the USGS/GEM Global Earthquake Model). Only the
GMPE classes themselves are used, not the full OpenQuake Engine (its risk
calculators, PSHA logic trees, web server, etc.).

One published GMPE per tectonic regime, chosen for being widely used,
openly published, and matching each scenario's regime (see scenario.py
for the regime/source literature each city is anchored to):

- crustal (Guatemala City, Santo Domingo): Boore, Stewart, Seyhan &
  Atkinson (2014), "NGA-West2 Equations for Predicting PGA, PGV, and 5%
  Damped PSA for Shallow Crustal Earthquakes", Earthquake Spectra 30(3),
  one of the four NGA-West2 crustal GMPEs, in wide global use (including
  outside California) as a generic active-shallow-crustal model absent a
  region-specific one.
- interface (San Jose): Zhao et al. (2016), "Ground Motion Prediction
  Equations for Subduction Interface Earthquakes...", Bulletin of the
  Seismological Society of America 106(4), the SInter variant, developed
  specifically for subduction interface events and widely used in Latin
  American subduction-zone hazard studies (incl. Costa Rica).
- intraslab: Zhao et al. (2016) SSlab variant, from the same study, for
  completeness. Not currently used by any of the three pilot scenarios.

The regression equations and their sigma (aleatory variability) are the
published ones, evaluated by hazardlib itself. The *inputs* fed to them
(distance, vs30, rake, ztor) are still point-source/regional
approximations documented in scenario.py and site.py, not a full
rupture-plane/measured-Vs30 model.

Vs30 is passed straight into the GMPE (both BooreEtAl2014 and
ZhaoEtAl2016SInter/SSlab include their own Vs30 site-amplification term),
so there is no separate Vs30-to-amplification step here; see site.py for
what per-city Vs30 values feed in.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

import numpy as np
from openquake.hazardlib import imt as oq_imt
from openquake.hazardlib.contexts import RuptureContext, get_mean_stds
from openquake.hazardlib.gsim.boore_2014 import BooreEtAl2014
from openquake.hazardlib.gsim.zhao_2016 import ZhaoEtAl2016SInter, ZhaoEtAl2016SSlab

TectonicRegime = Literal["crustal", "interface", "intraslab"]

_GMPE_BY_REGIME = {
    "crustal": BooreEtAl2014(),
    "interface": ZhaoEtAl2016SInter(),
    "intraslab": ZhaoEtAl2016SSlab(),
}

GMPE_CITATION: dict[TectonicRegime, str] = {
    "crustal": "Boore, Stewart, Seyhan & Atkinson (2014), NGA-West2 shallow-crustal GMPE "
    "(Earthquake Spectra 30(3)).",
    "interface": "Zhao et al. (2016) subduction-interface GMPE, SInter variant "
    "(BSSA 106(4)).",
    "intraslab": "Zhao et al. (2016) subduction-intraslab GMPE, SSlab variant "
    "(BSSA 106(4)).",
}


@dataclass(frozen=True)
class GroundMotion:
    period_s: float
    median_sa_g: float
    sigma_ln: float


def _period_to_imt(period_s: float):
    return oq_imt.PGA() if period_s <= 0.0 else oq_imt.SA(period_s)


def _build_context(
    magnitude: float,
    distance_km: float,
    depth_km: float,
    regime: TectonicRegime,
    vs30: float,
    rake: float,
    ztor_km: float | None,
) -> RuptureContext:
    ctx = RuptureContext()
    ctx.mag = magnitude
    ctx.vs30 = vs30
    ctx.sids = np.array([0])
    if regime == "crustal":
        # BooreEtAl2014 wants Rjb (horizontal distance to the surface
        # projection of the rupture) and rake (style-of-faulting term).
        # For a point source, surface-projection distance == epicentral
        # distance.
        ctx.rake = rake
        ctx.rjb = np.array([distance_km])
    else:
        # Zhao et al. (2016) wants Rrup (closest distance to the rupture
        # surface) and ztor (depth to top of rupture). Without a fault
        # plane, Rrup is approximated as hypocentral distance from the
        # scenario's epicenter+depth point. ztor should not be set equal to
        # that hypocentral depth for a large interface rupture: interface
        # ruptures dip from shallow (near the trench) to deep, so the top
        # of the rupture sits well above the hypocenter/centroid depth.
        # Confirmed by direct testing: ztor=25km (== San Jose's hypocentral
        # depth) produces an unphysical spectral spike (SA(0.1s) jumping to
        # ~1.7g then collapsing by SA(1.0s)); ztor=10-15km gives a smooth,
        # plausible spectrum. ztor_km is therefore a separate, explicit
        # scenario field (see scenario.py), not derived from depth_km.
        ztor = ztor_km if ztor_km is not None else depth_km
        ctx.ztor = ztor
        ctx.rrup = np.array([math.sqrt(distance_km**2 + depth_km**2)])
        ctx.rvolc = np.array([0.0])  # no volcanic-arc path geometry modelled
    return ctx


def ground_motion_at_period(
    magnitude: float,
    distance_km: float,
    depth_km: float,
    regime: TectonicRegime,
    period_s: float,
    vs30: float,
    rake: float = 0.0,
    ztor_km: float | None = None,
) -> GroundMotion:
    gmpe = _GMPE_BY_REGIME[regime]
    ctx = _build_context(magnitude, distance_km, depth_km, regime, vs30, rake, ztor_km)
    result = get_mean_stds(gmpe, ctx, [_period_to_imt(period_s)])
    mean_ln, sigma_ln = float(result[0, 0, 0]), float(result[1, 0, 0])
    return GroundMotion(period_s=period_s, median_sa_g=math.exp(mean_ln), sigma_ln=sigma_ln)


def median_pga_g(
    magnitude: float,
    distance_km: float,
    depth_km: float,
    regime: TectonicRegime,
    vs30: float,
    rake: float = 0.0,
    ztor_km: float | None = None,
) -> float:
    return ground_motion_at_period(
        magnitude, distance_km, depth_km, regime, 0.0, vs30, rake, ztor_km
    ).median_sa_g
