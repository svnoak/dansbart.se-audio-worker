"""
Database models for the audio analysis worker.

These models define the database schema for storing audio analysis results.
The audio worker writes to these tables; the main application reads from them.

AGPL-3.0 License - See LICENSE file for details.
"""
import uuid
from datetime import datetime
from typing import List, Optional
from sqlalchemy import String, Integer, Float, Boolean, ForeignKey, DateTime, UniqueConstraint
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func
from app.core.database import Base
from pgvector.sqlalchemy import Vector


class Track(Base):
    """
    Core track entity with audio analysis features.

    The audio worker updates analysis fields (tempo_bpm, swing_ratio, etc.)
    after processing audio files.
    """
    __tablename__ = "tracks"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String, index=True)
    isrc: Mapped[str | None] = mapped_column(String, index=True)

    # Metadata Relationships
    album_links: Mapped[List["TrackAlbum"]] = relationship("TrackAlbum", back_populates="track", cascade="all, delete-orphan")
    artist_links: Mapped[List["TrackArtist"]] = relationship("TrackArtist", back_populates="track", cascade="all, delete-orphan")

    # Audio Features (populated by analysis)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    has_vocals: Mapped[bool | None] = mapped_column(Boolean, default=False, nullable=True)
    duration_ms: Mapped[int] = mapped_column(Integer, nullable=True)
    tempo_bpm: Mapped[float | None] = mapped_column(Float, nullable=True)
    swing_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    articulation: Mapped[float | None] = mapped_column(Float, nullable=True)
    bounciness: Mapped[float | None] = mapped_column(Float, nullable=True)
    loudness: Mapped[float | None] = mapped_column(Float, nullable=True)
    punchiness: Mapped[float | None] = mapped_column(Float, nullable=True)
    voice_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    polska_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    hambo_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    bpm_stability: Mapped[float | None] = mapped_column(Float, nullable=True)
    is_instrumental: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # Analysis vector embedding
    embedding: Mapped[list[float] | None] = mapped_column(Vector(), nullable=True)
    analysis_version: Mapped[str | None] = mapped_column(String, nullable=True, index=True)

    # Analysis Data blobs
    bars: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    sections: Mapped[list[float] | None] = mapped_column(JSONB, nullable=True)
    section_labels: Mapped[list[str] | None] = mapped_column(JSONB, nullable=True)
    processing_status: Mapped[str] = mapped_column(String, default="PENDING", server_default="PENDING")

    # Relationships
    analysis_sources = relationship("AnalysisSource", back_populates="track", cascade="all, delete-orphan")
    playback_links = relationship("PlaybackLink", back_populates="track", cascade="all, delete-orphan")
    dance_styles = relationship("TrackDanceStyle", back_populates="track", cascade="all, delete-orphan")
    structure_versions = relationship("TrackStructureVersion", back_populates="track", cascade="all, delete-orphan")

    @property
    def primary_artist(self) -> Optional["Artist"]:
        """Returns the first artist marked as primary."""
        for link in self.artist_links:
            if link.role == 'primary':
                return link.artist
        return self.artist_links[0].artist if self.artist_links else None

    @property
    def album(self) -> Optional["Album"]:
        """Returns the first album (for backward compatibility)."""
        return self.album_links[0].album if self.album_links else None


class TrackArtist(Base):
    """Junction table for track-artist relationships."""
    __tablename__ = "track_artists"
    __table_args__ = (
        UniqueConstraint('track_id', 'artist_id', name='unique_track_artist'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id"))
    artist_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("artists.id"))
    role: Mapped[str] = mapped_column(String, default="primary")
    track: Mapped["Track"] = relationship("Track", back_populates="artist_links")
    artist: Mapped["Artist"] = relationship("Artist", back_populates="track_links")


class TrackAlbum(Base):
    """Junction table for track-album relationships."""
    __tablename__ = "track_albums"
    __table_args__ = (
        UniqueConstraint('track_id', 'album_id', name='unique_track_album'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id"))
    album_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("albums.id"))

    track: Mapped["Track"] = relationship("Track", back_populates="album_links")
    album: Mapped["Album"] = relationship("Album", back_populates="track_links")


class Artist(Base):
    """Artist metadata."""
    __tablename__ = "artists"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String, index=True)
    image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    spotify_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True)
    track_links: Mapped[List["TrackArtist"]] = relationship("TrackArtist", back_populates="artist")
    albums: Mapped[List["Album"]] = relationship("Album", back_populates="artist")
    is_verified: Mapped[bool] = mapped_column(Boolean, default=False, server_default='false')


class Album(Base):
    """Album metadata."""
    __tablename__ = "albums"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    title: Mapped[str] = mapped_column(String, index=True)
    cover_image_url: Mapped[str | None] = mapped_column(String, nullable=True)
    release_date: Mapped[str | None] = mapped_column(String, nullable=True)
    spotify_id: Mapped[str | None] = mapped_column(String, unique=True, nullable=True, index=True)
    artist_id: Mapped[uuid.UUID | None] = mapped_column(ForeignKey("artists.id"), nullable=True)

    artist: Mapped["Artist"] = relationship("Artist", back_populates="albums")
    track_links: Mapped[List["TrackAlbum"]] = relationship("TrackAlbum", back_populates="album", cascade="all, delete-orphan")


class AnalysisSource(Base):
    """
    Stores raw analysis artifacts from the ML pipeline.

    This allows re-classification without re-analyzing audio files.
    """
    __tablename__ = "analysis_sources"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))
    source_type: Mapped[str] = mapped_column(String)  # 'neckenml_analyzer', 'hybrid_ml_v2'
    raw_data: Mapped[dict] = mapped_column(JSONB)
    confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    analyzed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    track = relationship("Track", back_populates="analysis_sources")


class TrackDanceStyle(Base):
    """
    Dance style classification results.

    Each track can have multiple dance styles (primary + alternatives).
    """
    __tablename__ = "track_dance_styles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))

    dance_style: Mapped[str] = mapped_column(String, index=True)
    sub_style: Mapped[str | None] = mapped_column(String, nullable=True, index=True)
    is_primary: Mapped[bool] = mapped_column(Boolean, default=False)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)

    tempo_category: Mapped[str | None] = mapped_column(String, nullable=True)
    bpm_multiplier: Mapped[float] = mapped_column(Float, default=1.0)
    effective_bpm: Mapped[int] = mapped_column(Integer)
    source: Mapped[str | None] = mapped_column(String, nullable=True)

    track = relationship("Track", back_populates="dance_styles")
    confirmation_count: Mapped[int] = mapped_column(Integer, default=0)
    is_user_confirmed: Mapped[bool] = mapped_column(Boolean, default=False)


class PlaybackLink(Base):
    """Links to playback sources (YouTube, Spotify, etc.)."""
    __tablename__ = "playback_links"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))
    platform: Mapped[str] = mapped_column(String)
    deep_link: Mapped[str] = mapped_column(String)
    is_working: Mapped[bool] = mapped_column(Boolean, default=True)

    track = relationship("Track", back_populates="playback_links")


class TrackStructureVersion(Base):
    """Audio structure annotations (bars, sections)."""
    __tablename__ = "track_structure_versions"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    track_id: Mapped[uuid.UUID] = mapped_column(ForeignKey("tracks.id", ondelete="CASCADE"))

    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    description: Mapped[str | None] = mapped_column(String, nullable=True)

    structure_data: Mapped[dict] = mapped_column(JSONB)

    vote_count: Mapped[int] = mapped_column(Integer, default=1)
    report_count: Mapped[int] = mapped_column(Integer, default=0)
    is_active: Mapped[bool] = mapped_column(Boolean, default=False)
    is_hidden: Mapped[bool] = mapped_column(Boolean, default=False)
    author_alias: Mapped[str | None] = mapped_column(String, nullable=True)
    track = relationship("Track", back_populates="structure_versions")


class GenreProfile(Base):
    """Genre analysis profiles for comparison."""
    __tablename__ = "genre_profiles"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    genre_name: Mapped[str] = mapped_column(String, unique=True, index=True)
    avg_note_density: Mapped[float] = mapped_column(Float)
    common_meters: Mapped[dict] = mapped_column(JSONB)
    rhythm_patterns: Mapped[dict] = mapped_column(JSONB)
    sample_size: Mapped[int] = mapped_column(Integer)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())


class DanceMovementFeedback(Base):
    """
    Global consensus on how dance styles feel.
    Used for movement-based recommendations.
    """
    __tablename__ = "dance_movement_feedback"
    __table_args__ = (
        UniqueConstraint('dance_style', 'movement_tag', name='_dance_move_uc'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    dance_style: Mapped[str] = mapped_column(String, index=True, nullable=False)
    movement_tag: Mapped[str] = mapped_column(String, index=True, nullable=False)
    score: Mapped[float] = mapped_column(Float, default=0.0)
    occurrences: Mapped[int] = mapped_column(Integer, default=0)


class StyleKeyword(Base):
    """
    Maps keywords in track metadata to dance styles.
    Used for metadata-based classification.
    """
    __tablename__ = "style_keywords"
    __table_args__ = (
        UniqueConstraint('keyword', name='unique_keyword'),
    )

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    keyword: Mapped[str] = mapped_column(String, nullable=False, index=True)
    main_style: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sub_style: Mapped[str | None] = mapped_column(String, nullable=True)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())


class DanceStyleConfig(Base):
    """
    Configuration for dance styles, including beats_per_bar for bar correction.
    Used after classification to re-derive bar positions from beat timestamps.
    """
    __tablename__ = "dance_style_config"

    id: Mapped[uuid.UUID] = mapped_column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    main_style: Mapped[str] = mapped_column(String, nullable=False, index=True)
    sub_style: Mapped[str | None] = mapped_column(String, nullable=True)
    beats_per_bar: Mapped[int] = mapped_column(Integer, nullable=False, default=3)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True, server_default='true')
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
