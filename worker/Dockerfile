# Magora Listen inference worker.
# ffmpeg + libsndfile let librosa decode whatever the phone uploads (WAV, or
# WebM/Opus from MediaRecorder).
FROM python:3.11-slim

ENV PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
      ffmpeg \
      libsndfile1 \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY inference_worker.py .

CMD ["python", "inference_worker.py"]
