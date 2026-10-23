FROM ghcr.io/astral-sh/uv:0.8.11 AS uv

FROM python:3.11-slim AS build
COPY --from=uv /uv /bin/uv

ENV UV_COMPILE_BYTECODE=1 \
    UV_LINK_MODE=copy
WORKDIR /app

COPY pyproject.toml uv.lock README.md ./
COPY src ./src
COPY config ./config
RUN uv sync --locked --no-dev --no-editable

FROM python:3.11-slim AS runtime

ENV PATH="/app/.venv/bin:$PATH" \
    PYTHONUNBUFFERED=1
WORKDIR /app

RUN groupadd --system --gid 10001 bridge \
    && useradd --system --uid 10001 --gid bridge --home-dir /app bridge

COPY --from=build --chown=bridge:bridge /app/.venv /app/.venv
COPY --from=build --chown=bridge:bridge /app/config /app/config

USER bridge
EXPOSE 8000
CMD ["uvicorn", "bridge.api:app", "--host", "0.0.0.0", "--port", "8000"]
