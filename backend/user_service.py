"""User profile and search history management."""

from typing import Any, Dict, List, Optional

from firebase_admin import firestore

from backend.config import USER_SEARCH_HISTORY_LIMIT
from backend.database import db


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


def save_or_update_user(user_info: dict):
  """Create or update user profile from Firebase auth token."""
  if not db:
    return

  user_data = {
    "uid": user_info["uid"],
    "email": user_info.get("email"),
    "display_name": user_info.get("name"),
    "photo_url": user_info.get("picture"),
    "last_login": firestore.SERVER_TIMESTAMP,
  }

  # Use set with merge to create or update
  db.collection("users").document(user_info["uid"]).set(user_data, merge=True)


def save_user_search(
  user_id: str,
  search_text: str,
  social_model: Dict[str, Any],
  figure_names: List[str],
  facets: List[str],
) -> Optional[str]:
  """Save a search to user's search history.

  Returns:
      The document ID of the saved search, or None if database unavailable.
  """
  if not db:
    return None

  search_entry = {
    "user_id": user_id,
    "search_text": search_text,
    "social_model": _flatten_social_model(social_model),
    "figure_names": figure_names,
    "facets": facets,
    "timestamp": firestore.SERVER_TIMESTAMP,
  }

  _, doc_ref = db.collection("user_searches").add(search_entry)
  print(f"[USER] Saved search history for user {user_id[:8]}...")
  return doc_ref.id


def update_user_search(
  search_id: str, figure_names: List[str], append: bool = False
) -> bool:
  """Update an existing search with discovered figure names.

  Args:
      search_id: The document ID of the search to update.
      figure_names: List of discovered figure names.
      append: If True, append to existing names instead of replacing.

  Returns:
      True if update succeeded, False otherwise.
  """
  if not db or not search_id:
    return False

  try:
    doc_ref = db.collection("user_searches").document(search_id)

    if append:
      # Use arrayUnion to append new names without duplicates
      doc_ref.update(
        {
          "figure_names": firestore.ArrayUnion(figure_names),
          "updated_at": firestore.SERVER_TIMESTAMP,
        }
      )
    else:
      doc_ref.update(
        {
          "figure_names": figure_names,
          "updated_at": firestore.SERVER_TIMESTAMP,
        }
      )
    print(
      f"[USER] Updated search {search_id[:8]}... with {len(figure_names)} figures (append={append})"
    )
    return True
  except Exception as e:
    print(f"[USER] Failed to update search {search_id}: {e}")
    return False


def get_user_searches(
  user_id: str, limit: int = USER_SEARCH_HISTORY_LIMIT
) -> List[Dict[str, Any]]:
  """Get user's search history, most recent first."""
  if not db:
    return []

  docs = (
    db.collection("user_searches")
    .where("user_id", "==", user_id)
    .order_by("timestamp", direction=firestore.Query.DESCENDING)
    .limit(limit)
    .stream()
  )

  searches = []
  for doc in docs:
    data = doc.to_dict()
    data["id"] = doc.id
    # Unflatten social_model back to list format
    if "social_model" in data:
      data["social_model"] = _unflatten_social_model(data["social_model"])
    searches.append(data)

  return searches


def delete_user_search(search_id: str, user_id: str) -> bool:
  """Delete a user's search by ID. Returns True if deleted, False if not found or unauthorized."""
  if not db:
    return False

  # Get the search document
  doc_ref = db.collection("user_searches").document(search_id)
  doc = doc_ref.get()

  if not doc.exists:
    return False

  # Verify ownership
  data = doc.to_dict()
  if data.get("user_id") != user_id:
    return False

  # Delete the document
  doc_ref.delete()
  print(f"[USER] Deleted search {search_id} for user {user_id[:8]}...")
  return True


def delete_all_user_searches(user_id: str) -> int:
  """Delete all searches for a user. Returns count of deleted searches."""
  if not db:
    return 0

  # Get all searches for this user
  docs = db.collection("user_searches").where("user_id", "==", user_id).stream()

  deleted_count = 0
  for doc in docs:
    doc.reference.delete()
    deleted_count += 1

  if deleted_count > 0:
    print(f"[USER] Deleted {deleted_count} searches for user {user_id[:8]}...")

  return deleted_count
