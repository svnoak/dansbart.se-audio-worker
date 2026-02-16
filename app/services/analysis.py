"""
Audio analysis service.

Orchestrates the full analysis pipeline:
1. Fetch audio from YouTube
2. Run ML analysis via neckenml
3. Store results in database
4. Trigger classification

AGPL-3.0 License - See LICENSE file for details.
"""
import structlog
from sqlalchemy.orm import Session, joinedload, selectinload
from app.core.models import Track, PlaybackLink, TrackStructureVersion, TrackArtist, TrackAlbum
from app.repository.analysis import AnalysisRepository
from app.workers.audio.fetcher import AudioFetcher
from neckenml.analyzer import AudioAnalyzer
from app.services.classification import ClassificationService
from app.core.config import settings
import time
import os
import gc
import psutil

log = structlog.get_logger()


class AnalysisService:
    """
    Main service for audio analysis.

    Manages the full lifecycle of track analysis:
    PENDING -> PROCESSING -> DONE/FAILED
    """

    def __init__(self, db: Session):
        self.db = db
        self.repo = AnalysisRepository(db) if db else None
        self.fetcher = AudioFetcher()
        self.classifier_service = ClassificationService(db) if db else None

        self._analyzer = None
        self._model_dir = os.getenv('NECKENML_MODEL_DIR', settings.NECKENML_MODEL_DIR)

    def _get_analyzer(self):
        """Get or create the cached AudioAnalyzer instance."""
        if self._analyzer is None:
            log.info("loading_neckenml_models", message="One-time load per worker")
            self._analyzer = AudioAnalyzer(audio_source=None, model_dir=self._model_dir)
        return self._analyzer

    def _log_memory_usage(self, stage: str):
        """Log current memory usage for debugging."""
        process = psutil.Process()
        mem_info = process.memory_info()
        mem_mb = mem_info.rss / 1024 / 1024
        log.debug("memory_usage", stage=stage, memory_mb=round(mem_mb, 1))
        return mem_mb

    def cleanup_analyzer_memory(self):
        """
        Force cleanup of analyzer's TensorFlow/Essentia resources.
        Call this after each analysis to prevent memory leaks.
        """
        if self._analyzer is not None:
            try:
                self._analyzer.close()
                self._analyzer = None
                log.debug("analyzer_cleanup", message="Analyzer resources released")
            except Exception as e:
                log.warn("analyzer_cleanup_warning", error=str(e))
            finally:
                gc.collect()

    def analyze_track_by_id(self, track_id: str):
        """
        Main entry point for track analysis.

        Manages the lifecycle state: PENDING -> PROCESSING -> DONE/FAILED
        """
        self._log_memory_usage("Start of task")

        self.repo.db = self.db
        self.classifier_service.db = self.db

        track = self.db.query(Track).options(
            joinedload(Track.playback_links),
            selectinload(Track.album_links).joinedload(TrackAlbum.album),
            joinedload(Track.artist_links).joinedload(TrackArtist.artist)
        ).filter(Track.id == track_id).first()

        if not track:
            return

        # Update state: PROCESSING
        log.info("status_update", title=track.title, status="PROCESSING")
        track.processing_status = "PROCESSING"
        self.db.commit()

        try:
            success = self._process_single_track(track)

            if success:
                track.processing_status = "DONE"
                log.info("status_update", title=track.title, status="DONE")
            else:
                track.processing_status = "FAILED"
                log.warn("status_update", title=track.title, status="FAILED")

            self.db.commit()

        except Exception as e:
            self.db.rollback()
            log.error("critical_failure", title=track.title, error=str(e))
            try:
                track.processing_status = "FAILED"
                self.db.commit()
            except:
                pass

        finally:
            # Cleanup files
            self.fetcher.cleanup(str(track.id))

            # Cleanup analyzer resources
            if self._analyzer:
                try:
                    self._analyzer.close()
                    self._analyzer = None
                    log.debug("analyzer_cleanup", message="Analyzer closed in finally block")
                except Exception as e:
                    log.error("analyzer_cleanup_error", error=str(e))

            # Clear SQLAlchemy Identity Map
            self.db.expire_all()

            # Python GC
            self._log_memory_usage("Before GC")
            gc.collect()
            self._log_memory_usage("After GC")

    def _process_single_track(self, track: Track) -> bool:
        """Process a single track through the analysis pipeline."""
        log.info("processing_track", title=track.title)

        # Get artist info
        artist_name = ""
        primary_link = next((l for l in track.artist_links if l.role == 'primary'), None)
        if primary_link:
            artist_name = primary_link.artist.name
        elif track.artist_links:
            artist_name = track.artist_links[0].artist.name

        album_name = track.album.title if track.album else ""

        # Check for existing YouTube link
        existing_link = next((l for l in track.playback_links if l.platform == 'youtube' and l.is_working), None)

        # Fetch audio
        if existing_link:
            log.info("using_existing_youtube_link", deep_link=existing_link.deep_link)
            result = self.fetcher.fetch_track_audio(
                track_id=str(track.id),
                query="",
                expected_duration_ms=track.duration_ms,
                track_title=track.title,
                artist_name=artist_name,
                direct_video_id=existing_link.deep_link
            )
        else:
            query = f"{artist_name} - {track.title}"
            log.info("searching_youtube", query=query)
            result = self.fetcher.fetch_track_audio(
                track_id=str(track.id),
                query=query,
                expected_duration_ms=track.duration_ms,
                track_title=track.title,
                artist_name=artist_name
            )

        if not result:
            log.info("no_audio_found", message="Attempting title-based classification")
            return self._classify_from_title(track)

        file_path = result['file_path']
        youtube_id = result.get('youtube_id')

        # Save YouTube link
        if youtube_id:
            self._ensure_youtube_link(track, youtube_id)

        # Get analyzer and run analysis
        analyzer = self._get_analyzer()

        log.info("starting_analysis", message="Starting CPU-intensive analysis")
        self._log_memory_usage("Before analysis")
        start_time = time.time()

        context = f"{track.title} {artist_name} {album_name}"
        result = analyzer.analyze_file(file_path, context, return_artifacts=True)

        end_time = time.time()
        self._log_memory_usage("After analysis")
        log.info("analysis_complete", duration_seconds=round(end_time - start_time, 2))

        if result:
            data = result["features"]
            artifacts = result["raw_artifacts"]

            # Save raw artifacts
            self.repo.add_analysis(
                track_id=track.id,
                source_type="neckenml_analyzer",
                raw_data=artifacts
            )

            # Update track with analysis results
            track.tempo_bpm = data.get('tempo_bpm')
            track.duration_ms = result.get('actual_duration_ms', 0)
            track.loudness = data.get('loudness_lufs')
            track.is_instrumental = data.get('is_likely_instrumental', False)

            track.swing_ratio = data.get('swing_ratio')
            track.articulation = data.get('articulation')
            track.bounciness = data.get('bounciness')
            track.punchiness = data.get('punchiness')

            track.polska_score = data.get('polska_score')
            track.hambo_score = data.get('hambo_score')
            track.voice_probability = data.get('voice_probability')

            track.bars = data.get('bars')
            track.sections = data.get('sections')
            track.section_labels = data.get('section_labels')
            track.embedding = data.get('embedding')

            # Create structure version
            ai_version = TrackStructureVersion(
                track_id=track.id,
                description="Original AI Analysis",
                author_alias="AI",
                structure_data={
                    "bars": data.get('bars'),
                    "sections": data.get('sections'),
                    "labels": data.get('section_labels')
                },
                is_active=True,
                vote_count=0,
                is_hidden=False
            )
            self.db.add(ai_version)
            self.db.add(track)

            # Auto-classify
            log.info("auto_classifying")
            self.classifier_service.classify_track_immediately(track, analysis_data=data)

            # Cleanup
            del result
            del data
            del artifacts
            gc.collect()
            self._log_memory_usage("After cleanup")

            return True

        return False

    def _ensure_youtube_link(self, track, video_id):
        """Save YouTube link if not already present."""
        exists = self.db.query(PlaybackLink).filter_by(track_id=track.id, deep_link=video_id).first()
        if not exists:
            link = PlaybackLink(
                track_id=track.id,
                platform="youtube",
                deep_link=video_id,
                is_working=True
            )
            self.db.add(link)

    def _classify_from_title(self, track: Track) -> bool:
        """
        Fallback classification when no audio is available.
        Attempts to infer dance style from the track title.
        """
        title_lower = track.title.lower()

        # Map of keywords to dance styles
        style_keywords = {
            "slängpolska": "Slängpolska",
            "slangpolska": "Slängpolska",
            "polska": "Polska",
            "schottis": "Schottis",
            "vals": "Vals",
            "waltz": "Vals",
            "hambo": "Hambo",
            "polka": "Polka",
            "mazurka": "Mazurka",
            "snoa": "Snoa",
            "gånglåt": "Gånglåt",
            "ganglåt": "Gånglåt",
            "ganglat": "Gånglåt",
            "marsch": "Gånglåt",
            "engelska": "Engelska",
        }

        detected_style = None
        for keyword, style in style_keywords.items():
            if keyword in title_lower:
                detected_style = style
                break

        if not detected_style:
            log.warn("style_inference_failed", title=track.title)
            return False

        log.info("style_inferred_from_title", detected_style=detected_style)

        from app.core.models import TrackDanceStyle

        existing = self.db.query(TrackDanceStyle).filter(
            TrackDanceStyle.track_id == track.id,
            TrackDanceStyle.dance_style == detected_style
        ).first()

        if not existing:
            style_row = TrackDanceStyle(
                track_id=track.id,
                dance_style=detected_style,
                is_primary=True,
                confidence=0.5,
                effective_bpm=0,
                tempo_category=None,
                bpm_multiplier=1.0,
                is_user_confirmed=False,
                confirmation_count=0
            )
            self.db.add(style_row)
        else:
            existing.is_primary = True
            if existing.confidence < 0.5:
                existing.confidence = 0.5

        return True
