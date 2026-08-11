# syntax=docker/dockerfile:1
#
# Builds the frontend's static assets, then bakes them into a Caddy
# image alongside the Caddyfile that serves them and reverse-proxies
# /api/* to the backend container. The Node toolchain never ships to
# production -- only its build output does.

FROM node:20-slim AS frontend-builder

WORKDIR /app

COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci

COPY frontend/ .

# Empty string, not e.g. "/api": api.ts already prefixes every request
# path with "/api/...", so an empty base makes every fetch a same-origin
# relative request -- exactly right once Caddy serves both the static
# assets and the /api/* proxy from one origin (see ../proxy/Caddyfile).
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE
RUN npm run build

FROM caddy:2-alpine

COPY --from=frontend-builder /app/dist /srv/frontend/dist
COPY deploy/proxy/Caddyfile /etc/caddy/Caddyfile
