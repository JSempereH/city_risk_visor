"""Great-circle distance, shared by the deterministic (ground_motion.py)
and probabilistic (psha.py) hazard paths; split out on its own so
neither has to import the other just for this."""

from __future__ import annotations

import math

import numpy as np

EARTH_RADIUS_KM = 6371.0


def haversine_km(lat1: float, lon1: float, lat2: float, lon2: float) -> float:
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    dphi = math.radians(lat2 - lat1)
    dlambda = math.radians(lon2 - lon1)
    a = math.sin(dphi / 2) ** 2 + math.cos(phi1) * math.cos(phi2) * math.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * math.asin(math.sqrt(a))


def haversine_km_array(lat1: float, lon1: float, lats2: np.ndarray, lons2: np.ndarray) -> np.ndarray:
    """Same formula as haversine_km, but from one fixed point (e.g. a
    scenario's epicenter) to many points at once (e.g. every building in
    a city), for batching the distance computation instead of calling
    haversine_km once per building."""
    phi1 = math.radians(lat1)
    phi2 = np.radians(lats2)
    dphi = np.radians(lats2 - lat1)
    dlambda = np.radians(lons2 - lon1)
    a = np.sin(dphi / 2) ** 2 + math.cos(phi1) * np.cos(phi2) * np.sin(dlambda / 2) ** 2
    return 2 * EARTH_RADIUS_KM * np.arcsin(np.sqrt(a))
