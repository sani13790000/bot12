# ============================================================
# Dockerfile — Galaxy Vast API
# ============================================================
FROM python:3.11-slim

LABEL maintainer="MT5 Trading Team"
LABEL description="Galaxy Vast AI Trading Bot — FastAPI + Institutional Modules"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

# System dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    build-essential \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Create non-root user
RUN groupadd -r bot12 && useradd -r -g bot12 bot12

WORKDIR /app

# Install Python dependencies
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy application
COPY backend/ /app/backend/
COPY mql5/ /app/mql5/

# Create directories
RUN mkdir -p /app/logs /app/models /app/data && chown -R bot12:bot12 /app

USER bot12

EXPOSE 8000

CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
