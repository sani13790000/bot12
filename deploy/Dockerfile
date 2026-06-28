# Dockerfile -- Bot12 EA Platform v1.0.0
# Multi-stage build | Non-root user | Pinned base | Healthcheck

# builder stage
FROM python:3.11.9-slim AS builder
WORKDIR /build
RUN apt-get update && apt-get install -y --no-install-recommends gcc libpq-dev && rm -rf /var/lib/apt/lists/*
COPY backend/requirements.txt .
RUN pip install --upgrade pip && pip install --no-cache-dir --prefix=/install -r requirements.txt

# runtime stage
FROM python:3.11.9-slim AS runtime
LABEL maintainer="Bot12 Technologies Ltd"
LABEL version="1.0.0"
ARG GIT_SHA=unknown
LABEL org.opencontainers.image.revision="${GIT_SHA}"
RUN apt-get update && apt-get install -y --no-install-recommends libpq5 curl && rm -rf /var/lib/apt/lists/*
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PATH=/install/bin:$PATH PYTHONPATH=/install/lib/python3.11/site-packages:/app
COPY --from=builder /install /install
RUN groupadd -r bot12 && useradd -r -g bot12 -d /app bot12
WORKDIR /app
COPY backend/ /app/backend/
RUN mkdir -p /app/logs /app/tmp && chown -R bot12:bot12 /app
USER bot12
EXPOSE 8000
HEALTHCHECK --interval=30s --timeout=10s --start-period=40s --retries=3 CMD curl -f http://localhost:8000/health/live || exit 1
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2", "--timeout-graceful-shutdown", "30", "--access-log"]
