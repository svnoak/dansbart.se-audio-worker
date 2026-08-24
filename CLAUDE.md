# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What This Is

AGPL-licensed Celery worker for audio analysis of Swedish folk music. Downloads audio from YouTube, runs ML-based feature extraction (tempo, key, loudness, dance style classification) using neckenml-analyzer and Essentia, then writes results to the shared PostgreSQL database. Part of the dansbart.se platform.

## Commands

### Run the worker

```bash
celery -A app.core.celery_app worker --loglevel=info --pool=solo -Q audio
```

Requires `POSTGRES_*` and `CELERY_BROKER_URL` env vars (see `.env.example`).

### Tests

```bash
pytest tests/ -v -m "not integration and not requires_audio"   # unit tests (no audio deps)
pytest tests/ -v -m "integration"                               # integration tests
pytest tests/ -v                                                # all tests
pytest tests/services/test_classification.py -v                 # single file
pytest tests/services/test_classification.py::TestClassName::test_method -v  # single test
```

### Linting

```bash
black --check app/ tests/
flake8 app/ tests/ --max-line-length=100 --ignore=E501,W503
isort --check-only app/ tests/
```

### Docker

```bash
docker build --platform linux/amd64 -t dansbart-audio-worker .   # must be linux/amd64 (Essentia)
docker-compose up -d --build                                      # standalone dev stack with PG + Redis
```

### Model setup

```bash
./scripts/download_models.sh        # download MusiCNN models from Essentia CDN
./scripts/download_models.sh -f     # force re-download
```

## Architecture

### Task flow

```
Java API --> Redis/Celery --> analyze_track_task(track_id)
                                  |
                          AudioFetcher (yt-dlp)
                                  |
                          neckenml AudioAnalyzer
                                  |
                          Store artifacts (AnalysisSource)
                                  |
                          ClassificationService (StyleClassifier)
                                  |
                          Bar correction (dance_style_config.beats_per_bar)
                                  |
                          Update Track in PostgreSQL
```

### Bar correction

After classification, bars are corrected based on the classified style's `beats_per_bar` from the `dance_style_config` table. Beat timestamps from the raw artifacts are regrouped (every Nth beat = bar start). This fixes common Madmom misdetections (e.g. 3/4 polska detected as 2/4). The correction is skipped when detected meter already matches the style's expected meter. During reclassification (`reclassify_library`), bar correction is also applied.

### Key files

- `app/core/celery_app.py` - Celery config, signal handlers (trace_id binding, canonical logging)
- `app/workers/tasks_audio.py` - `analyze_track_task` entry point, retry/cleanup logic
- `app/services/analysis.py` - AnalysisService orchestrates fetch -> analyze -> classify -> correct bars -> store
- `app/services/classification.py` - Wraps neckenml StyleClassifier, handles reclassification + bar correction
- `app/services/bar_correction.py` - Re-derives bar positions from beat timestamps using dance_style_config beats_per_bar
- `app/services/style_config_cache.py` - In-memory cache for dance_style_config table (5min TTL)
- `app/workers/audio/fetcher.py` - YouTube search/download with scoring (title 40%, artist 20%, duration 40%)
- `app/core/models.py` - SQLAlchemy ORM models (Track, AnalysisSource, TrackDanceStyle, DanceStyleConfig, etc.)
- `app/core/music_theory.py` - Tempo ranges for 10 Swedish folk dance styles

### Task retry behavior

- Max 3 retries, exponential backoff (60s base, 600s cap), jitter enabled
- On retry: resets track to PENDING (unless REANALYZING, which stays REANALYZING)
- On final failure: marks track FAILED with error message

### Resource management

- Singleton `AnalysisService` per worker process (ML models loaded once)
- After each task: `analyzer.close()`, `gc.collect()`, DB session closed
- Docker limits: 2GB reserved, 4GB max memory

### Track status lifecycle

```
PENDING --> PROCESSING --> DONE / FAILED
REANALYZING -----------> DONE / FAILED (stays visible in search during reanalysis)
```

### Fallback classification

When no audio is found, the worker attempts keyword-based dance style inference from the track title (confidence 0.5).

## Conventions

- No emojis in code, comments, or commit messages
- Commit format: `<type>: <summary>` (feat, fix, refactor, test, docs, chore, style)
- Structured JSON logging with context variables (trace_id, task_id, task_name)
- Repository pattern: `BaseRepository[T]` with generic CRUD

## Known Issues

- **bpm_stability** is extracted by neckenml but never saved to the Track model
- **duration_ms** gets overwritten by the audio worker when it should preserve the metadata fetcher's value
- Essentia requires **linux/amd64** - cannot run natively on macOS/ARM
