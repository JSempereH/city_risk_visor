"""Set/clear an expert-specified structural-typology *prior* for a city
(see app/typology_prior.py for what this means, and how it differs from
app/typology_hypothesis.py). Setting one changes what every subsequent
map/building/scenario request for that city returns, until cleared --
same "live, in-memory, per-city setting" convention as
app/routers/typology_hypothesis.py."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import data_loader, typology_prior
from app.cities import CITIES
from app.typology_ensemble import get_ensemble_quality_metrics

router = APIRouter(prefix="/api/cities", tags=["typology_prior"])


class SetTypologyPriorRequest(BaseModel):
    proportions: dict[str, float] = Field(
        description="Class -> share of the WHOLE city/neighborhood population (ground truth "
        "included), must sum to 1.0. Only ML-estimated buildings are ever actually adjusted; "
        "see app/typology_prior.py's module docstring."
    )
    alpha: float = Field(default=0.6, ge=0.0, le=1.0, description="Trust weight, 0=ignore the prior, 1=prior decides.")


def _feasibility_to_json(feasibility: typology_prior.PriorFeasibility) -> dict:
    return {
        "ground_truth_counts": feasibility.ground_truth_counts,
        "n_ground_truth": feasibility.n_ground_truth,
        "n_estimated": feasibility.n_estimated,
        "n_total": feasibility.n_total,
        "prior_within_estimated": feasibility.prior_within_estimated,
    }


def _prior_to_json(prior: typology_prior.TypologyPrior) -> dict:
    return {
        "city": prior.city,
        "proportions": prior.proportions_dict(),
        "alpha": prior.alpha,
        "fingerprint": prior.fingerprint(),
    }


@router.get("/{city}/typology_prior")
def get_typology_prior(city: str) -> dict | None:
    if city not in CITIES:
        raise HTTPException(status_code=404, detail=f"Unknown city: {city}")
    prior = typology_prior.get_prior(city)
    return _prior_to_json(prior) if prior is not None else None


@router.get("/{city}/typology_prior/available_classes")
def get_available_classes(city: str) -> dict:
    """The classes this city's classifier ensemble can actually predict
    (see typology_prior.available_classes's own docstring for why this
    isn't a fixed global list), so the settings UI only ever offers
    inputs for classes a prior can meaningfully target."""
    if city not in CITIES:
        raise HTTPException(status_code=404, detail=f"Unknown city: {city}")
    buildings = data_loader.get_buildings_by_city(city)
    return {
        "city": city,
        "classes": typology_prior.available_classes(buildings),
        # False for a city whose ensemble has no held-out quality metrics
        # (e.g. lomas_centinela's cross-city pooled model, never checked
        # against real local examples), so the settings UI can caveat the
        # prior form instead of presenting it as equally trustworthy.
        "locally_validated": get_ensemble_quality_metrics(city) is not None,
    }


@router.post("/{city}/typology_prior")
def set_typology_prior(city: str, body: SetTypologyPriorRequest) -> dict:
    if city not in CITIES:
        raise HTTPException(status_code=404, detail=f"Unknown city: {city}")
    buildings = data_loader.get_buildings_by_city(city)
    try:
        prior, feasibility = typology_prior.set_prior(city, body.proportions, body.alpha, buildings)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return {**_prior_to_json(prior), "feasibility": _feasibility_to_json(feasibility)}


@router.delete("/{city}/typology_prior")
def delete_typology_prior(city: str) -> dict:
    if city not in CITIES:
        raise HTTPException(status_code=404, detail=f"Unknown city: {city}")
    typology_prior.clear_prior(city)
    return {"city": city, "cleared": True}
