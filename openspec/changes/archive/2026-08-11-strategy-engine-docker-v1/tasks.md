## 1. Build the image

- [x] Write a production `Dockerfile`: Python 3.12 base, install the package, run the existing `strategy-engine` console entrypoint directly as PID1 (no shell/supervisor wrapper).
- [x] Set `PYTHONDONTWRITEBYTECODE=1` and unbuffered stdout/stderr in the image.
- [x] Create a non-root user/group `10001:10001` and run the container as that identity.
- [x] Add a `HEALTHCHECK` calling `GET /health` (not `/readiness`).
- [x] Write a strict `.dockerignore`: `.git`, virtual environments, Python/tool caches, `tests/`, build outputs (`dist/`, `build/`, `*.egg-info`), and `openspec/changes/archive/`.

## 2. Local run/compose configuration

- [x] Add a local production run/compose configuration that binds the container to `0.0.0.0:8090` internally and publishes it to the host on `127.0.0.1` only.
- [x] Set `STRATEGY_ENGINE_MDS_BASE_URL` (and other `STRATEGY_ENGINE_*` env vars as needed) to point at the externally-running Market Data Service — no MDS/Runtime/ABI container defined here.

## 3. Verify

- [x] Build the image and confirm it succeeds.
- [x] Run the container and confirm the service process runs as UID/GID `10001`, not root.
- [x] Run the container with `docker run --read-only` and confirm it starts and serves `GET /health`.
- [x] Confirm `GET /health` responds `200`, and `GET /readiness` is reachable but is not what the Docker healthcheck targets.
- [x] Send `SIGTERM` to the container and confirm it stops gracefully without needing `SIGKILL`.
- [x] Stop, remove, and recreate the container from the same image with no volume mounted; confirm it starts clean.
- [x] Confirm the built image contains no `dist/`, `*.egg-info`, `__pycache__/`, `.pyc` files, `legacy_source`, or parity artifacts.
- [x] Run `make verify` and confirm it is still green.
