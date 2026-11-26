FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/workspace/packages
WORKDIR /workspace
COPY services/npl-service/requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt
COPY packages/preferences /workspace/packages/preferences
COPY services/npl-service/app /workspace/services/npl-service/app
COPY services/npl-service/migrations /workspace/services/npl-service/migrations
WORKDIR /workspace/services/npl-service
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
