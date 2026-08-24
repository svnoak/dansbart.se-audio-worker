# ====================================================
# DANSBART AUDIO WORKER DOCKERFILE
# AGPL-3.0 Licensed - Heavy ML models for audio analysis
# ====================================================

FROM python:3.10-slim

LABEL org.opencontainers.image.source="https://github.com/svnoak/dansbart.se-audio-worker"
LABEL org.opencontainers.image.description="Dansbart Audio Worker - AGPL-3.0"
LABEL org.opencontainers.image.licenses="AGPL-3.0"

# 1. Install System Dependencies for Audio Processing & ML
RUN apt-get update && apt-get install -y \
    build-essential \
    ca-certificates \
    curl \
    libsndfile1 \
    ffmpeg \
    g++ \
    gcc \
    git \
    postgresql-client \
    && rm -rf /var/lib/apt/lists/*

# 2. Set work directory
WORKDIR /app

# 3. Environment Config for CPU-Only ML
ENV CUDA_VISIBLE_DEVICES="-1"
ENV TF_CPP_MIN_LOG_LEVEL="2"

# 4. Install Python Dependencies
RUN pip install --no-cache-dir --upgrade pip

# Install build dependencies first (needed for madmom compilation)
RUN pip install --no-cache-dir numpy Cython

# Install requirements
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt

# 5. Create non-root user for running Celery
RUN useradd -m -u 1000 celeryuser && \
    chown -R celeryuser:celeryuser /app

# 6. Copy Application Code
COPY --chown=celeryuser:celeryuser app/ ./app/

# 7. Create temp directory for audio downloads
RUN mkdir -p /app/temp_audio && chown celeryuser:celeryuser /app/temp_audio

# 8. Create models directory and download MusiCNN models (baked into image)
RUN mkdir -p /app/models
COPY scripts/ ./scripts/
RUN bash ./scripts/download_models.sh && chown -R celeryuser:celeryuser /app/models

# Switch to non-root user
USER celeryuser

# Default: Run Celery worker for audio tasks
CMD ["celery", "-A", "app.core.celery_app", "worker", "--loglevel=info", "--pool=solo", "-Q", "audio"]
