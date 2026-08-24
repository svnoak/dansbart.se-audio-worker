"""
Tests for the audio worker Celery tasks.

Tests cover:
- Task initialization
- Resource management
- Error handling and retries
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
import uuid


class TestAnalyzeTrackTask:
    """Test suite for analyze_track_task."""

    @pytest.fixture
    def mock_session_local(self):
        """Mock the SessionLocal for database access."""
        with patch('app.workers.tasks_audio.SessionLocal') as MockSession:
            session = MagicMock()
            MockSession.return_value = session
            yield session

    @pytest.fixture
    def mock_analysis_service(self):
        """Mock the AnalysisService."""
        with patch('app.workers.tasks_audio.AnalysisService') as MockService:
            service = MagicMock()
            MockService.return_value = service
            yield service

    def test_get_analysis_service_singleton(self):
        """Test that analysis service is created as singleton."""
        from app.workers.tasks_audio import get_analysis_service, _worker_analysis_service

        # Reset global state
        import app.workers.tasks_audio as tasks_module
        tasks_module._worker_analysis_service = None

        with patch.object(tasks_module, 'AnalysisService') as MockService:
            service1 = tasks_module.get_analysis_service()
            service2 = tasks_module.get_analysis_service()

            # Should only create once
            assert MockService.call_count == 1
            assert service1 is service2

    def test_cleanup_resources_runs_gc(self):
        """Test that cleanup_resources runs garbage collection."""
        with patch('app.workers.tasks_audio.gc') as mock_gc:
            mock_gc.collect.return_value = 10

            from app.workers.tasks_audio import cleanup_resources
            cleanup_resources()

            mock_gc.collect.assert_called_once()

    def test_worker_shutdown_cleanup(self):
        """Test that worker shutdown cleans up resources."""
        import app.workers.tasks_audio as tasks_module

        mock_analyzer = Mock()
        mock_service = Mock()
        mock_service._analyzer = mock_analyzer

        tasks_module._worker_analysis_service = mock_service

        tasks_module.cleanup_worker_on_shutdown()

        mock_analyzer.close.assert_called_once()


class TestTaskConfiguration:
    """Test that task is configured correctly."""

    def test_task_queue_configuration(self):
        """Test that task is configured for audio queue."""
        from app.workers.tasks_audio import analyze_track_task

        # Check task configuration
        assert analyze_track_task.queue == 'audio'

    def test_task_retry_configuration(self):
        """Test that task has correct retry settings."""
        from app.workers.tasks_audio import analyze_track_task

        assert analyze_track_task.max_retries == 3
        assert analyze_track_task.autoretry_for == (Exception,)


class TestTaskIntegration:
    """Integration tests for audio worker tasks."""

    @pytest.mark.integration
    def test_imports_work(self):
        """Test that all imports work correctly."""
        from app.workers.tasks_audio import analyze_track_task, get_analysis_service
        from app.services.analysis import AnalysisService

        assert analyze_track_task is not None
        assert get_analysis_service is not None
        assert AnalysisService is not None

    @pytest.mark.integration
    def test_neckenml_imports(self):
        """Test that neckenml imports work correctly."""
        from neckenml.analyzer import AudioAnalyzer
        from neckenml.core import StyleClassifier, compute_derived_features

        assert AudioAnalyzer is not None
        assert StyleClassifier is not None
        assert compute_derived_features is not None
