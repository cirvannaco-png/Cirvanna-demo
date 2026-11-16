FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1

WORKDIR /workspace
COPY services/appearance-intelligence-service/requirements.txt /workspace/requirements.txt
RUN python -m pip install --upgrade pip \
    && python -m pip install -r /workspace/requirements.txt

COPY packages/appearance_intelligence /workspace/packages/appearance_intelligence
COPY services/appearance-intelligence-service /workspace/services/appearance-intelligence-service
ENV PYTHONPATH=/workspace/packages:/workspace/services/appearance-intelligence-service

WORKDIR /workspace/services/appearance-intelligence-service
RUN useradd --system --uid 10023 --create-home appearance \
    && chown -R appearance:appearance /workspace
USER appearance

EXPOSE 8080
HEALTHCHECK --interval=30s --timeout=3s --start-period=10s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8080/health', timeout=2).read()"
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
