# Build only from the reviewed upstream source revision; no floating branch/tag is allowed.
ARG FASHN_VTON_GIT_REF=7c0f10af3f91ad4048fe9729c470a13ef905d25a
FROM nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
ARG FASHN_VTON_GIT_REF
ENV DEBIAN_FRONTEND=noninteractive \
    PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FASHN_VTON_SOURCE_REF=${FASHN_VTON_GIT_REF} \
    FASHN_VTON_BUILT_SOURCE_REF=${FASHN_VTON_GIT_REF} \
    FASHN_VTON_SOURCE_DIR=/opt/fashn-vton \
    FASHN_VTON_WEIGHTS_DIR=/models/fashn-vton-1.5 \
    HF_HOME=/models/hf-cache \
    HF_HUB_OFFLINE=1 \
    TRANSFORMERS_OFFLINE=1
RUN echo "$FASHN_VTON_GIT_REF" | grep -Fx "7c0f10af3f91ad4048fe9729c470a13ef905d25a" \
    && apt-get update && apt-get install -y --no-install-recommends python3 python3-pip python3-venv git ca-certificates libgl1 libglib2.0-0 \
    && rm -rf /var/lib/apt/lists/*
WORKDIR /app
COPY services/virtual-try-on/model-worker/requirements.txt /app/requirements.txt
RUN python3 -m pip install --upgrade pip \
    && python3 -m pip install -r /app/requirements.txt \
    && git clone https://github.com/fashn-AI/fashn-vton-1.5.git "$FASHN_VTON_SOURCE_DIR" \
    && git -C "$FASHN_VTON_SOURCE_DIR" checkout --detach "$FASHN_VTON_GIT_REF" \
    && test "$(git -C "$FASHN_VTON_SOURCE_DIR" rev-parse HEAD)" = "$FASHN_VTON_GIT_REF" \
    && python3 -m pip install -e "$FASHN_VTON_SOURCE_DIR"
COPY services/virtual-try-on/model-worker/app /app/app
COPY services/virtual-try-on/model-worker/scripts /app/scripts
RUN useradd --system --uid 10003 --create-home vton \
    && mkdir -p /models/fashn-vton-1.5 /models/hf-cache \
    && chown -R vton:vton /app /models /opt/fashn-vton
USER vton
EXPOSE 8081
CMD ["python3", "-m", "uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8081"]
