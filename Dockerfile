# syntax=docker/dockerfile:1.6
# ATLAS backend — multi-stage build for small, reproducible runtime image.

# ─── Stage 1: builder ─────────────────────────────────────────────────────
FROM python:3.12-slim AS builder

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
        build-essential \
        libpq-dev \
        gcc \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt ./
RUN pip install --prefix=/install -r requirements.txt

# ─── Stage 2: runtime ────────────────────────────────────────────────────
FROM python:3.12-slim AS runtime

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PATH="/usr/local/bin:$PATH" \
    PORT=8010

RUN apt-get update && apt-get install -y --no-install-recommends \
        libpq5 \
        curl \
    && rm -rf /var/lib/apt/lists/* \
    && useradd --create-home --shell /bin/bash --uid 10001 atlas

COPY --from=builder /install /usr/local

WORKDIR /app
COPY backend ./backend
COPY contracts ./contracts
COPY alembic ./alembic
COPY alembic.ini ./alembic.ini

RUN chown -R atlas:atlas /app
USER atlas

EXPOSE 8010

HEALTHCHECK --interval=30s --timeout=5s --start-period=20s --retries=3 \
    CMD curl -fsS http://localhost:8010/health || exit 1

CMD ["uvicorn", "backend.main:app", "--host", "0.0.0.0", "--port", "8010"]
