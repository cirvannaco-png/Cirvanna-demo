FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1
WORKDIR /app
COPY services/asset-service/requirements.txt /app/requirements.txt
RUN python -m pip install --upgrade pip && python -m pip install -r /app/requirements.txt
COPY services/asset-service/app /app/app
RUN useradd --system --uid 10004 --create-home asset && chown -R asset:asset /app
USER asset
EXPOSE 8082
CMD ["sh","-c","uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8082}"]
