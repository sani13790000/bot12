# ============================================================
# Dockerfile - Galaxy Vast AI Trading Platform
# P17-FIX-DF-1: multi-stage (builder + runtime)
# P17-FIX-DF-2: non-root USER galaxyvast
# P17-FIX-DF-3: PYTHONPATH combined in single ENV (no override bug)
# P17-FIX-DF-4: HEALTHCHECK on /health/live
# P17-FIX-DF-5: graceful shutdown --timeout-graceful-shutdown
# P17-FIX-DF-6: pinned python:3.11-slim (no :latest)
# P17-FIX-DF-7: gcc only in builder, not runtime
# ============================================================

# ── builder stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install --no-cache-dir --prefix=/install -r requirements.txt

# ── runtime stage ─────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

LABEL maintainer="Galaxy Vast Team"
LABEL description="Galaxy Vast AI Trading Platform — API"
LABEL version="3.0.0"
ARG GIT_SHA=unknown
LABEL org.opencontainers.image.revision="${GIT_SHA}"

# Runtime-only system deps (no gcc)
RUN apt-get update && apt-get install -y --no-install-recommends \
    libpq5 \
    curl \
    && rm -rf /var/lib/apt/lists/*

# P17-FIX-DF-3: single ENV instruction — second ENV would override PYTHONPATH
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PATH=/install/bin:$PATH \
    PYTHONPATH=/install/lib/python3.11/site-packages:/app

# Copy installed packages from builder
COPY --from=builder /install /install

# P17-FIX-DF-2: non-root user
RUN groupadd -r galaxyvast && useradd -r -g galaxyvast -d /app galaxyvast

WORKDIR /app
COPY backend/ /app/backend/

# Directories + ownership
RUN mkdir -p /app/logs /app/models \
    && chown -R galaxyvast:galaxyvast /app

USER galaxyvast

EXPOSE 8000

# P17-FIX-DF-4: healthcheck on /health/live (liveness, not readiness)
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 \
    CMD curl -f http://localhost:8000/health/live || exit 1

# P17-FIX-DF-5: graceful shutdown
CMD ["uvicorn", "backend.api.main:app", \
     "--host", "0.0.0.0", \
     "--port", "8000", \
     "--workers", "2", \
     "--timeout-graceful-shutdown", "30", \
     "--access-log"]
