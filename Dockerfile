# One image, three roles (ADR-026).
#
# api, worker-runtime and worker-authoring are the same code with different
# entrypoints, so they share an image. That is what keeps the split from being
# microservices: no service boundary, no network call between them, no separate
# dependency set. They talk through the job table in Postgres (ADR-017).
#
# The role is chosen by the `command` in docker-compose.yml, never by a build
# argument. A per-role image would mean three things to build, tag and keep in
# step on a machine somebody else has to run.

FROM python:3.12-slim AS base

# uv is copied from its own image rather than installed with pip: it pins the
# version and avoids a resolver run in every build.
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /app

# Dependencies first, in their own layer: they change far less often than source,
# so a code edit does not reinstall the world.
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

COPY src/ ./src/
RUN uv sync --frozen --no-dev

# The document volume mounts here. The directory has to exist in the image and
# be owned by the runtime user *before* the volume is attached: Docker copies
# the image's ownership onto a fresh named volume, and creates it root-owned if
# the path is absent. Without this the object store cannot create its incoming/
# directory on first use, and the failure appears at the first upload rather
# than at boot (ADR-019).
RUN mkdir -p /app/storage

# Nothing runs as root. The factory host is shared and long-lived.
RUN useradd --system --create-home --uid 10001 pdm \
    && chown -R pdm:pdm /app /opt/venv
USER pdm

# No default CMD on purpose. Every role must state which one it is in compose,
# so a misconfigured service fails immediately instead of silently starting the
# wrong process.
