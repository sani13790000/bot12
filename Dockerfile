# ================================================================
# Dockerfile - Galaxy Vast AI Trading Platform
# ================================================================
FROM python:3.11-slim

LABEL maintainer="Galaxy Vast Team"
LABEL description="Galaxy Vast AI Trading Platform"

# Environment
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

# System dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# Non-root user
RUN groupadd -r galaxyvast && useradd -r -g galaxyvast galaxyvast

WORKDIR /app

# Install Python dependencies from ROOT requirements.txt (not backend/tests/)
COPY requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# Copy source code
COPY backend/ /app/backend/

# Logs directory
RUN mkdir -p /app/logs && chown -R galaxyvast:galaxyvast /app

USER galaxyvast

EXPOSE 8000

CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
