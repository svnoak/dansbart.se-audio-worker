"""
Dance Style Config Cache Service.

Provides in-memory caching of dance style configuration (beats_per_bar, etc.)
from database. Used after classification to correct bar positions.

AGPL-3.0 License - See LICENSE file for details.
"""
import structlog
import time
from typing import Dict, Tuple, Optional
from sqlalchemy.orm import Session

log = structlog.get_logger()

# Module-level cache: (main_style, sub_style) -> beats_per_bar
_config_cache: Dict[Tuple[str, Optional[str]], int] = {}
_cache_timestamp: float = 0

CACHE_TTL_SECONDS = 300


def get_config(db: Session, force_refresh: bool = False) -> Dict[Tuple[str, Optional[str]], int]:
    """
    Get style config mappings from cache or database.

    Returns:
        Dict mapping (main_style, sub_style) -> beats_per_bar
    """
    global _config_cache, _cache_timestamp

    now = time.time()
    cache_expired = (now - _cache_timestamp) > CACHE_TTL_SECONDS

    if force_refresh or cache_expired or not _config_cache:
        _refresh_cache(db)

    return _config_cache


def get_beats_per_bar(db: Session, main_style: str, sub_style: str = None) -> Optional[int]:
    """
    Look up beats_per_bar for a dance style.

    Checks sub_style-specific config first, then falls back to main_style default.

    Args:
        db: SQLAlchemy database session
        main_style: Primary dance style (e.g. "Polska")
        sub_style: Optional sub-style (e.g. "Bingsjopolska")

    Returns:
        beats_per_bar integer, or None if no config exists for this style
    """
    config = get_config(db)

    # Try sub_style-specific first
    if sub_style:
        result = config.get((main_style, sub_style))
        if result is not None:
            return result

    # Fall back to main_style default
    return config.get((main_style, None))


def invalidate_cache() -> None:
    """Manually invalidate the cache."""
    global _config_cache, _cache_timestamp
    _config_cache = {}
    _cache_timestamp = 0
    log.info("style_config_cache_invalidated")


def _refresh_cache(db: Session) -> None:
    """Load style config from database into cache."""
    global _config_cache, _cache_timestamp

    from app.core.models import DanceStyleConfig

    configs = db.query(DanceStyleConfig).filter(
        DanceStyleConfig.is_active == True
    ).all()

    _config_cache = {
        (c.main_style, c.sub_style): c.beats_per_bar
        for c in configs
    }

    _cache_timestamp = time.time()
    log.info("style_config_cache_refreshed", config_count=len(_config_cache))


def get_cache_info() -> dict:
    """Get cache statistics for debugging/admin."""
    global _config_cache, _cache_timestamp

    now = time.time()
    age = now - _cache_timestamp if _cache_timestamp > 0 else -1

    return {
        "size": len(_config_cache),
        "age_seconds": round(age, 1) if age >= 0 else None,
        "ttl_seconds": CACHE_TTL_SECONDS,
        "expires_in": round(CACHE_TTL_SECONDS - age, 1) if age >= 0 else None,
        "is_valid": age >= 0 and age < CACHE_TTL_SECONDS
    }
