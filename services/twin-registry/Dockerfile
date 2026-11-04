FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY services/twin-registry/requirements.txt ./requirements.txt
RUN pip install --no-cache-dir -r requirements.txt
COPY services/twin-registry/app ./app
RUN useradd --create-home --uid 10001 appuser
USER appuser
EXPOSE 8096
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8096"]
