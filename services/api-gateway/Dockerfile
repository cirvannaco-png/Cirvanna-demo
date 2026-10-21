FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    CIRVANNA_AUDIT_DB=/data/audit.sqlite3

WORKDIR /app

COPY services/api-gateway/requirements.txt /app/services/api-gateway/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /app/services/api-gateway/requirements.txt

COPY services/api-gateway /app/services/api-gateway
COPY packages/identity-intelligence /app/packages/identity-intelligence
COPY packages/preferences /app/packages/preferences
COPY packages/fit-intelligence /app/packages/fit-intelligence

RUN useradd --system --uid 10001 --create-home cirvanna \
    && mkdir -p /data \
    && chown -R cirvanna:cirvanna /app /data

USER cirvanna
WORKDIR /app/services/api-gateway

VOLUME ["/data"]
EXPOSE 8080

CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
