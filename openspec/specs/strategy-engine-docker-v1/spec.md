# strategy-engine-docker-v1 Specification

## Purpose
Define the production Docker runtime for Strategy Engine — image, process, network, and filesystem contract — without changing application or HTTP semantics. Market Data Service remains an external dependency; no other service is containerized by this capability.
## Requirements
### Requirement: Python 3.12 production image

The production image SHALL be built on a Python 3.12 base, matching the package's `requires-python` constraint.

#### Scenario: Inspect the production image runtime

- **WHEN** the production image is built
- **THEN** its Python runtime SHALL be version 3.12.

### Requirement: Direct PID1 entrypoint

The container SHALL run the existing `strategy-engine` console entrypoint directly as PID1. The image SHALL NOT wrap it in a shell, init system, or process supervisor.

#### Scenario: Start the container

- **WHEN** the container starts
- **THEN** PID1 SHALL be the `strategy-engine` entrypoint process
- **AND** no shell or supervisor process SHALL sit between the container runtime and PID1.

### Requirement: Container HTTP bind

Inside the container, the service SHALL bind HTTP to `0.0.0.0:8090`.

#### Scenario: Inspect the container listening address

- **WHEN** the container is running
- **THEN** the service SHALL listen on `0.0.0.0:8090` inside the container network namespace.

### Requirement: External Market Data Service dependency

Market Data Service SHALL remain an external HTTP dependency reached through `STRATEGY_ENGINE_MDS_BASE_URL`. This capability SHALL NOT define a container, compose service, or image for Market Data Service, Runtime, or ABI.

#### Scenario: Configure the MDS endpoint

- **WHEN** the container starts
- **THEN** it SHALL read `STRATEGY_ENGINE_MDS_BASE_URL` to reach Market Data Service over HTTP
- **AND** no MDS, Runtime, or ABI container SHALL be defined in this repository.

### Requirement: Non-root runtime identity

The container SHALL run the service process as a non-root user with UID `10001` and GID `10001`.

#### Scenario: Inspect the running process identity

- **WHEN** the container is running
- **THEN** the service process SHALL run as UID `10001` and GID `10001`, not as root.

### Requirement: Read-only root filesystem support

The image SHALL start and serve requests successfully when run with a read-only root filesystem (`docker run --read-only`), without requiring an application-managed writable path.

#### Scenario: Run with a read-only root filesystem

- **WHEN** the container is started with a read-only root filesystem
- **THEN** the service SHALL start successfully
- **AND** SHALL serve `/health` without requiring any writable path.

### Requirement: No persistent state

The service SHALL NOT require a persistent volume. Restarting or recreating the container SHALL NOT depend on any prior container's filesystem state.

#### Scenario: Recreate the container

- **WHEN** the container is stopped, removed, and recreated from the same image
- **THEN** the service SHALL start successfully with no volume mounted
- **AND** SHALL depend on no state left behind by the previous container.

### Requirement: Runtime environment flags

The image SHALL set `PYTHONDONTWRITEBYTECODE=1` and run Python with unbuffered stdout/stderr.

#### Scenario: Inspect container output and bytecode behavior

- **WHEN** the container runs
- **THEN** it SHALL NOT write `.pyc` files during normal operation
- **AND** stdout/stderr SHALL be unbuffered.

### Requirement: Liveness-based Docker healthcheck

The image's Docker `HEALTHCHECK` SHALL call `GET /health`. It SHALL NOT call `/readiness`.

#### Scenario: Inspect the configured healthcheck

- **WHEN** the image's `HEALTHCHECK` is inspected
- **THEN** it SHALL target `GET /health`
- **AND** SHALL NOT target `/readiness`.

#### Scenario: Readiness remains reachable but unused by Docker

- **WHEN** the container is running
- **THEN** `GET /readiness` SHALL remain reachable over HTTP
- **AND** SHALL NOT be the endpoint Docker uses to determine container health.

### Requirement: Graceful shutdown

The container SHALL stop gracefully on `SIGTERM` and `SIGINT`, allowing the entrypoint's uvicorn process to shut down in place as PID1.

#### Scenario: Stop the container

- **WHEN** the container receives `SIGTERM`
- **THEN** PID1 SHALL receive that signal directly
- **AND** the service SHALL shut down without requiring `SIGKILL`.

### Requirement: Localhost-only host publishing

The local production compose/run configuration SHALL publish the container's HTTP port to the host bound to `127.0.0.1` only, not to all host interfaces.

#### Scenario: Inspect local host port publishing

- **WHEN** the local production run/compose configuration publishes the container's HTTP port
- **THEN** it SHALL bind that published port to `127.0.0.1` on the host
- **AND** SHALL NOT bind it to `0.0.0.0` or another external host interface.

### Requirement: Clean build context

`.dockerignore` SHALL exclude `.git`, virtual environments, Python/tool caches, `tests/`, build outputs, and archive artifacts from the build context. The built image SHALL contain no source-tree build garbage (`dist/`, `*.egg-info`, `__pycache__/`, `.pyc` files) and no legacy or parity artifacts.

#### Scenario: Inspect the build context and built image

- **WHEN** the production image is built
- **THEN** its build context SHALL exclude `.git`, virtual environments, caches, `tests/`, build outputs, and archive artifacts
- **AND** the built image SHALL contain no generated package artifacts, `legacy_source`, or parity artifacts.

