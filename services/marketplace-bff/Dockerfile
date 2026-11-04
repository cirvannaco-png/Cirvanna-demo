FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/marketplace-bff/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY services/marketplace-bff/app /app/app
COPY apps/demo-web/marketplace.html /app/marketplace.html
COPY apps/demo-web/brand-portal.html /app/brand-portal.html
COPY apps/demo-web/founder-console.html /app/founder-console.html
COPY apps/demo-web/assets /app/assets
ENV MARKETPLACE_HTML_PATH=/app/marketplace.html
ENV BRAND_PORTAL_HTML_PATH=/app/brand-portal.html
ENV FOUNDER_CONSOLE_HTML_PATH=/app/founder-console.html
ENV MARKETPLACE_ASSETS_DIR=/app/assets
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
