"""Set/clear an expert-specified structural-typology hypothesis for a
city (see app/typology_hypothesis.py for what this means and why it's
built the way it is). Setting one changes what every subsequent scenario
request for that city returns, until cleared."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from app import typology_hypothesis
from app.cities import CITIES

router = APIRouter(prefix="/api/cities", tags=["typology_hypothesis"])


class SetTypologyHypothesisRequest(BaseModel):
    proportions: dict[str, float] = Field(
        description="Class -> share of buildings, must sum to 1.0. "
        f"Classes: {list(typology_hypothesis.KNOWN_CLASSES)}."
    )
    seed: int = 0


def _hypothesis_to_json(hypothesis: typology_hypothesis.TypologyHypothesis) -> dict:
    proportions = hypothesis.proportions_dict()
    return {
        "city": hypothesis.city,
        "proportions": proportions,
        "seed": hypothesis.seed,
        "normalized_entropy": typology_hypothesis.normalized_entropy(proportions),
        "typology_beta": typology_hypothesis.hypothesis_typology_beta(proportions),
        "fingerprint": hypothesis.fingerprint(),
    }


@router.get("/{city}/typology_hypothesis")
def get_typology_hypothesis(city: str) -> dict | None:
    if city not in CITIES:
        raise HTTPException(status_code=404, detail=f"Unknown city: {city}")
    hypothesis = typology_hypothesis.get_hypothesis(city)
    return _hypothesis_to_json(hypothesis) if hypothesis is not None else None


@router.post("/{city}/typology_hypothesis")
def set_typology_hypothesis(city: str, body: SetTypologyHypothesisRequest) -> dict:
    if city not in CITIES:
        raise HTTPException(status_code=404, detail=f"Unknown city: {city}")
    try:
        hypothesis = typology_hypothesis.set_hypothesis(city, body.proportions, body.seed)
    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    return _hypothesis_to_json(hypothesis)


@router.delete("/{city}/typology_hypothesis")
def delete_typology_hypothesis(city: str) -> dict:
    if city not in CITIES:
        raise HTTPException(status_code=404, detail=f"Unknown city: {city}")
    typology_hypothesis.clear_hypothesis(city)
    return {"city": city, "cleared": True}
