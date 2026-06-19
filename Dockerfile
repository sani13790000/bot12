# ============================================================
# Dockerfile - Galaxy Vast AI Trading Platform
# Multi-stage build: smaller image, non-root user, healthcheck
# ============================================================

# ---- builder stage ----
FROM python:3.11-slim AS builder

WORKDIR /build

# System build deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ---- runtime stage ----
FROM python:3.11-slim AS runtime

LABEL maintainer="Galaxy Vast Team"
LABEL description="Galaxy Vast AI Trading Platform"
LABEL version="2.0.0"

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1 \
    PATH=/install/bin:$PATH \
    PYTHONPATH=/install/lib/python3.11/site-packages:/app

# Copy installed packages from builder
COPY --from=builder /install /install

# Non-root user
RUN groupadd -r galaxyvast && useradd -r -g galaxyvast -d /app galaxyvast

WORKDIR /app

# Copy source
COPY backend/ /app/backend/

# Logs directory
RUN mkdir -p /app/logs /app/models && chown -R galaxyvast:galaxyvast /app

USER galaxyvast

EXPOSE 8000

# Graceful shutdown with --timeout
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health || exit 1

CMD ["uvicorn", "backend.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--timeout-graceful-shutdown", "30", \
     "--access-log"]
