"""The generic exposure layer endpoints (see app/layers/registry.py)."""

from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app import data_loader
from app.colors import categorical_legend
from app.data_loader import UNLABELED
from app.layers import LAYER_REGISTRY
from app.layers.registry import LayerSpec
from app.schemas import LayerAttributeOut, LayerOut

router = APIRouter(prefix="/api/layers", tags=["layers"])


def _get_layer(layer_id: str) -> LayerSpec:
    layer = LAYER_REGISTRY.get(layer_id)
    if layer is None:
        raise HTTPException(status_code=404, detail=f"Unknown layer: {layer_id}")
    return layer


@router.get("", response_model=list[LayerOut])
def list_layers() -> list[LayerOut]:
    return [
        LayerOut(
            id=layer.id,
            label=layer.label,
            description=layer.description,
            attributes=[
                LayerAttributeOut(name=a.name, label=a.label, kind=a.kind)
                for a in layer.attributes
            ],
            cities=layer.cities(),
        )
        for layer in LAYER_REGISTRY.values()
    ]


@router.get("/{layer_id}/data")
def layer_data(layer_id: str, city: str | None = None) -> dict:
    layer = _get_layer(layer_id)
    return layer.load(city)


@router.get("/{layer_id}/legend")
def layer_legend(layer_id: str) -> dict[str, dict[str, str]]:
    layer = _get_layer(layer_id)
    legend: dict[str, dict[str, str]] = {}
    for attribute in layer.attributes:
        if attribute.kind != "categorical":
            continue
        values = data_loader.attribute_domain(attribute.name)
        legend[attribute.name] = categorical_legend(values, unlabeled_value=UNLABELED)
    return legend
