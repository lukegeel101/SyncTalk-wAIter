# CUDA 11.3 + dev toolchain (has nvcc)
FROM nvidia/cuda:11.3.1-devel-ubuntu20.04

ENV DEBIAN_FRONTEND=noninteractive
WORKDIR /app

# System deps (Python 3.8, GCC-10, audio/ffmpeg, build tools)
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3.8 python3.8-dev python3-distutils python3-pip \
    build-essential cmake git ffmpeg unzip pkg-config \
    gcc-10 g++-10 portaudio19-dev \
 && rm -rf /var/lib/apt/lists/*

# Make python/pip default to 3.8
RUN update-alternatives --install /usr/bin/python python /usr/bin/python3.8 1 \
 && update-alternatives --install /usr/bin/pip pip /usr/bin/pip3 1

# PyTorch (CUDA 11.3) – exact versions SyncTalk docs use
RUN pip install --no-cache-dir --upgrade pip \
 && pip install --no-cache-dir \
    torch==1.12.1+cu113 torchvision==0.13.1+cu113 torchaudio==0.12.1 \
    --extra-index-url https://download.pytorch.org/whl/cu113

# Core Python deps (pin to stable ABI with Py3.8/cu113)
RUN pip install --no-cache-dir \
    fastapi uvicorn gdown pydub ffmpeg-python \
    opencv-python-headless==4.10.0.84 \
    numpy==1.23.5 scipy==1.10.1 \
    trimesh==4.4.9 networkx ninja python-multipart

# Copy your project
COPY . /app

# Build local CUDA extensions with GCC-10 (critical!)
ENV CC=/usr/bin/gcc-10
ENV CXX=/usr/bin/g++-10
ENV MAX_JOBS=4
RUN pip install --no-cache-dir --no-build-isolation ./freqencoder ./shencoder ./gridencoder ./raymarching

# PyTorch3D wheel matching py38/cu113/pyt1121
RUN pip install --no-index --no-cache-dir pytorch3d \
  -f https://dl.fbaipublicfiles.com/pytorch3d/packaging/wheels/py38_cu113_pyt1121/download.html

# (Optional) bake data/model in – comment out if you prefer to mount at runtime
RUN mkdir -p /app/data /app/model \
 && gdown --fuzzy "https://drive.google.com/uc?id=18Q2H612CAReFxBd9kxr-i1dD8U1AUfsV" -O /app/data/May.zip \
 && unzip -o /app/data/May.zip -d /app/data && rm /app/data/May.zip \
 && gdown --fuzzy "https://drive.google.com/uc?id=1C2639qi9jvhRygYHwPZDGs8pun3po3W7" -O /app/model/trial_may.zip \
 && unzip -o /app/model/trial_may.zip -d /app/model && rm /app/model/trial_may.zip

# Serve the GPU worker FastAPI (gpu_worker.py must define /health and /render)
EXPOSE 8080
CMD ["uvicorn","gpu_worker:app","--host","0.0.0.0","--port","8080"]
