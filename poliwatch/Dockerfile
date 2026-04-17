FROM python:3.12-slim

WORKDIR /app

# Install uv
COPY --from=ghcr.io/astral-sh/uv:latest /uv /usr/local/bin/uv

# Install dependencies first (layer cache)
COPY pyproject.toml .
RUN uv pip install --system --no-cache .

# Copy source
COPY poliwatch/ poliwatch/
COPY alembic/ alembic/
COPY alembic.ini .

# Create data directory
RUN mkdir -p data

EXPOSE 8000 8501

CMD ["python", "-m", "poliwatch.cli", "serve"]
