"""
Dance style classification service.

Uses neckenml's StyleClassifier to predict dance styles from audio features.

AGPL-3.0 License - See LICENSE file for details.
"""
import structlog
from sqlalchemy.orm import Session
from app.core.models import Track, AnalysisSource, TrackDanceStyle
from neckenml.core import StyleClassifier, compute_derived_features
from app.core.music_theory import categorize_tempo
from app.services.style_keywords_cache import get_sorted_keywords

log = structlog.get_logger()


class ClassificationService:
    """
    Classifies tracks into dance styles based on audio analysis.

    Uses a combination of ML predictions and metadata matching.
    """

    def __init__(self, db: Session):
        self.db = db
        if db:
            self.classifier = StyleClassifier(
                db=db,
                categorize_tempo_fn=categorize_tempo,
                get_keywords_fn=get_sorted_keywords
            )
        else:
            self.classifier = None

    def _get_features_from_source(self, source: AnalysisSource) -> dict:
        """
        Extract features from an AnalysisSource.

        Handles both old and new formats:
        - Old format (hybrid_ml_v2): raw_data contains features directly
        - New format (neckenml_analyzer): raw_data contains artifacts
        """
        if source.source_type == "neckenml_analyzer":
            log.info("computing_features_from_artifacts", message="Computing features from stored artifacts")
            return compute_derived_features(source.raw_data)
        else:
            return source.raw_data

    def _save_predictions(self, track, predictions):
        """Save classification predictions to database."""
        try:
            # Remove existing styles (only for non-confirmed tracks)
            self.db.query(TrackDanceStyle).filter(TrackDanceStyle.track_id == track.id).delete()

            # Add new styles
            for p in predictions:
                new_style = TrackDanceStyle(
                    track_id=track.id,
                    dance_style=p['style'],
                    sub_style=p.get('sub_style'),
                    is_primary=(p['type'] == 'Primary'),
                    confidence=p.get('confidence', 0.0),
                    tempo_category=p.get('dance_tempo'),
                    bpm_multiplier=p.get('multiplier', 1.0),
                    effective_bpm=p.get('effective_bpm', 0),
                    is_user_confirmed=False
                )
                self.db.add(new_style)

            self.db.commit()

        except Exception as e:
            self.db.rollback()
            log.error("save_predictions_failed", title=track.title, error=str(e))

    def reclassify_library(self):
        """
        Re-classify all tracks in the library.

        Skips user-confirmed tracks to preserve manual corrections.

        Returns:
            dict: Statistics about the reclassification
        """
        log.info("reclassify_library_started")

        tracks = (self.db.query(Track)
                  .join(AnalysisSource)
                  .filter(AnalysisSource.source_type.in_(['neckenml_analyzer', 'hybrid_ml_v2']))
                  .all())

        updated_count = 0
        skipped_count = 0

        for track in tracks:
            # Safety lock: don't override user-confirmed styles
            is_locked = any(s.is_user_confirmed for s in track.dance_styles)

            if is_locked:
                skipped_count += 1
                continue

            source = next((s for s in track.analysis_sources
                          if s.source_type in ['neckenml_analyzer', 'hybrid_ml_v2']), None)
            if not source:
                continue

            features = self._get_features_from_source(source)
            predictions = self.classifier.classify(track, features)
            self._save_predictions(track, predictions)

            # Correct bars based on classified style
            if predictions and source.raw_data:
                from app.services.bar_correction import correct_track_bars
                primary = predictions[0]
                correct_track_bars(
                    self.db, track, source.raw_data,
                    primary['style'], primary.get('sub_style')
                )

            updated_count += 1

        log.info("reclassify_library_complete", updated=updated_count, skipped=skipped_count)

        return {"updated": updated_count, "skipped": skipped_count}

    def classify_track_immediately(self, track: Track, analysis_data: dict = None):
        """
        Classify a specific track immediately.

        Args:
            track: Track instance to classify
            analysis_data: Optional pre-computed analysis data
        """
        # Check if user locked it
        for style in track.dance_styles:
            if style.is_user_confirmed:
                log.info("classification_skipped", title=track.title, reason="user_confirmed")
                return

        features = analysis_data

        if not features:
            source = next((s for s in track.analysis_sources
                          if s.source_type in ['neckenml_analyzer', 'hybrid_ml_v2']), None)
            if source:
                features = self._get_features_from_source(source)

        if not features:
            log.warn("no_analysis_data", title=track.title)
            return

        # Update vocals flag
        is_instrumental = features.get('is_likely_instrumental', True)
        track.has_vocals = not is_instrumental
        self.db.add(track)

        # Run classification
        predictions = self.classifier.classify(track, features)

        # Save results
        self._save_predictions(track, predictions)

        if predictions:
            primary = predictions[0]
            log.info("track_classified", style=primary['style'], dance_tempo=primary['dance_tempo'])

            # Correct bars based on classified style
            source = next((s for s in track.analysis_sources
                          if s.source_type in ['neckenml_analyzer', 'hybrid_ml_v2']), None)
            if source and source.raw_data:
                from app.services.bar_correction import correct_track_bars
                correct_track_bars(
                    self.db, track, source.raw_data,
                    primary['style'], primary.get('sub_style')
                )
        else:
            log.warn("classification_empty", title=track.title)
