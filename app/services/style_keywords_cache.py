"""
Style Keywords Cache Service.

Provides in-memory caching of style keywords from database.
Optimized for read-heavy, write-rare access patterns.

AGPL-3.0 License - See LICENSE file for details.
"""
import structlog
import time
from typing import Dict, Tuple, Optional, List
from sqlalchemy.orm import Session

log = structlog.get_logger()

# Module-level cache
_keyword_cache: Dict[str, Tuple[str, Optional[str]]] = {}
_cache_timestamp: float = 0

# Cache TTL in seconds (5 minutes)
CACHE_TTL_SECONDS = 300


def get_keywords(db: Session, force_refresh: bool = False) -> Dict[str, Tuple[str, Optional[str]]]:
    """
    Get keyword mappings from cache or database.

    Args:
        db: SQLAlchemy database session
        force_refresh: Force reload from database even if cache is valid

    Returns:
        Dict mapping keyword -> (main_style, sub_style)
        Keys are lowercase, sorted by length (longest first) for proper matching.
    """
    global _keyword_cache, _cache_timestamp

    now = time.time()
    cache_expired = (now - _cache_timestamp) > CACHE_TTL_SECONDS

    if force_refresh or cache_expired or not _keyword_cache:
        _refresh_cache(db)

    return _keyword_cache


def get_sorted_keywords(db: Session) -> List[Tuple[str, str, Optional[str]]]:
    """
    Get keywords as a list sorted longest-first for metadata matching.

    Args:
        db: SQLAlchemy database session

    Returns:
        List of (keyword, main_style, sub_style) tuples, sorted by keyword length descending.
        This ordering ensures "bingsjopolska" matches before "polska".
    """
    cache = get_keywords(db)
    return [(kw, main, sub) for kw, (main, sub) in cache.items()]


def invalidate_cache() -> None:
    """
    Manually invalidate the cache.
    Call this after admin creates/updates/deletes keywords.
    """
    global _keyword_cache, _cache_timestamp
    _keyword_cache = {}
    _cache_timestamp = 0
    log.info("cache_invalidated")


def _refresh_cache(db: Session) -> None:
    """Load keywords from database into cache."""
    global _keyword_cache, _cache_timestamp

    from app.core.models import StyleKeyword

    keywords = db.query(StyleKeyword).filter(
        StyleKeyword.is_active == True
    ).all()

    # Sort by keyword length (longest first)
    sorted_keywords = sorted(keywords, key=lambda k: len(k.keyword), reverse=True)

    _keyword_cache = {
        kw.keyword.lower(): (kw.main_style, kw.sub_style)
        for kw in sorted_keywords
    }

    _cache_timestamp = time.time()
    log.info("cache_refreshed", keyword_count=len(_keyword_cache))


def get_cache_info() -> dict:
    """
    Get cache statistics for debugging/admin.
    """
    global _keyword_cache, _cache_timestamp

    now = time.time()
    age = now - _cache_timestamp if _cache_timestamp > 0 else -1

    return {
        "size": len(_keyword_cache),
        "age_seconds": round(age, 1) if age >= 0 else None,
        "ttl_seconds": CACHE_TTL_SECONDS,
        "expires_in": round(CACHE_TTL_SECONDS - age, 1) if age >= 0 else None,
        "is_valid": age >= 0 and age < CACHE_TTL_SECONDS
    }
