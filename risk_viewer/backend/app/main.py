from __future__ import annotations

from contextlib import asynccontextmanager
from typing import Any, AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app import data_loader, precomputed
from app.config import FRONTEND_ORIGIN
from app.routers import layers, scenarios, typology_ensemble, typology_hypothesis, typology_prior, vulnerability


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    # data_loader.load_geodataframe() is lazy and lru_cache'd for the
    # process lifetime (see its docstring), so it would otherwise run on
    # whichever request happens to touch it first (e.g. the exposure
    # map layer, or any risk computation), hanging a real visitor's
    # first request for however long that takes (grows with total
    # building count; footprint_attributes.position()'s per-building
    # contact geometry scales worse than linearly, see
    # docs/adding_a_city.md's La Guaira case study). Paying it here
    # instead, before uvicorn starts accepting connections, means the
    # container's healthcheck (see Dockerfile/docker-compose.yml, both
    # tuned for this) only passes once the app can actually serve every
    # endpoint promptly.
    data_loader.load_geodataframe()
    yield


app = FastAPI(title="Risk Viewer API", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=[FRONTEND_ORIGIN],
    allow_methods=["GET", "POST", "DELETE"],
    allow_headers=["*"],
)

app.include_router(layers.router)
app.include_router(vulnerability.router)
app.include_router(scenarios.router)
app.include_router(typology_ensemble.router)
app.include_router(typology_hypothesis.router)
app.include_router(typology_prior.router)


@app.get("/api/health")
def health() -> dict[str, Any]:
    return {"status": "ok", "precomputed_scenarios": precomputed.precomputed_scenario_count()}
