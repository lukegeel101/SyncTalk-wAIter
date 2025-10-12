FROM python:3.10-slim

WORKDIR /app

# Install system deps
# Add build toolchain + portaudio headers + ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    portaudio19-dev \
    libasound2-dev \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*
# Copy project
COPY . /app

# Install Python deps
RUN pip install --no-cache-dir fastapi uvicorn gTTS pydub

# (Optional) install your project requirements
RUN pip install --no-cache-dir -r requirements.txt || true

EXPOSE 8080
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
