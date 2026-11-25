FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/workspace/packages
WORKDIR /workspace
COPY services/cultural-identity-service/requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt
COPY packages/identity-intelligence /workspace/packages/identity-intelligence
COPY services/cultural-identity-service/app /workspace/services/cultural-identity-service/app
COPY services/cultural-identity-service/migrations /workspace/services/cultural-identity-service/migrations
WORKDIR /workspace/services/cultural-identity-service
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
