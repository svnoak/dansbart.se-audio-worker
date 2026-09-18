"""
Bar correction service.

Re-derives bar boundaries from beat timestamps using the correct
beats_per_bar for the classified dance style.

AGPL-3.0 License - See LICENSE file for details.
"""
import structlog
from typing import Optional
from sqlalchemy.orm import Session
from app.core.models import Track, AnalysisSource, TrackStructureVersion
from app.services.style_config_cache import get_beats_per_bar

log = structlog.get_logger()


def rederive_bars(beat_times: list[float], beats_per_bar: int) -> list[float]:
    """
    Re-derive bar boundaries from beat times using target beats_per_bar.

    Takes every Nth beat as a bar start, where N = beats_per_bar.

    Args:
        beat_times: List of beat timestamps in seconds
        beats_per_bar: Target beats per bar (e.g. 3 for Polska, 4 for Schottis)

    Returns:
        List of bar boundary timestamps
    """
    if not beat_times or beats_per_bar < 1:
        return []
    return [beat_times[i] for i in range(0, len(beat_times), beats_per_bar)]


def correct_track_bars(
    db: Session,
    track: Track,
    artifacts: dict,
    main_style: str,
    sub_style: Optional[str] = None,
) -> bool:
    """
    Correct a track's bars based on its classified dance style.

    Looks up beats_per_bar from dance_style_config, re-derives bars
    from stored beat timestamps, and updates the Track and its
    active TrackStructureVersion.

    Args:
        db: SQLAlchemy session
        track: Track to correct
        artifacts: Raw artifacts dict (from AnalysisSource.raw_data)
        main_style: Classified main dance style
        sub_style: Optional classified sub-style

    Returns:
        True if bars were corrected, False if skipped
    """
    target_bpb = get_beats_per_bar(db, main_style, sub_style)
    if target_bpb is None:
        return False

    rhythm = artifacts.get("rhythm_extractor", {})
    beat_times = rhythm.get("beats", [])
    detected_bpb = rhythm.get("beats_per_bar")

    if not beat_times:
        log.debug("bar_correction_skipped", reason="no_beat_times", title=track.title)
        return False

    # Skip if detection already matches the expected meter
    if detected_bpb == target_bpb:
        log.debug("bar_correction_skipped", reason="meter_matches",
                  title=track.title, beats_per_bar=target_bpb)
        return False

    corrected_bars = rederive_bars(beat_times, target_bpb)
    track.bars = corrected_bars

    # Update active structure version if present
    for sv in track.structure_versions:
        if sv.is_active and sv.structure_data:
            sv.structure_data = {
                **sv.structure_data,
                "bars": corrected_bars
            }

    log.info("bars_corrected",
             title=track.title,
             style=main_style,
             detected_bpb=detected_bpb,
             target_bpb=target_bpb,
             bar_count=len(corrected_bars))

    return True
