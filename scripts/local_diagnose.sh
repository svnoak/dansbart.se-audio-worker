#!/bin/sh
# Local, VPS-free check for the rms/zcr/onset_rate bug in
# neckenml.analyzer.audio_analyzer.AudioAnalyzer._extract_lightweight_features.
#
# Usage:
#   ./scripts/local_diagnose.sh /path/to/a/real/audio/file.mp3
#
# Run this from inside the dansbart-audio-worker directory.
# Needs Docker Desktop running. Builds the image once (slow, cached after
# that), then runs one lightweight container against your local edited
# neckenml-core/neckenml-analyzer source, skipping Postgres/Redis/Celery
# and skipping beat tracking/MusiCNN -- only the broken method runs.

set -e

if [ -z "$1" ]; then
  echo "Usage: $0 /path/to/audio/file.mp3"
  exit 1
fi

case "$1" in
  /*) AUDIO_PATH="$1" ;;
  *) AUDIO_PATH="$(cd "$(dirname "$1")" && pwd)/$(basename "$1")" ;;
esac

if [ ! -f "$AUDIO_PATH" ]; then
  echo "File not found: $AUDIO_PATH"
  exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
WORKER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
NECKENML_DIR="$(cd "$WORKER_DIR/../neckenml-analyzer" && pwd)"
IMAGE=dansbart-audio-worker-local

echo "== Step 1: build image (uses cache after first run) =="
docker build --platform linux/amd64 -t "$IMAGE" "$WORKER_DIR"

echo "== Step 2: find site-packages path inside the image =="
SITE_PACKAGES=$(docker run --rm --platform linux/amd64 "$IMAGE" find / -maxdepth 6 -type d -name neckenml 2>/dev/null | head -n 1 | xargs dirname)

if [ -z "$SITE_PACKAGES" ]; then
  echo "Could not find the neckenml install path automatically."
  exit 1
fi
echo "Found: $SITE_PACKAGES"

echo "== Step 3: run the diagnostic against your locally edited code =="
docker run --rm --platform linux/amd64 \
  -v "$NECKENML_DIR/packages/neckenml-core/src/neckenml/core:$SITE_PACKAGES/neckenml/core" \
  -v "$NECKENML_DIR/packages/neckenml-analyzer/src/neckenml/analyzer:$SITE_PACKAGES/neckenml/analyzer" \
  -v "$SCRIPT_DIR/diagnose_lightweight_features.py:/app/diagnose_lightweight_features.py" \
  -v "$AUDIO_PATH:/app/test_audio.mp3" \
  --user root \
  "$IMAGE" \
  python /app/diagnose_lightweight_features.py /app/test_audio.mp3
