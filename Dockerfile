# Base image note: this build uses Microsoft's Python 3.12 base
# (mcr.microsoft.com/azurelinux/base/python:3.12) instead of Docker Hub's
# python:3.12-slim. In the sandbox this Dockerfile was authored and
# smoke-tested in, Docker Hub and AWS ECR blob downloads are rejected
# because they redirect to *.cloudfront.net, which that sandbox's egress
# policy blocks; Microsoft Container Registry is not affected. Swap the
# FROM lines below back to python:3.12-slim if your build/deploy
# environment has full Docker Hub access - no other Dockerfile change is
# required (both images ship pip and a real Python 3.12).

# Builder: produce an installable wheel from pyproject.toml only.
# uv.lock is intentionally not used here - it pins environment-specific
# internal registry URLs that do not apply inside the Docker build.
FROM mcr.microsoft.com/azurelinux/base/python:3.12 AS builder

WORKDIR /build

COPY pyproject.toml LICENSE ./
COPY src ./src

RUN pip install --no-cache-dir --no-compile build \
    && python3 -m build --wheel --outdir /dist

# Runtime: only the installed package and its runtime dependencies.
# No repository source tree, no build tooling, no uv.lock.
FROM mcr.microsoft.com/azurelinux/base/python:3.12 AS runtime

ENV STRATEGY_ENGINE_HTTP_HOST=0.0.0.0 \
    STRATEGY_ENGINE_HTTP_PORT=8090 \
    STRATEGY_ENGINE_MDS_BASE_URL=http://host.docker.internal:8080 \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

# No useradd/groupadd on this minimal base - create the runtime identity
# by appending directly to /etc/passwd and /etc/group.
RUN echo 'strategy-engine:x:10001:10001::/nonexistent:/sbin/nologin' >> /etc/passwd \
    && echo 'strategy-engine:x:10001:' >> /etc/group

COPY --from=builder /dist/*.whl /tmp/
RUN pip install --no-cache-dir --no-compile /tmp/*.whl \
    && rm -rf /tmp/*.whl \
    && find / -xdev \( -name '__pycache__' -o -name '*.pyc' -o -name '*.pyo' \) -exec rm -rf {} + 2>/dev/null || true

USER 10001:10001

EXPOSE 8090

HEALTHCHECK --interval=30s --timeout=3s --start-period=5s --retries=3 \
    CMD ["python3", "-c", "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8090/health', timeout=2)"]

ENTRYPOINT ["strategy-engine"]
