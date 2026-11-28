ARG CUDA_BASE_IMAGE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
FROM ${CUDA_BASE_IMAGE}

ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PYTHONPATH=/app:/app/app \
    OMP_NUM_THREADS=4 \
    TMPDIR=/tmp

RUN apt-get update && apt-get install -y --no-install-recommends \
      python3.10 python3-pip ca-certificates \
    && rm -rf /var/lib/apt/lists/* \
    && python3.10 -m pip install --upgrade pip

WORKDIR /app
RUN python3.10 -m pip install --no-cache-dir \
      torch==2.6.0 \
      --index-url https://download.pytorch.org/whl/cu124

COPY requirements.txt /app/requirements.txt
RUN python3.10 -m pip install --no-cache-dir -r /app/requirements.txt

COPY app /app/app
COPY model.py /app/model.py
RUN mkdir -p /models/cvi-tryon /tmp \
    && chown -R 10001:10001 /app /models /tmp

USER 10001:10001
EXPOSE 8080
CMD ["python3.10", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080", "--workers", "1"]
