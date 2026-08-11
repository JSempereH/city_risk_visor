"""Generic layer registry.

A `LayerSpec` bundles everything the API needs to expose one map layer:
its id/label, the attributes it can be colored/filtered by, and how to
load its data. `/api/layers*` routes are written against this registry
rather than against a single hardcoded "buildings" concept, so adding a
future "damage" layer is a new module that registers itself here plus a
reused route, not a new endpoint family.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Literal

AttributeKind = Literal["categorical", "sequential"]


@dataclass(frozen=True)
class LayerAttribute:
    name: str
    label: str
    kind: AttributeKind


@dataclass(frozen=True)
class LayerSpec:
    id: str
    label: str
    description: str
    attributes: list[LayerAttribute]
    load: Callable[[str | None], dict[str, Any]]
    cities: Callable[[], list[str]]


LAYER_REGISTRY: dict[str, LayerSpec] = {}


def register(spec: LayerSpec) -> LayerSpec:
    LAYER_REGISTRY[spec.id] = spec
    return spec
