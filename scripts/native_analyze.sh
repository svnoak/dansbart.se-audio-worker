#!/bin/sh
# Local, VPS-free full audio analysis for the ml-trainer tool.
#
# Runs the real AudioAnalyzer (needs Essentia/linux-amd64, via Docker)
# against every MP3 in a folder -- the same folder
# ml-trainer/tuner/download_audio.py downloads into -- and writes one
# JSON artifacts file per track. This only extracts; it never touches
# any database.
#
# Usage:
#   ./scripts/native_analyze.sh /path/to/audio_cache /path/to/native_analysis_out
#
# After this finishes, import the results into the trainer's local
# SQLite from ml-trainer (no Docker needed for that step):
#   .venv/bin/python -m tuner.import_native_analysis /path/to/native_analysis_out
#
# Run this from inside the dansbart-audio-worker directory. Needs
# Docker Desktop running. Builds the image once (slow, cached after
# that), against your locally edited neckenml-core/neckenml-analyzer
# source -- same pattern as local_diagnose.sh.

set -e

if [ -z "$1" ] || [ -z "$2" ]; then
  echo "Usage: $0 /path/to/audio_cache /path/to/native_analysis_out"
  exit 1
fi

case "$1" in
  /*) INPUT_DIR="$1" ;;
  *) INPUT_DIR="$(cd "$1" && pwd)" ;;
esac

mkdir -p "$2"
case "$2" in
  /*) OUTPUT_DIR="$2" ;;
  *) OUTPUT_DIR="$(cd "$2" && pwd)" ;;
esac

if [ ! -d "$INPUT_DIR" ]; then
  echo "Input directory not found: $INPUT_DIR"
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

echo "== Step 3: analyze every MP3 in $INPUT_DIR =="
docker run --rm --platform linux/amd64 \
  -v "$NECKENML_DIR/packages/neckenml-core/src/neckenml/core:$SITE_PACKAGES/neckenml/core" \
  -v "$NECKENML_DIR/packages/neckenml-analyzer/src/neckenml/analyzer:$SITE_PACKAGES/neckenml/analyzer" \
  -v "$SCRIPT_DIR/native_analyze_batch.py:/app/native_analyze_batch.py" \
  -v "$INPUT_DIR:/app/audio_cache" \
  -v "$OUTPUT_DIR:/app/native_analysis_out" \
  --user root \
  "$IMAGE" \
  python /app/native_analyze_batch.py /app/audio_cache /app/native_analysis_out

echo ""
echo "Done. Now import the results locally (no Docker needed):"
echo "  cd $(cd "$WORKER_DIR/../ml-trainer" 2>/dev/null && pwd || echo '../ml-trainer')"
echo "  .venv/bin/python -m tuner.import_native_analysis \"$OUTPUT_DIR\""
