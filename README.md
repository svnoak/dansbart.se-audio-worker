# Dansbart Audio Worker

Open-source audio analysis worker for Swedish folk dance music classification.

This is the AGPL-licensed audio analysis component of [dansbart.se](https://dansbart.se).

## Overview

This worker processes audio tracks through an ML pipeline to:
1. Fetch audio from YouTube
2. Extract audio features using [neckenml-analyzer](https://github.com/svnoak/neckenml-analyzer)
3. Classify tracks into Swedish folk dance styles (Polska, Hambo, Vals, etc.)
4. Store results in PostgreSQL for the main application to read

## Architecture

```
┌──────────────────────────────────────┐
│  dansbart-audio-worker	       │
│  - Fetches audio from YouTube        │
│  - Runs ML analysis (neckenml)       │
│  - Classifies dance styles           │
└──────────────┬───────────────────────┘
               │ writes
               ▼
        ┌──────────────┐
        │  PostgreSQL  │
        └──────────────┘
```

## Requirements

- Python 3.10+
- PostgreSQL 15+ with pgvector extension
- Redis
- FFmpeg
- ~4GB RAM for ML models

## Quick Start

### Using Docker (Recommended)

```bash
# Clone the repository
git clone https://github.com/svnoak/dansbart-audio-worker.git
cd dansbart-audio-worker

# Copy environment file
cp .env.example .env
# Edit .env with your database credentials

# Build and start (MusiCNN models are downloaded automatically during docker build)
docker-compose up -d --build
```

### Manual Installation

```bash
# Create virtual environment
python -m venv venv
source venv/bin/activate

# Install dependencies
pip install numpy Cython  # Build deps first
pip install -r requirements.txt

# Set environment variables
export POSTGRES_USER=postgres
export POSTGRES_PASSWORD=your_password
export POSTGRES_SERVER=localhost
export POSTGRES_DB=dansbart
export CELERY_BROKER_URL=redis://localhost:6379/0
export NECKENML_MODEL_DIR=./models

# Run the worker
celery -A app.core.celery_app worker --loglevel=info --pool=solo -Q audio
```

## Configuration

| Environment Variable | Description | Default |
|---------------------|-------------|---------|
| `POSTGRES_USER` | Database username | `postgres` |
| `POSTGRES_PASSWORD` | Database password | `password` |
| `POSTGRES_SERVER` | Database host | `localhost` |
| `POSTGRES_PORT` | Database port | `5432` |
| `POSTGRES_DB` | Database name | `dansbart` |
| `CELERY_BROKER_URL` | Redis connection URL | `redis://localhost:6379/0` |
| `NECKENML_MODEL_DIR` | Path to ML models | `/app/models` |

## Models

The worker requires pre-trained MusiCNN models (`msd-musicnn-1.pb`, `voice_instrumental-musicnn-msd-1.pb`). **When using Docker, these are downloaded automatically at image build time**—no one-time setup needed.

For non-Docker runs (or to refresh models on the host), use:

```bash
./scripts/download_models.sh
```

This downloads the two `.pb` files into **`models/`** in this repo. The Dockerfile runs this script during `docker build`, so the image ships with the models in `/app/models`.

If the worker logs **"Invalid GraphDef"** or **"MusiCNN embeddings model not loaded"**, the `.pb` file may be corrupted. Rebuild the image, or for local runs delete the files in `models/` and re-run with `-f`: `./scripts/download_models.sh -f`.

## Integration with dansbart.se

This worker is designed to run alongside the main dansbart.se application:

1. Both services share the same PostgreSQL database
2. The main app enqueues `analyze_track_task` to the `audio` queue
3. This worker picks up tasks and writes results back to the database
4. The main app reads classification results to display to users

## License

This project is licensed under the GNU Affero General Public License v3.0 (AGPL-3.0).

This means:
- You can use, modify, and distribute this code
- If you modify it and provide it as a network service, you must release your modifications
- Any derivative work must also be AGPL-3.0

The AGPL license is required because this project uses [Essentia](https://essentia.upf.edu/), which is AGPL-licensed.

## Contributing

Contributions are welcome! Please ensure any contributions are compatible with the AGPL-3.0 license.

## Related Projects

- [neckenml-analyzer](https://github.com/svnoak/neckenml-analyzer) - ML analysis library (APGL)
- [neckenml-analyzer-code(https://github.com/svnoak/neckenml-analyzer) - ML Core analysis library (MIT)
- [dansbart.se](https://dansbart.se) - Site using this specific audio worker for analysis and classification
