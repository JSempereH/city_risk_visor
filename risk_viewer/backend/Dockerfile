# syntax=docker/dockerfile:1
#
# Multi-stage build: the builder stage resolves dependencies (including
# footprint-attributes, a git dependency -- see pyproject.toml) and bakes
# the 12 known scenario combinations (see scripts/precompute.py) into
# app/data/precomputed/; the runtime stage ships only the built venv, the
# app code, and those baked results -- no build toolchain, no uv, no git.

FROM python:3.13-slim AS builder

# git is needed by `uv sync` to resolve the footprint-attributes
# dependency, which is pinned to a git commit, not a local path or PyPI
# release (see pyproject.toml's [tool.uv.sources]).
RUN apt-get update \
    && apt-get install -y --no-install-recommends git \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Resolve dependencies first, in their own layer, so editing app code
# doesn't invalidate the (slow: openquake + geopandas) dependency install.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY app ./app
COPY scripts ./scripts
RUN uv sync --frozen --no-dev

# Bake the 12 (city, scenario) menu combinations reachable through the
# UI's normal controls; see docs -- this is what makes every "menu"
# request instant instead of a 15-90s live computation.
RUN uv run python scripts/precompute.py

FROM python:3.13-slim AS runtime

# libexpat1 provides libexpat.so.1, which fiona (a geopandas/openquake
# I/O backend) dynamically loads at import time. Its wheel bundles its
# own libgdal, but not libexpat -- discovered empirically (a plain
# python:3.13-slim runtime image fails on `import fiona` without this;
# the builder stage above doesn't hit it only because installing git
# there happens to pull libexpat1 in as a transitive dependency).
RUN apt-get update \
    && apt-get install -y --no-install-recommends libexpat1 \
    && rm -rf /var/lib/apt/lists/*

RUN useradd --create-home --shell /usr/sbin/nologin appuser
WORKDIR /app

COPY --from=builder /app/.venv /app/.venv
COPY --from=builder /app/app /app/app

ENV PATH="/app/.venv/bin:$PATH" PYTHONUNBUFFERED=1

USER appuser

EXPOSE 8001

# start-period covers app startup, not just container boot: app/main.py's
# lifespan hook blocks on loading and processing every city's exposure
# data before uvicorn accepts connections (see that module's docstring),
# on top of importing openquake.hazardlib (every GMPE module) -- observed
# 15-150s total depending on how warm the image layers are in the OS
# page cache. Generous budget so a slow first boot doesn't get marked
# unhealthy before it's actually done.
HEALTHCHECK --interval=15s --timeout=5s --start-period=3m --retries=10 \
    CMD python -c "import urllib.request,sys; sys.exit(0 if urllib.request.urlopen('http://localhost:8001/api/health').status == 200 else 1)"

# No --reload (dev-only, must never run in production) and no --workers
# (a second worker process would hold its own unshared in-memory
# lru_cache for the Custom Scenario path, see app/risk/service.py).
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8001"]
