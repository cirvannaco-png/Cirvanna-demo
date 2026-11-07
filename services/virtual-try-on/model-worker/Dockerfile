# Build with --build-arg FASHN_VTON_GIT_REF=<verified-40-character-upstream-commit>.
# A missing/unpinned source revision deliberately fails the build.
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
ARG FASHN_VTON_GIT_REF
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FASHN_VTON_SOURCE_REF=${FASHN_VTON_GIT_REF} \
    FASHN_VTON_BUILT_SOURCE_REF=${FASHN_VTON_GIT_REF} \
    FASHN_VTON_WEIGHTS_DIR=/models/fashn-vton-1.5
RUN apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-venv git ca-certificates libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/virtual-try-on/model-worker/requirements.txt /app/requirements.txt
RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install -r /app/requirements.txt \
    && echo "$FASHN_VTON_GIT_REF" | grep -Eq '^[0-9a-f]{40}$' \
    && python3 -m pip install "git+https://github.com/fashn-AI/fashn-vton-1.5.git@$FASHN_VTON_GIT_REF"
COPY services/virtual-try-on/model-worker/app /app/app
COPY services/virtual-try-on/model-worker/scripts /app/scripts
RUN useradd --system --uid 10003 --create-home vton \
    && mkdir -p /models/fashn-vton-1.5 \
    && chown -R vton:vton /app /models
USER vton
EXPOSE 8081
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
