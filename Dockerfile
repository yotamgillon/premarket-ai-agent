# syntax=docker/dockerfile:1.7

# ---------- build stage: resolve and install dependencies with uv ----------
FROM ghcr.io/astral-sh/uv:0.13.0 AS uv

FROM python:3.12-slim AS builder
COPY --from=uv /uv /usr/local/bin/uv
ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy \
    UV_PYTHON_DOWNLOADS=never
WORKDIR /app

# Dependencies first: this layer is cached until pyproject.toml / uv.lock change,
# so editing source code doesn't re-download every package.
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-install-project

COPY README.md ./
COPY src ./src
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --locked --no-dev --no-editable

# ---------- runtime stage: just Python + the virtualenv, no build tools ----------
FROM python:3.12-slim AS runtime

RUN groupadd --gid 10001 app && useradd --uid 10001 --gid app --create-home app
WORKDIR /app
COPY --from=builder --chown=app:app /app/.venv /app/.venv

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    REPORTS_DIR=/app/reports
RUN mkdir -p /app/reports && chown app:app /app/reports

USER app
ENTRYPOINT ["premarket-agent"]
