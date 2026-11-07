FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    HF_HUB_DISABLE_TELEMETRY=1 \
    HF_HOME=/home/app/.cache/huggingface \
    CLICK_IT_FACE_DETECTOR_MODEL_PATH=/opt/cirvanna-models/blaze_face_full_range.tflite \
    CLICK_IT_FACE_DETECTOR_MODEL_SHA256=3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b

WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
      libgl1 libglib2.0-0 libgomp1 libegl1 libgles2 && \
    rm -rf /var/lib/apt/lists/* && \
    groupadd --system app && \
    useradd --system --gid app --create-home --home-dir /home/app app && \
    mkdir -p /home/app/.cache/huggingface && \
    chown -R app:app /home/app

COPY requirements.txt ./requirements.txt
RUN python -m pip install --upgrade pip && \
    python -m pip install -r requirements.txt

# Pin the official Google MediaPipe BlazeFace full-range model by immutable
# versioned URL, exact byte count and SHA-256. Do not use a floating "latest" URL.
RUN mkdir -p /opt/cirvanna-models && python - <<'PY'
import hashlib
import urllib.request
from pathlib import Path

url = "https://storage.googleapis.com/mediapipe-models/face_detector/blaze_face_full_range/float16/1/blaze_face_full_range.tflite"
expected_sha256 = "3698b18f063835bc609069ef052228fbe86d9c9a6dc8dcb7c7c2d69aed2b181b"
expected_size = 1083786
request = urllib.request.Request(url, headers={"User-Agent": "Cirvanna-Vision-Model-Provisioner/1.0"})
with urllib.request.urlopen(request, timeout=60) as response:
    payload = response.read(expected_size + 1)
if len(payload) != expected_size:
    raise SystemExit(f"Unexpected BlazeFace model size: {len(payload)}")
actual_sha256 = hashlib.sha256(payload).hexdigest()
if actual_sha256 != expected_sha256:
    raise SystemExit(f"BlazeFace model checksum mismatch: {actual_sha256}")
Path("/opt/cirvanna-models/blaze_face_full_range.tflite").write_bytes(payload)
PY
RUN chown -R app:app /opt/cirvanna-models

COPY app ./app
# Build-time smoke test loads the real pinned MediaPipe model and performs
# one inference on a synthetic no-face image. This is not a recall benchmark.
RUN python - <<'PY'
from PIL import Image
from app.click_it_privacy import _face_detector, anonymize_click_it_image, detector_configuration

assert detector_configuration() == (True, "configured")
image = Image.new("RGB", (256, 256), (0, 0, 0))
masked, count = anonymize_click_it_image(image)
assert count == 0
masked.close()
image.close()
_face_detector().close()
PY
USER app
EXPOSE 8000

HEALTHCHECK --interval=30s --timeout=3s --start-period=60s --retries=3 \
  CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/health', timeout=2).read()"

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
