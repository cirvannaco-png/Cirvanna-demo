FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 PYTHONPATH=/workspace/services/xari
WORKDIR /workspace
COPY services/xari/requirements.txt /workspace/requirements.txt
RUN pip install --no-cache-dir -r /workspace/requirements.txt
COPY services/xari/xari /workspace/services/xari/xari
COPY services/xari/app /workspace/services/xari/app
WORKDIR /workspace/services/xari
EXPOSE 8080
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8080}"]
