FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/marketplace-bff/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt

# Preserve the repository-relative layout expected by app/main.py and install
# the shared telemetry package used by both the BFF and Decision Gateway.
COPY services/marketplace-bff /app/services/marketplace-bff
COPY packages/http_observability /app/packages/http_observability
COPY apps/demo-web /app/apps/demo-web

WORKDIR /app/services/marketplace-bff
ENV PYTHONPATH=/app/services/marketplace-bff
ENV MARKETPLACE_HTML_PATH=/app/apps/demo-web/marketplace.html
ENV WARDROBE_HTML_PATH=/app/apps/demo-web/wardrobe.html
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
