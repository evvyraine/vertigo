# syntax=docker/dockerfile:1
FROM ghcr.io/astral-sh/uv:python3.12-bookworm-slim AS runtime

WORKDIR /app

# Install the app with its locked dependencies. `uv sync` builds the project
# itself, so the sources and README must be present before it runs.
COPY pyproject.toml uv.lock README.md LICENSE ./
COPY src ./src
COPY .streamlit ./.streamlit
RUN uv sync --frozen --no-dev

RUN useradd --create-home --uid 1000 vertigo \
    && mkdir -p /data \
    && chown -R vertigo:vertigo /app /data

ENV PATH="/app/.venv/bin:$PATH" \
    VERTIGO_HOME=/data \
    PYTHONUNBUFFERED=1

USER vertigo
VOLUME ["/data"]
EXPOSE 8501

# Bind to all interfaces so the container is reachable through its port mapping;
# put a TLS reverse proxy in front of it for anything internet-facing.
CMD ["vertigo", "--server.address", "0.0.0.0", "--server.port", "8501", "--server.headless", "true"]
