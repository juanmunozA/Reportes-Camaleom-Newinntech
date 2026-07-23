FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEADLESS=true

RUN apt-get update && apt-get install -y --no-install-recommends \
    chromium \
    chromium-driver \
    fonts-liberation \
    libnss3 \
    libatk-bridge2.0-0 \
    libgtk-3-0 \
    libasound2 \
    && rm -rf /var/lib/apt/lists/*

ENV CHROME_BIN=/usr/bin/chromium \
    CHROMEDRIVER_PATH=/usr/bin/chromedriver

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY camaleom_azure_reporte_app ./camaleom_azure_reporte_app

RUN mkdir -p /app/descargas_reportes /app/salidas_reportes

EXPOSE 8000

CMD ["sh", "-c", "uvicorn camaleom_azure_reporte_app.web.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
