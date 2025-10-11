FROM python:3.10-slim

WORKDIR /app

# Install system deps
RUN apt-get update && apt-get install -y ffmpeg git && rm -rf /var/lib/apt/lists/*

# Copy project
COPY . /app

# Install Python deps
RUN pip install --no-cache-dir fastapi uvicorn gTTS pydub

# (Optional) install your project requirements
RUN pip install --no-cache-dir -r requirements.txt || true

EXPOSE 8080
CMD ["uvicorn", "server:app", "--host", "0.0.0.0", "--port", "8080"]
