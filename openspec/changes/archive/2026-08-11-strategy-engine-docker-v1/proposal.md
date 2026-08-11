## Why

Strategy Engine has no production container runtime yet. Pre-Docker repository cleanup is complete and all verification gates pass, so the next step is a minimal, secure production Docker image — without touching application or HTTP semantics.

## What Changes

Add a production Dockerfile and `.dockerignore` for Strategy Engine: Python 3.12 base image, the existing `strategy-engine` console entrypoint as PID1, container-side bind to `0.0.0.0:8090`, non-root UID/GID `10001`, read-only-root-filesystem support, no persistent volume, `GET /health` as the Docker healthcheck, and a strict build-context exclusion list. Market Data Service stays an external HTTP dependency reached through `STRATEGY_ENGINE_MDS_BASE_URL`; no other service gets a container in this repo.

## Impact

New capability `strategy-engine-docker-v1`. No production code, HTTP contract, or existing OpenSpec capability changes. This proposal is spec-only; apply (writing the Dockerfile) is deferred to a follow-up.
