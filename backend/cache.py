"""Search cache management for global query optimization."""

import hashlib
from datetime import datetime, timedelta
from typing import Any, Dict, List, Optional

from firebase_admin import firestore

from backend.config import SEARCH_CACHE_TTL_DAYS
from backend.database import db


def normalize_search_text(text: str) -> str:
  """Normalize text for consistent cache keys."""
  return " ".join(text.lower().strip().split())


def get_cache_key(text: str) -> str:
  """Generate SHA-256 hash for cache key."""
  normalized = normalize_search_text(text)
  return hashlib.sha256(normalized.encode()).hexdigest()


def get_cached_search(text: str) -> Optional[Dict[str, Any]]:
  """
  Check if search text exists in cache and is not expired.

  Returns:
    {
      "social_model": {...},
      "figure_names": [...],
      "facets": [...]
    }
    or None if cache miss or expired
  """
  if not db:
    return None

  cache_key = get_cache_key(text)
  doc = db.collection("search_cache").document(cache_key).get()

  if not doc.exists:
    return None

  data = doc.to_dict()

  # Check expiration
  expires_at = data.get("expires_at")
  if expires_at and expires_at.timestamp() < datetime.now().timestamp():
    # Expired, delete it
    db.collection("search_cache").document(cache_key).delete()
    return None

  # Update hit stats
  db.collection("search_cache").document(cache_key).update(
    {"hit_count": firestore.Increment(1), "last_hit": firestore.SERVER_TIMESTAMP}
  )

  return {
    "social_model": _unflatten_social_model(data.get("social_model", {})),
    "figure_names": data.get("figure_names", []),
    "facets": data.get("facets", []),
  }


def _flatten_social_model(social_model: Dict[str, Any]) -> Dict[str, str]:
  """Convert list values to comma-separated strings for Firestore."""
  flattened = {}
  for key, value in social_model.items():
    if isinstance(value, list):
      flattened[key] = ", ".join(value) if value else ""
    else:
      flattened[key] = value if value else ""
  return flattened


def _unflatten_social_model(social_model: Dict[str, str]) -> Dict[str, List[str]]:
  """Convert comma-separated strings back to lists."""
  unflattened = {}
  for key, value in social_model.items():
    if isinstance(value, str) and value:
      unflattened[key] = [item.strip() for item in value.split(",")]
    else:
      unflattened[key] = []
  return unflattened


def save_to_cache(
  text: str, social_model: Dict[str, Any], figure_names: List[str], facets: List[str]
):
  """Save search results to cache with configured TTL."""
  if not db:
    return

  cache_key = get_cache_key(text)
  now = datetime.now()
  expires_at = now + timedelta(days=SEARCH_CACHE_TTL_DAYS)

  cache_entry = {
    "text_hash": cache_key,
    "normalized_text": normalize_search_text(text),
    "social_model": _flatten_social_model(social_model),
    "figure_names": figure_names,
    "facets": facets,
    "created_at": now,
    "expires_at": expires_at,
    "hit_count": 0,
    "last_hit": now,
  }

  db.collection("search_cache").document(cache_key).set(cache_entry)
  print(f"[CACHE] Saved search cache: {cache_key[:8]}... ({len(figure_names)} figures)")
