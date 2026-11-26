FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/workspace/packages
WORKDIR /workspace
COPY services/wardrobe-service/requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt
COPY packages /workspace/packages
COPY services/wardrobe-service/app /workspace/services/wardrobe-service/app
COPY services/wardrobe-service/migrations /workspace/services/wardrobe-service/migrations
WORKDIR /workspace/services/wardrobe-service
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
