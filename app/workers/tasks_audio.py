"""
Audio Worker Celery Tasks.

Heavy ML-based audio analysis and classification tasks.
Requires: TensorFlow, Essentia, Madmom, Librosa, neckenml

AGPL-3.0 License - See LICENSE file for details.
"""
import structlog
from celery.exceptions import MaxRetriesExceededError
from celery.signals import worker_shutdown
from app.core.celery_app import celery_app
from app.core.database import SessionLocal
from app.services.analysis import AnalysisService
from app.core.models import Track
import gc

log = structlog.get_logger()

# Global variable (per worker process)
# Loads once, reused for subsequent tasks
_worker_analysis_service = None


def get_analysis_service():
    """Get or create the analysis service with loaded models."""
    global _worker_analysis_service
    if _worker_analysis_service is None:
        log.info("loading_neckenml_models", message="Loading neckenml models for this process")
        _worker_analysis_service = AnalysisService(None)
    return _worker_analysis_service


def cleanup_resources():
    """Clean up memory after analysis by forcing garbage collection."""
    collected = gc.collect()
    log.debug("gc_cleanup", objects_collected=collected)


@worker_shutdown.connect
def cleanup_worker_on_shutdown(**kwargs):
    """Clean up neckenml resources when worker shuts down gracefully."""
    global _worker_analysis_service
    if _worker_analysis_service and hasattr(_worker_analysis_service, '_analyzer'):
        if _worker_analysis_service._analyzer:
            log.info("worker_shutdown_cleanup", message="Cleaning up neckenml models")
            _worker_analysis_service._analyzer.close()
            log.info("worker_shutdown_complete", message="Cleanup complete")


@celery_app.task(
    bind=True,
    acks_late=True,
    queue='audio',
    autoretry_for=(Exception,),
    retry_backoff=60,
    retry_backoff_max=600,
    max_retries=3,
    retry_jitter=True,
)
def analyze_track_task(self, track_id: str):
    """
    Main audio analysis task.

    Fetches audio from YouTube, runs ML analysis, and stores results.

    Automatic retry:
    - Retries up to 3 times on any exception
    - Exponential backoff: 60s, 120s, 240s (capped at 600s)
    - On final failure, marks track as FAILED
    """
    attempt = self.request.retries + 1
    max_attempts = self.max_retries + 1
    log.info("analysis_started", track_id=track_id, attempt=attempt, max_attempts=max_attempts)

    # Get the service (loads model if first run)
    service = get_analysis_service()

    # Create fresh DB session
    db = SessionLocal()
    try:
        # Inject session into reused service (repo/classifier_service are None until first use)
        service.db = db
        if service.repo is None:
            from app.repository.analysis import AnalysisRepository
            service.repo = AnalysisRepository(db)
        else:
            service.repo.db = db
        if service.classifier_service is None:
            from app.services.classification import ClassificationService
            service.classifier_service = ClassificationService(db)
        else:
            service.classifier_service.db = db

        # Run analysis
        service.analyze_track_by_id(track_id)

        log.info("analysis_finished", track_id=track_id)

        # Clean up analyzer memory
        service.cleanup_analyzer_memory()
        cleanup_resources()
        gc.collect()

    except MaxRetriesExceededError:
        log.error("max_retries_exceeded", track_id=track_id)
        try:
            track = db.query(Track).filter(Track.id == track_id).first()
            if track:
                # REANALYZING tracks revert to DONE (old data is still valid)
                if track.processing_status == "REANALYZING":
                    track.processing_status = "DONE"
                else:
                    track.processing_status = "FAILED"
                db.commit()
        except Exception as status_err:
            log.error("failed_to_update_status", track_id=track_id, error=str(status_err))
        raise

    except Exception as e:
        db.rollback()
        log.error("analysis_failed", track_id=track_id, attempt=attempt, max_attempts=max_attempts, error=str(e))

        if self.request.retries >= self.max_retries:
            log.error("final_attempt_failed", track_id=track_id)
            try:
                track = db.query(Track).filter(Track.id == track_id).first()
                if track:
                    # REANALYZING tracks revert to DONE (old data is still valid)
                    if track.processing_status == "REANALYZING":
                        track.processing_status = "DONE"
                    else:
                        track.processing_status = "FAILED"
                    db.commit()
            except Exception as status_err:
                log.error("failed_to_update_status", track_id=track_id, error=str(status_err))
        else:
            try:
                track = db.query(Track).filter(Track.id == track_id).first()
                if track:
                    # REANALYZING stays REANALYZING on retry; PROCESSING resets to PENDING
                    if track.processing_status == "PROCESSING":
                        track.processing_status = "PENDING"
                        db.commit()
                        log.info("status_reset_to_pending", track_id=track_id)
                    elif track.processing_status != "REANALYZING":
                        track.processing_status = "PENDING"
                        db.commit()
                        log.info("status_reset_to_pending", track_id=track_id)
            except Exception as status_err:
                log.error("failed_to_update_status", track_id=track_id, target_status="PENDING", error=str(status_err))
        raise

    finally:
        try:
            service.cleanup_analyzer_memory()
        except Exception as e:
            log.error("finally_cleanup_error", error=str(e))

        cleanup_resources()
        gc.collect()
        db.close()
