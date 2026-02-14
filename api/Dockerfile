FROM python:3.12

ENV PYTHONUNBUFFERED=1

# Install uv
COPY --from=ghcr.io/astral-sh/uv:0.9.26 /uv /uvx /bin/

ENV UV_COMPILE_BYTECODE=1
ENV UV_LINK_MODE=copy

WORKDIR /app/

ENV PATH="/app/.venv/bin:$PATH"

# Install dependencies (layer cache)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    --mount=type=bind,source=api/pyproject.toml,target=api/pyproject.toml \
    uv sync --frozen --no-install-workspace --package cogmem-cloud

# Copy API source
COPY ./api/scripts /app/api/scripts
COPY ./api/pyproject.toml ./api/alembic.ini /app/api/
COPY ./api/app /app/api/app
COPY ./api/kos_extensions /app/api/kos_extensions

# Final sync (installs the workspace package)
RUN --mount=type=cache,target=/root/.cache/uv \
    --mount=type=bind,source=uv.lock,target=uv.lock \
    --mount=type=bind,source=pyproject.toml,target=pyproject.toml \
    uv sync --frozen --package cogmem-cloud

WORKDIR /app/api/

CMD ["fastapi", "run", "--workers", "4", "app/main.py"]
