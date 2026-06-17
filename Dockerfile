# =====================================================================
# Dockerfile اصلی - bot12 API
# =====================================================================
FROM python:3.13-slim

# متادیتا
LABEL maintainer="MT5 Trading Team"
LABEL description="bot12 - سیستم معامله‌گری حرفه‌ای MT5"

# تنظیم محیط
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PYTHONPATH=/app \
    PIP_NO_CACHE_DIR=1

# نصب وابستگی‌های سیستمی
RUN apt-get update && apt-get install -y \
    gcc \
    libpq-dev \
    curl \
    && rm -rf /var/lib/apt/lists/*

# ایجاد کاربر غیر root برای امنیت
RUN groupadd -r bot12 && useradd -r -g bot12 bot12

WORKDIR /app

# کپی و نصب وابستگی‌های Python
COPY backend/tests/requirements.txt /app/requirements.txt
RUN pip install --upgrade pip && pip install -r requirements.txt

# کپی سورس کد
COPY backend/ /app/backend/

# ایجاد دایرکتوری لاگ
RUN mkdir -p /app/logs && chown -R bot12:bot12 /app

# تغییر کاربر
USER bot12

# پورت
EXPOSE 8000

# دستور اجرا
CMD ["uvicorn", "backend.api.main:app", "--host", "0.0.0.0", "--port", "8000", "--workers", "2"]
