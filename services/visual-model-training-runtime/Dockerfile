ARG CUDA_BASE_IMAGE=nvidia/cuda:12.4.1-cudnn-runtime-ubuntu22.04
FROM $CUDA_BASE_IMAGE
ENV DEBIAN_FRONTEND=noninteractive PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 PYTHONDONTWRITEBYTECODE=1 HOME=/tmp/cvi-home PYTHONPATH=/workspace/source GIT_OPTIONAL_LOCKS=0
RUN apt-get update && apt-get install -y --no-install-recommends python3.10 python3-pip git ca-certificates && rm -rf /var/lib/apt/lists/* && python3.10 -m pip install --no-cache-dir --upgrade pip
COPY requirements.txt /tmp/requirements.txt
RUN python3.10 -m pip install --no-cache-dir --index-url https://download.pytorch.org/whl/cu124 --extra-index-url https://pypi.org/simple torch==2.6.0 torchvision==0.21.0 && python3.10 -m pip install --no-cache-dir -r /tmp/requirements.txt && python3.10 -c 'import torch,torchvision,numpy,PIL,trimesh,networkx,cryptography; assert torch.version.cuda=="12.4"; print(torch.__version__,torchvision.__version__,torch.version.cuda)'
RUN useradd --uid 10001 --create-home --shell /usr/sbin/nologin cvi && mkdir -p /workspace/source /data /output && chown -R 10001:10001 /workspace /output /home/cvi && chmod 0755 /workspace /data
COPY entrypoint.sh /usr/local/bin/cvi-entrypoint
RUN chmod 0555 /usr/local/bin/cvi-entrypoint
WORKDIR /workspace/source
USER 10001:10001
ENTRYPOINT ["/usr/local/bin/cvi-entrypoint"]
CMD ["python3.10","--version"]
