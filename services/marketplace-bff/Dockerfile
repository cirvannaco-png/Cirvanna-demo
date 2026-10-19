FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/marketplace-bff/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY services/marketplace-bff/app /app/app
COPY apps/demo-web/marketplace.html /app/marketplace.html
ENV MARKETPLACE_HTML_PATH=/app/marketplace.html
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
