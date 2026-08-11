from __future__ import annotations

from pydantic import BaseModel


class LayerAttributeOut(BaseModel):
    name: str
    label: str
    kind: str


class LayerOut(BaseModel):
    id: str
    label: str
    description: str
    attributes: list[LayerAttributeOut]
    cities: list[str]
