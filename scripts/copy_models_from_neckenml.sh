#!/usr/bin/env bash
# Copy ML models from neckenml-analyzer (source of truth) into dansbart-audio-worker/models.
# Both audio and feature workers mount this directory at /app/models.
# Run from repo root: dansbart-audio-worker/scripts/copy_models_from_neckenml.sh
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SOURCE="${REPO_ROOT}/neckenml-analyzer/models"
DEST="${REPO_ROOT}/dansbart-audio-worker/models"
mkdir -p "$DEST"
if [ ! -d "$SOURCE" ] || [ -z "$(ls -A "$SOURCE"/*.pb 2>/dev/null)" ]; then
  echo "No .pb files in neckenml-analyzer/models. Put the models there first or run download_models.sh." >&2
  exit 1
fi
echo "Copying models from neckenml-analyzer/models to dansbart-audio-worker/models ..."
cp -v "$SOURCE"/*.pb "$DEST/"
echo "Done. Restart workers (e.g. docker compose up --build)."