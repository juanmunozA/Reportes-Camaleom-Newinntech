FROM python:3.12-slim

ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    HEADLESS=true

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY camaleom_azure_reporte_app ./camaleom_azure_reporte_app

RUN mkdir -p /app/descargas_reportes /app/salidas_reportes

EXPOSE 8000

CMD ["sh", "-c", "uvicorn camaleom_azure_reporte_app.web.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
