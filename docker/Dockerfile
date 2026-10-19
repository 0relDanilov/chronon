# syntax=docker/dockerfile:1
# One Dockerfile, one image per target. `base` runs the API, state service,
# worker and instrument; `arc` (later) adds the ARC extra.
FROM python:3.12.15-slim AS base
COPY --from=ghcr.io/astral-sh/uv:0.13.1 /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PROJECT_ENVIRONMENT=/opt/venv \
    PATH=/opt/venv/bin:$PATH
WORKDIR /app
# Dependencies first, so code changes don't invalidate this layer.
COPY pyproject.toml uv.lock README.md ./
RUN uv sync --locked --no-install-project
COPY src ./src
RUN uv sync --locked
RUN useradd --uid 10001 --no-create-home chronon
USER 10001
EXPOSE 8000
CMD ["uvicorn", "chronon.api.app:app", "--host", "0.0.0.0", "--port", "8000"]
