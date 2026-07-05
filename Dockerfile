# ────────────────────────────────────────────────────────────────────────────
# Stage 1: Build dependencies
# ────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS builder

WORKDIR /build

# Install build tools
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    git \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --upgrade pip \
 && pip install --no-cache-dir -r requirements.txt

# ────────────────────────────────────────────────────────────────────────────
# Stage 2: Runtime image
# ────────────────────────────────────────────────────────────────────────────
FROM python:3.11-slim AS runtime

WORKDIR /app

# Security: non-root user
RUN groupadd -r appuser && useradd -r -g appuser -d /app -s /sbin/nologin appuser

# Runtime system deps only
RUN apt-get update && apt-get install -y --no-install-recommends \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Copy installed packages from builder
COPY --from=builder /usr/local/lib/python3.11/site-packages /usr/local/lib/python3.11/site-packages
COPY --from=builder /usr/local/bin /usr/local/bin

# Copy application source
COPY backend/ ./backend/
COPY --chown=appuser:appuser . .

# Create necessary directories
RUN mkdir -p /app/models/xgboost /app/logs && \
    chown -R appuser:appuser /app

USER appuser

# Health check using the dedicated /health/live endpoint
HEALTHCHECK --interval=30s --timeout=10s --start-period=60s --retries=3 \
    CMD curl -sf http://localhost:8000/health/live || exit 1

EXPOSE 8000

# ARCH-R6-1 FIX: --workers 1 prevents KillSwitch race condition.
# With --workers 2, activating KillSwitch via one worker leaves the
# other worker still trading (50% chance orders go through).
# Use --workers 1 until KillSwitch state is migrated to Redis.
CMD ["uvicorn", "backend.api.main:app",
     "--host", "0.0.0.0",
     "--port", "8000",
     "--workers", "1",
     "--loop", "uvloop",
     "--http", "httptools",
     "--log-level", "info",
     "--access-log"]
