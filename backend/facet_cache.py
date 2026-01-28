"""Thread-safe in-memory cache for facet extraction results.

Caches the expensive LLM-based facet extraction to avoid redundant calls
for repeated identical queries.
"""

import hashlib
import threading
import time
from typing import Any, Dict, List, Optional

# Cache configuration
CACHE_TTL_SECONDS = 3600  # 1 hour
MAX_CACHE_ENTRIES = 1000

# Thread-safe cache storage
_cache: Dict[str, Dict[str, Any]] = {}
_cache_lock = threading.Lock()


def _normalize_text(text: str) -> str:
  """Normalize text for cache key generation."""
  return text.strip().lower()


def _make_cache_key(text: str) -> str:
  """Create SHA-256 hash key from normalized text."""
  normalized = _normalize_text(text)
  return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _cleanup_expired_entries() -> None:
  """Remove expired entries from cache. Must be called with lock held."""
  now = time.time()
  expired_keys = [
    key for key, entry in _cache.items() if now - entry["timestamp"] > CACHE_TTL_SECONDS
  ]
  for key in expired_keys:
    del _cache[key]


def _evict_oldest_if_needed() -> None:
  """Evict oldest entries if cache exceeds max size. Must be called with lock held."""
  if len(_cache) >= MAX_CACHE_ENTRIES:
    # Sort by timestamp and remove oldest 10%
    sorted_keys = sorted(_cache.keys(), key=lambda k: _cache[k]["timestamp"])
    num_to_remove = max(1, len(sorted_keys) // 10)
    for key in sorted_keys[:num_to_remove]:
      del _cache[key]


def get_cached_facets(text: str) -> Optional[Dict[str, Any]]:
  """Retrieve cached facets for the given text.

  Args:
      text: The user's description text

  Returns:
      Cached result dict with 'facets' and 'social_model' keys,
      or None if not found/expired
  """
  key = _make_cache_key(text)

  with _cache_lock:
    entry = _cache.get(key)

    if entry is None:
      print(f"[FACET_CACHE] Miss for: {text[:50]}...")
      return None

    # Check expiration
    if time.time() - entry["timestamp"] > CACHE_TTL_SECONDS:
      del _cache[key]
      print(f"[FACET_CACHE] Expired for: {text[:50]}...")
      return None

    print(f"[FACET_CACHE] Hit for: {text[:50]}...")
    return entry["data"]


def save_facets_to_cache(
  text: str, facets: List[str], social_model: Dict[str, List[str]]
) -> None:
  """Save extracted facets to cache.

  Args:
      text: The user's description text
      facets: List of extracted facet strings
      social_model: Dictionary of facet categories to values
  """
  key = _make_cache_key(text)

  with _cache_lock:
    # Cleanup and eviction
    _cleanup_expired_entries()
    _evict_oldest_if_needed()

    _cache[key] = {
      "timestamp": time.time(),
      "data": {"facets": facets, "social_model": social_model},
    }

    print(f"[FACET_CACHE] Saved for: {text[:50]}... (cache size: {len(_cache)})")


def clear_cache() -> None:
  """Clear all cached entries."""
  with _cache_lock:
    _cache.clear()
    print("[FACET_CACHE] Cache cleared")


def get_cache_stats() -> Dict[str, int]:
  """Get cache statistics."""
  with _cache_lock:
    return {
      "entries": len(_cache),
      "max_entries": MAX_CACHE_ENTRIES,
      "ttl_seconds": CACHE_TTL_SECONDS,
    }
