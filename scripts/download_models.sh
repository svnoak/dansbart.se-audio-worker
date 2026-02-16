#!/usr/bin/env bash
# One-time setup: download ML models required by the audio worker into this repo's models/ directory.
# Run from audio worker root: ./scripts/download_models.sh
# When using the root dansbart repo's docker-compose, that repo mounts ./dansbart-audio-worker/models at /app/models.
#
# If you see "Invalid GraphDef" in the worker, the .pb file was likely corrupted or an HTML error
# page was saved. Delete models/*.pb and re-run this script (use -f to force re-download).
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
AUDIO_WORKER_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
MODELS_DIR="${AUDIO_WORKER_ROOT}/models"
mkdir -p "$MODELS_DIR"

# Optional: remove existing .pb files so we get a clean download (pass -f to enable)
if [ "${1:-}" = "-f" ]; then
  rm -f "$MODELS_DIR"/msd-musicnn-1.pb "$MODELS_DIR"/voice_instrumental-musicnn-msd-1.pb
  echo "Removed existing .pb files; re-downloading."
fi

echo "Downloading models to $MODELS_DIR ..."
# -f: fail on HTTP errors (4xx/5xx) so we don't save an error page as .pb
curl -f -L -o "$MODELS_DIR/msd-musicnn-1.pb" \
  https://essentia.upf.edu/models/feature-extractors/musicnn/msd-musicnn-1.pb
# Voice/instrumental model (classification-heads; graph has model/Softmax; README audio-event-recognition URL returns 404)
curl -f -L -o "$MODELS_DIR/voice_instrumental-musicnn-msd-1.pb" \
  https://essentia.upf.edu/models/classification-heads/voice_instrumental/voice_instrumental-msd-musicnn-1.pb

# Sanity check: msd-musicnn-1.pb is ~3.2 MB; voice_instrumental is ~82 KB
size_msd=$(stat -f%z "$MODELS_DIR/msd-musicnn-1.pb" 2>/dev/null || stat -c%s "$MODELS_DIR/msd-musicnn-1.pb" 2>/dev/null)
size_vocal=$(stat -f%z "$MODELS_DIR/voice_instrumental-musicnn-msd-1.pb" 2>/dev/null || stat -c%s "$MODELS_DIR/voice_instrumental-musicnn-msd-1.pb" 2>/dev/null)
if [ "$size_msd" -lt $((2 * 1024 * 1024)) ]; then
  echo "ERROR: msd-musicnn-1.pb is too small ($(( size_msd / 1024 )) KB). Expected ~3 MB. Delete and re-run with -f." >&2
  exit 1
fi
if [ "$size_vocal" -lt 50000 ]; then
  echo "ERROR: voice_instrumental-musicnn-msd-1.pb is too small ($(( size_vocal / 1024 )) KB). Expected ~82 KB. Delete and re-run with -f." >&2
  exit 1
fi
echo "Done ($(ls -lh "$MODELS_DIR"/*.pb 2>/dev/null | awk '{print $5}' | tr '\n' ' ')). Restart the audio worker (e.g. docker compose up --build)."
