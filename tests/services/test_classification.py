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
