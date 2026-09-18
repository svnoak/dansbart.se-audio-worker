"""
Shared pytest fixtures for dansbart-audio-worker tests.
"""
import pytest
from unittest.mock import Mock, MagicMock, patch
import uuid
import numpy as np


@pytest.fixture
def mock_db_session():
    """A mock database session for unit tests."""
    session = MagicMock()
    session.query.return_value.filter.return_value.first.return_value = None
    session.query.return_value.filter.return_value.all.return_value = []
    session.query.return_value.options.return_value.filter.return_value.first.return_value = None
    return session


@pytest.fixture
def sample_track():
    """Create a sample track for testing."""
    class MockArtist:
        def __init__(self):
            self.name = "Boda Spelmanslag"

    class MockArtistLink:
        def __init__(self):
            self.role = "primary"
            self.artist = MockArtist()

    class MockAlbum:
        def __init__(self):
            self.title = "Swedish Folk Music"

    class MockDanceStyle:
        def __init__(self):
            self.dance_style = "Polska"
            self.is_primary = True
            self.confidence = 0.85
            self.is_user_confirmed = False

    class MockPlaybackLink:
        def __init__(self):
            self.platform = "youtube"
            self.deep_link = "dQw4w9WgXcQ"
            self.is_working = True

    class MockTrack:
        def __init__(self):
            self.id = uuid.uuid4()
            self.title = "Slängpolska från Boda"
            self.duration_ms = 180000
            self.processing_status = "PENDING"
            self.tempo_bpm = None
            self.has_vocals = None
            self.swing_ratio = None
            self.articulation = None
            self.bounciness = None
            self.loudness = None
            self.is_instrumental = None
            self.punchiness = None
            self.voice_probability = None
            self.polska_score = None
            self.hambo_score = None
            self.bars = None
            self.sections = None
            self.section_labels = None
            self.embedding = None

            self.dance_styles = [MockDanceStyle()]
            self.artist_links = [MockArtistLink()]
            self.album_links = []
            self.playback_links = [MockPlaybackLink()]
            self.analysis_sources = []
            self.album = MockAlbum()

    return MockTrack()


@pytest.fixture
def sample_analysis_result():
    """Sample analysis result from AudioAnalyzer."""
    return {
        "features": {
            "ml_suggested_style": "Polska",
            "ml_confidence": 0.85,
            "embedding": list(np.random.randn(217)),
            "loudness_lufs": -14.0,
            "tempo_bpm": 120.0,
            "bpm_stability": 0.92,
            "is_likely_instrumental": True,
            "voice_probability": 0.2,
            "swing_ratio": 1.15,
            "articulation": 0.45,
            "bounciness": 0.55,
            "punchiness": 0.4,
            "polska_score": 0.35,
            "hambo_score": 0.25,
            "bars": [0.0, 1.5, 3.0],
            "sections": [[0, 8], [8, 16]],
            "section_labels": ["A", "B"],
        },
        "raw_artifacts": {
            "rhythm_extractor": {"beats": [], "bars": [], "ternary_confidence": 0.8},
            "musicnn": {"avg_embedding": [0.0] * 200},
            "vocal": {"vocal_score": 0.2, "instrumental_score": 0.8},
            "audio_stats": {"loudness_lufs": -14.0, "rms": 0.1, "zcr": 0.1, "onset_rate": 2.0},
        },
        "actual_duration_ms": 180000
    }


@pytest.fixture
def mock_audio_analyzer():
    """Mock AudioAnalyzer for testing without actual audio files."""
    with patch('app.services.analysis.AudioAnalyzer') as MockAnalyzer:
        instance = MockAnalyzer.return_value
        instance.analyze_file.return_value = {
            "features": {
                "ml_suggested_style": "Polska",
                "ml_confidence": 0.85,
                "embedding": list(np.random.randn(217)),
                "loudness_lufs": -14.0,
                "tempo_bpm": 120.0,
            },
            "raw_artifacts": {},
            "actual_duration_ms": 180000
        }
        instance.close.return_value = None
        yield instance


@pytest.fixture
def mock_audio_fetcher():
    """Mock AudioFetcher for testing without actual downloads."""
    with patch('app.services.analysis.AudioFetcher') as MockFetcher:
        instance = MockFetcher.return_value
        instance.fetch_track_audio.return_value = {
            'file_path': '/tmp/test_audio.mp3',
            'youtube_id': 'dQw4w9WgXcQ'
        }
        instance.cleanup.return_value = None
        yield instance
