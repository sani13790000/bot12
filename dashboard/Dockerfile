FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir streamlit pandas plotly httpx

COPY dashboard/ ./dashboard/
COPY backend/institutional/ ./backend/institutional/

EXPOSE 8501

CMD ["streamlit", "run", "dashboard/app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.headless=true"]
