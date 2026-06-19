# ============================================================
# Galaxy Vast Institutional Dashboard — Streamlit
# ============================================================
FROM python:3.11-slim

LABEL maintainer="Galaxy Vast Team"
LABEL description="Galaxy Vast Institutional Streamlit Dashboard"

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

RUN apt-get update && apt-get install -y \
    gcc \
    curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dashboard dependencies
RUN pip install --upgrade pip && pip install \
    streamlit==1.39.0 \
    plotly==5.24.1 \
    pandas==2.2.3 \
    numpy==1.26.4 \
    httpx==0.27.2 \
    scipy==1.14.1 \
    statsmodels==0.14.4 \
    kaleido==0.2.1

# Copy dashboard and institutional modules
COPY dashboard/ ./dashboard/
COPY backend/institutional/ ./backend/institutional/
COPY backend/__init__.py ./backend/__init__.py

# Create logs dir
RUN mkdir -p /app/logs

EXPOSE 8501

HEALTHCHECK --interval=30s --timeout=10s --start-period=15s --retries=3 \
    CMD curl -f http://localhost:8501/_stcore/health || exit 1

CMD ["streamlit", "run", "dashboard/app.py", \
     "--server.port=8501", \
     "--server.address=0.0.0.0", \
     "--server.headless=true", \
     "--browser.gatherUsageStats=false", \
     "--theme.base=dark", \
     "--theme.primaryColor=#FFD700", \
     "--theme.backgroundColor=#0E1117", \
     "--theme.secondaryBackgroundColor=#1E2329"]
