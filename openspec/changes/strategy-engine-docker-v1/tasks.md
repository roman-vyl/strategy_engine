## 1. Build the image

- [ ] Write a production `Dockerfile`: Python 3.12 base, install the package, run the existing `strategy-engine` console entrypoint directly as PID1 (no shell/supervisor wrapper).
- [ ] Set `PYTHONDONTWRITEBYTECODE=1` and unbuffered stdout/stderr in the image.
- [ ] Create a non-root user/group `10001:10001` and run the container as that identity.
- [ ] Add a `HEALTHCHECK` calling `GET /health` (not `/readiness`).
- [ ] Write a strict `.dockerignore`: `.git`, virtual environments, Python/tool caches, `tests/`, build outputs (`dist/`, `build/`, `*.egg-info`), and `openspec/changes/archive/`.

## 2. Local run/compose configuration

- [ ] Add a local production run/compose configuration that binds the container to `0.0.0.0:8090` internally and publishes it to the host on `127.0.0.1` only.
- [ ] Set `STRATEGY_ENGINE_MDS_BASE_URL` (and other `STRATEGY_ENGINE_*` env vars as needed) to point at the externally-running Market Data Service — no MDS/Runtime/ABI container defined here.

## 3. Verify

- [ ] Build the image and confirm it succeeds.
- [ ] Run the container and confirm the service process runs as UID/GID `10001`, not root.
- [ ] Run the container with `docker run --read-only` and confirm it starts and serves `GET /health`.
- [ ] Confirm `GET /health` responds `200`, and `GET /readiness` is reachable but is not what the Docker healthcheck targets.
- [ ] Send `SIGTERM` to the container and confirm it stops gracefully without needing `SIGKILL`.
- [ ] Stop, remove, and recreate the container from the same image with no volume mounted; confirm it starts clean.
- [ ] Confirm the built image contains no `dist/`, `*.egg-info`, `__pycache__/`, `.pyc` files, `legacy_source`, or parity artifacts.
- [ ] Run `make verify` and confirm it is still green.
