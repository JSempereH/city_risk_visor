"""The v1 "exposure_typology" layer: building footprints colored by
structural typology or other exposure attributes."""

from __future__ import annotations

from app import data_loader
from app.layers.registry import LayerAttribute, LayerSpec, register

EXPOSURE_TYPOLOGY = register(
    LayerSpec(
        id="exposure_typology",
        label="Exposure & typology",
        description=(
            "Building footprints with structural typology, code quality, "
            "roof material, floor count, height, and construction year."
        ),
        attributes=[
            LayerAttribute("structural_system_class", "Structural system", "categorical"),
            LayerAttribute("code_quality", "Code quality", "categorical"),
            LayerAttribute("roof_material", "Roof material", "categorical"),
            LayerAttribute("n_floors", "Number of floors", "sequential"),
            LayerAttribute("height", "Height (m)", "sequential"),
        ],
        load=data_loader.feature_collection,
        cities=data_loader.known_cities,
    )
)
