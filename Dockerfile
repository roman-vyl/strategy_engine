# Base image: Docker Hub's official python:3.12-slim (Debian), pinned by
# immutable multi-arch index digest so linux/amd64 and linux/arm64 builds are
# reproducible. Bump the digest deliberately when taking a new base image.
#
# Dependencies: runtime dependencies are installed from uv.lock (the single
# source of truth for exact versions), exported at build time to a
# hash-pinned requirements file and installed with `pip --require-hashes`
# from public PyPI. The project wheel itself is then installed with
# --no-deps, so nothing is resolved from pyproject.toml's version ranges.

# Builder: produce an installable wheel from pyproject.toml, and export the
# locked runtime dependency set (no dev extras, no project) from uv.lock.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS builder

COPY --from=ghcr.io/astral-sh/uv:0.12.0@sha256:606e70c71c852d03f611b1e56a195d08648507018a7057fab82c4974c4eae105 /uv /usr/local/bin/uv

WORKDIR /build

COPY pyproject.toml uv.lock LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir --no-compile build \
    && python3 -m build --wheel --outdir /dist \
    && uv export --frozen --no-dev --no-emit-project --format requirements-txt \
        -o /dist/requirements.lock.txt

# Runtime: only the installed package and its runtime dependencies.
# No repository source tree, no build tooling, no uv binary, no uv.lock.
FROM python:3.12-slim@sha256:f77ac9e44ae96ef2c90b8053ea08c31f8be030f824196b0ae4db6d462c84e51f AS runtime

ENV STRATEGY_ENGINE_HTTP_HOST=0.0.0.0 \
    STRATEGY_ENGINE_HTTP_PORT=8090 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# Create the runtime identity by appending directly to /etc/passwd and
# /etc/group (fixed UID/GID 10001, no home, no login shell).
RUN echo 'strategy-engine:x:10001:10001::/nonexistent:/sbin/nologin' >> /etc/passwd \
    && echo 'strategy-engine:x:10001:' >> /etc/group

COPY --from=builder /dist/requirements.lock.txt /tmp/requirements.lock.txt
COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir --no-compile --require-hashes -r /tmp/requirements.lock.txt \
    && pip install --no-cache-dir --no-compile --no-deps /tmp/*.whl \
    && rm -f /tmp/requirements.lock.txt \
    && rm -rf /tmp/*.whl \
    && find / -xdev \( -name '__pycache__' -o -name '*.pyc' -o -name '*.pyo' \) -exec rm -rf {} + 2>/dev/null || true

USER 10001:10001

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=2)"]

ENTRYPOINT ["strategy-engine"]
