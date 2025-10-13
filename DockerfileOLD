FROM python:3.10-slim
WORKDIR /app

# System deps for PyAudio + ffmpeg
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential portaudio19-dev libasound2-dev ffmpeg unzip\
 && rm -rf /var/lib/apt/lists/*

COPY requirements_server.txt /app/
ENV PIP_NO_CACHE_DIR=1
RUN pip install --no-cache-dir -r requirements_server.txt

COPY . /app
EXPOSE 8080
CMD ["uvicorn","server:app","--host","0.0.0.0","--port","8080"]
