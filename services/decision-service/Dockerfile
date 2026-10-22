FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/decision-service/requirements.txt /tmp/requirements.txt
RUN pip install --no-cache-dir -r /tmp/requirements.txt
COPY packages/identity-intelligence /app/packages/identity-intelligence
COPY packages/preferences /app/packages/preferences
COPY packages/fit-intelligence /app/packages/fit-intelligence
COPY services/decision-service/app /app/services/decision-service/app
WORKDIR /app/services/decision-service
EXPOSE 8082
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8082}"]
