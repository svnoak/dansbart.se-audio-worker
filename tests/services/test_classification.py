"""
Tests for the ClassificationService (audio worker version).

Tests cover:
- Feature extraction from stored artifacts
- Classification from analysis data
- Reclassification of library
"""
import pytest
from unittest.mock import Mock, MagicMock, patch


class TestClassificationService:
    """Test suite for ClassificationService."""

    @pytest.fixture
    def classification_service(self, mock_db_session):
        """Create a ClassificationService instance with mocked dependencies."""
        with patch('app.services.classification.StyleClassifier') as MockClassifier:
            MockClassifier.return_value.classify.return_value = [
                {
                    'style': 'Polska',
                    'sub_style': None,
                    'type': 'Primary',
                    'confidence': 0.85,
                    'dance_tempo': 'Lagom',
                    'multiplier': 1.0,
                    'effective_bpm': 120
                }
            ]

            from app.services.classification import ClassificationService
            service = ClassificationService(mock_db_session)
            return service

    def test_initialization(self, mock_db_session):
        """Test service can be initialized."""
        with patch('app.services.classification.StyleClassifier'):
            from app.services.classification import ClassificationService
            service = ClassificationService(mock_db_session)
            assert service.db == mock_db_session

    def test_get_features_from_neckenml_source(self, classification_service, sample_track):
        """Test feature extraction from neckenml_analyzer source."""
        source = Mock()
        source.source_type = "neckenml_analyzer"
        source.raw_data = {
            "rhythm_extractor": {"beats": [], "bars": [], "ternary_confidence": 0.8},
            "musicnn": {"avg_embedding": [0.0] * 200},
        }

        with patch('app.services.classification.compute_derived_features') as mock_compute:
            mock_compute.return_value = {'tempo_bpm': 120.0}

            features = classification_service._get_features_from_source(source)

            mock_compute.assert_called_once_with(source.raw_data)

    def test_get_features_from_legacy_source(self, classification_service):
        """Test feature extraction from hybrid_ml_v2 source."""
        source = Mock()
        source.source_type = "hybrid_ml_v2"
        source.raw_data = {'tempo_bpm': 115.0, 'swing_ratio': 1.2}

        features = classification_service._get_features_from_source(source)

        # Legacy format should return raw_data directly
        assert features['tempo_bpm'] == 115.0

    def test_save_predictions(self, classification_service, sample_track, mock_db_session):
        """Test saving classification predictions."""
        predictions = [
            {
                'style': 'Polska',
                'sub_style': None,
                'type': 'Primary',
                'confidence': 0.85,
                'dance_tempo': 'Lagom',
                'multiplier': 1.0,
                'effective_bpm': 120
            }
        ]

        classification_service._save_predictions(sample_track, predictions)

        # Should have called commit
        assert mock_db_session.commit.called

    def test_save_predictions_rollback_on_error(self, classification_service, sample_track, mock_db_session):
        """Test that predictions rollback on error."""
        mock_db_session.commit.side_effect = Exception("DB Error")

        predictions = [{'style': 'Polska', 'type': 'Primary'}]

        # Should not raise, but should rollback
        classification_service._save_predictions(sample_track, predictions)

        assert mock_db_session.rollback.called

    def test_save_predictions_preserves_user_confirmed_style(self, classification_service, sample_track):
        """A user-confirmed style row must survive a reclassify."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.core.models import TrackDanceStyle

        engine = create_engine("sqlite:///:memory:")
        TrackDanceStyle.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        db.add(TrackDanceStyle(
            track_id=sample_track.id, dance_style="Schottis", sub_style=None,
            is_primary=True, confidence=1.0, tempo_category="Snabbt",
            bpm_multiplier=1.0, effective_bpm=130, confirmation_count=3,
            is_user_confirmed=True,
        ))
        db.commit()

        classification_service.db = db
        predictions = [{
            'style': 'Polska', 'sub_style': None, 'type': 'Primary',
            'confidence': 0.7, 'dance_tempo': 'Medium', 'multiplier': 1.0, 'effective_bpm': 110,
        }]
        classification_service._save_predictions(sample_track, predictions)

        rows = {r.dance_style: r for r in db.query(TrackDanceStyle)
                .filter(TrackDanceStyle.track_id == sample_track.id).all()}

        assert rows['Schottis'].is_user_confirmed is True
        assert rows['Schottis'].effective_bpm == 130
        assert rows['Polska'].is_user_confirmed is False
        db.close()

    def test_save_predictions_skips_style_already_confirmed(self, classification_service, sample_track):
        """No duplicate row is created when a prediction repeats an already-confirmed style."""
        from sqlalchemy import create_engine
        from sqlalchemy.orm import sessionmaker
        from app.core.models import TrackDanceStyle

        engine = create_engine("sqlite:///:memory:")
        TrackDanceStyle.__table__.create(engine)
        db = sessionmaker(bind=engine)()
        db.add(TrackDanceStyle(
            track_id=sample_track.id, dance_style="Schottis", sub_style=None,
            is_primary=True, confidence=1.0, tempo_category="Snabbt",
            bpm_multiplier=1.0, effective_bpm=130, confirmation_count=3,
            is_user_confirmed=True,
        ))
        db.commit()

        classification_service.db = db
        predictions = [
            {'style': 'Schottis', 'sub_style': None, 'type': 'Primary',
             'confidence': 0.6, 'dance_tempo': 'Medium', 'multiplier': 1.0, 'effective_bpm': 100},
            {'style': 'Vals', 'sub_style': None, 'type': 'Secondary',
             'confidence': 0.4, 'dance_tempo': 'Lugnt', 'multiplier': 1.0, 'effective_bpm': 90},
        ]
        classification_service._save_predictions(sample_track, predictions)

        schottis_rows = db.query(TrackDanceStyle).filter(
            TrackDanceStyle.track_id == sample_track.id,
            TrackDanceStyle.dance_style == 'Schottis').all()
        assert len(schottis_rows) == 1
        assert schottis_rows[0].is_user_confirmed is True
        assert schottis_rows[0].effective_bpm == 130

        vals = db.query(TrackDanceStyle).filter(
            TrackDanceStyle.track_id == sample_track.id,
            TrackDanceStyle.dance_style == 'Vals').first()
        assert vals is not None
        assert vals.is_user_confirmed is False
        db.close()


class TestClassificationIntegration:
    """Integration tests that test the full classification flow."""

    @pytest.mark.integration
    def test_imports_work(self):
        """Test that all imports work correctly."""
        from app.services.classification import ClassificationService
        from neckenml.core import StyleClassifier, compute_derived_features

        assert ClassificationService is not None
        assert StyleClassifier is not None
        assert compute_derived_features is not None
