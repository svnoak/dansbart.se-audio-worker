# dansbart-audio-worker

Celery worker for dansbart.se. It downloads audio from YouTube, analyses it with `neckenml-analyzer` and Essentia, classifies the dance style, and writes the result to PostgreSQL.

Repository: `svnoak/dansbart.se-audio-worker`. License: AGPL-3.0.

## Status

The ML pipeline is dormant. The worker still runs in production and gives a secondary signal. Community votes are the primary classification. Start new ML work only when the maintainer asks for it.

## Commands

```bash
celery -A app.core.celery_app worker --loglevel=info --pool=solo -Q audio   # needs POSTGRES_* and CELERY_BROKER_URL, see .env.example
pytest tests/ -m "not integration and not requires_audio"                    # unit tests
pytest tests/ -m "integration"                                               # integration tests
black --check app/ tests/
flake8 app/ tests/
isort --check-only app/ tests/
docker build --platform linux/amd64 -t dansbart-audio-worker .              # Essentia needs linux/amd64
./scripts/download_models.sh                                                 # MusiCNN models
```

## Task flow

`analyze_track_task(track_id)` -> `AudioFetcher` (yt-dlp) -> neckenml `AudioAnalyzer` -> store `AnalysisSource` artifacts -> `ClassificationService` -> bar correction -> update `Track`.

- `app/workers/tasks_audio.py`: entry point and retries. Max 3 retries with exponential backoff. On retry, the track goes back to `PENDING`. A `REANALYZING` track stays `REANALYZING`. On final failure, the track becomes `FAILED`.
- `app/services/analysis.py`: orchestrates fetch, analysis, classification, bar correction, and storage.
- `app/services/classification.py`: classification and reclassification.
- `app/services/bar_correction.py`: regroups beat timestamps with `beats_per_bar` from `dance_style_config`. It skips a track when the detected meter already matches the style.
- If the worker finds no audio, it infers the style from keywords in the title with confidence 0.5.

## Rules

- Load the ML models once: use one `AnalysisService` per worker process.
- After each task, close the analyzer, run `gc.collect()`, and close the database session.
- Log with the structlog context variables `trace_id`, `task_id`, and `task_name`.
- `ml-trainer` in the dansbart workspace calls `app/workers/audio/fetcher.py` by path. Keep that path stable.
- `scripts/native_analyze_batch.py` is on the branch `wip/ml-trainer-feature-v6`. `main` does not hold it.

## Conventions

- Commit format: `<type>: <summary>`. Types: `feat`, `fix`, `refactor`, `test`, `docs`, `chore`, `style`.
- No emojis in code, comments, or commit messages.
