"""
Tests for the AnalysisService.

Tests cover:
- Track analysis workflow
- Error handling
- Memory management
"""
import pytest
from unittest.mock import Mock, MagicMock, patch


class TestAnalysisService:
    """Test suite for AnalysisService."""

    @pytest.fixture
    def analysis_service(self, mock_db_session, mock_audio_analyzer, mock_audio_fetcher):
        """Create an AnalysisService instance with mocked dependencies."""
        with patch('app.services.analysis.ClassificationService') as MockClassifier:
            MockClassifier.return_value.classify_track_immediately.return_value = None

            from app.services.analysis import AnalysisService
            service = AnalysisService(mock_db_session)
            return service

    def test_initialization(self, mock_db_session):
        """Test service can be initialized."""
        with patch('app.services.analysis.AudioFetcher'):
            from app.services.analysis import AnalysisService
            service = AnalysisService(mock_db_session)
            assert service.db == mock_db_session

    def test_initialization_without_db(self):
        """Test service handles None db gracefully."""
        with patch('app.services.analysis.AudioFetcher'):
            from app.services.analysis import AnalysisService
            service = AnalysisService(None)
            assert service.repo is None
            assert service.classifier_service is None

    def test_get_analyzer_lazy_loading(self, analysis_service):
        """Test that analyzer is lazily loaded."""
        # Initially no analyzer
        assert analysis_service._analyzer is None

    def test_cleanup_analyzer_memory(self, analysis_service):
        """Test analyzer memory cleanup."""
        # Set up a mock analyzer
        mock_analyzer = Mock()
        analysis_service._analyzer = mock_analyzer

        analysis_service.cleanup_analyzer_memory()

        mock_analyzer.close.assert_called_once()
        assert analysis_service._analyzer is None

    def test_classify_from_title_polska(self, analysis_service, sample_track, mock_db_session):
        """Test title-based classification detects 'polska'."""
        sample_track.title = "Slängpolska från Boda"
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        result = analysis_service._classify_from_title(sample_track)

        assert result is True

    def test_classify_from_title_schottis(self, analysis_service, sample_track, mock_db_session):
        """Test title-based classification detects 'schottis'."""
        sample_track.title = "Schottis från Dalarna"
        mock_db_session.query.return_value.filter.return_value.first.return_value = None

        result = analysis_service._classify_from_title(sample_track)

        assert result is True

    def test_classify_from_title_unknown(self, analysis_service, sample_track):
        """Test title-based classification handles unknown styles."""
        sample_track.title = "Unknown Song"

        result = analysis_service._classify_from_title(sample_track)

        assert result is False

    def test_ensure_youtube_link_new(self, analysis_service, sample_track, mock_db_session):
        """Test creating a new YouTube link."""
        mock_db_session.query.return_value.filter_by.return_value.first.return_value = None

        analysis_service._ensure_youtube_link(sample_track, "newVideoId123")

        # Should add a new link
        assert mock_db_session.add.called


class TestAnalysisServiceIntegration:
    """Integration tests for AnalysisService."""

    @pytest.mark.integration
    def test_imports_work(self):
        """Test that all imports work correctly."""
        from app.services.analysis import AnalysisService
        from neckenml.analyzer import AudioAnalyzer

        assert AnalysisService is not None
        assert AudioAnalyzer is not None

    @pytest.mark.integration
    def test_classification_imports(self):
        """Test classification service imports work."""
        from app.services.classification import ClassificationService
        from neckenml.core import StyleClassifier, compute_derived_features

        assert ClassificationService is not None
        assert StyleClassifier is not None
        assert compute_derived_features is not None
