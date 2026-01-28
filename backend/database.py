import os
import time
from typing import Any, Dict, List, Tuple

import firebase_admin
from firebase_admin import credentials, firestore
from google.cloud.firestore_v1.base_query import FieldFilter

from backend.config import (
  DEFAULT_CANDIDATE_LIMIT,
  DEFAULT_MIN_SIMILARITY,
  DEFAULT_RESULTS_LIMIT,
  EXACT_MATCH_BOOST_ENABLED,
  EXACT_MATCH_CASE_SENSITIVE,
  EXACT_MATCH_PENALTY_MULTIPLIER,
  FACETS_CACHE_TTL_SECONDS,
  FACETS_REFRESH_LIMIT,
  MAX_FACETS_PER_QUERY,
)
from backend.embeddings import (
  calculate_facet_similarity_detailed,
  check_exact_facet_match,
  encode_facets_from_tags,
  encode_user_facets,
)

# Initialize Firebase
# Priority order for credentials:
# 1. GOOGLE_APPLICATION_CREDENTIALS env var (for Cloud Run with mounted secret)
# 2. firebase-key.json in project root (for local dev and Docker)
# 3. ~/firebase-keys/kindred-histories-firebase-key.json (legacy local path)
# 4. service-account-key.json (fallback)

cred_path = None

# Check if already set via environment (Cloud Run secret mount)
if os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") and os.path.exists(
  os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
):
  cred_path = os.environ["GOOGLE_APPLICATION_CREDENTIALS"]
  print(f"Using GOOGLE_APPLICATION_CREDENTIALS from env: {cred_path}")
# Cloud Run secret mount path
elif os.path.exists("/secrets/firebase-key.json"):
  cred_path = "/secrets/firebase-key.json"
  os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
  print("Using Cloud Run secret mount: /secrets/firebase-key.json")
# Check project root (works in Docker and local dev)
elif os.path.exists("firebase-key.json"):
  cred_path = "firebase-key.json"
  os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
  print("Using firebase-key.json from project root")
# Legacy home directory path
elif os.path.exists(
  os.path.expanduser("~/firebase-keys/kindred-histories-firebase-key.json")
):
  cred_path = os.path.expanduser("~/firebase-keys/kindred-histories-firebase-key.json")
  os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
  print(f"Using legacy path: {cred_path}")
# Fallback
elif os.path.exists("service-account-key.json"):
  cred_path = "service-account-key.json"
  os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
  print("Using service-account-key.json fallback")

if not firebase_admin._apps:
  try:
    if cred_path:
      cred = credentials.Certificate(cred_path)
      firebase_admin.initialize_app(cred)
      print(f"Firebase initialized with credentials from {cred_path}")
    else:
      # Use Application Default Credentials (ADC) - works on Cloud Run
      # Must specify project ID since Cloud Run may be in a different GCP project
      firebase_project = os.environ.get("FIREBASE_PROJECT_ID", "kindred-histories")
      firebase_admin.initialize_app(options={"projectId": firebase_project})
      print(f"Firebase initialized with ADC for project: {firebase_project}")
  except Exception as e:
    print(f"Failed to initialize Firebase: {e}")

try:
  db = firestore.client()
  print("Connected to Firestore database: (default)")
except Exception as e:
  db = None
  print(f"Firestore client creation failed: {e}")

# Cache for facets (expires after configured TTL)
_facets_cache: Dict[str, List[str]] = {}
_facets_cache_time: float = 0


def _extract_facets_from_tags(tags: Dict[str, Any]) -> List[str]:
  """
  Extract and flatten all facet values from a tags dictionary.

  Args:
      tags: Dictionary with SocialModel fields (race, ethnicity, etc.)

  Returns:
      Deduplicated list of all facet values
  """
  facets = []

  for field in [
    "race",
    "ethnicity",
    "cultural_background",
    "location",
    "gender",
    "sexuality",
    "interests",
    "aspirations",
  ]:
    if field in tags and tags[field]:
      # Handle both list and single values
      field_values = tags[field] if isinstance(tags[field], list) else [tags[field]]
      facets.extend(field_values)

  # Deduplicate and filter out empty strings
  return list(set(f for f in facets if f))


def _extract_searchable_text(figure_data: Dict[str, Any]) -> str:
  """
  Extract all searchable text from a figure for exact matching.

  Combines profile narrative fields and tag values into a single string
  that can be searched for exact facet matches.

  Args:
      figure_data: Dictionary containing figure profile data

  Returns:
      Combined text from all searchable fields
  """
  parts = [
    figure_data.get("marginalization_context", ""),
    figure_data.get("challenges_faced", ""),
    figure_data.get("how_they_overcame", ""),
    figure_data.get("achievement", ""),
  ]

  # Also include tag values (race, ethnicity, location, etc.)
  tags = figure_data.get("tags", {})
  for field_values in tags.values():
    if isinstance(field_values, list):
      parts.extend(field_values)
    elif field_values:
      parts.append(str(field_values))

  return " ".join(filter(None, parts))


def save_figure(figure_data: Dict[str, Any], generate_embeddings: bool = True):
  """
  Save a historical figure to Firestore with semantic search support.

  Args:
      figure_data: Figure data including name, achievement, tags, etc.
      generate_embeddings: Whether to generate embeddings for facets (default True)
  """
  if not db:
    print("Database not initialized, skipping save.")
    return

  # Extract and flatten facets from tags, with rich sentence embeddings
  if "tags" in figure_data and isinstance(figure_data["tags"], dict):
    if generate_embeddings:
      print("  Generating embeddings with rich descriptions...")
      facets, facet_embeddings = encode_facets_from_tags(figure_data["tags"])
      figure_data["facets"] = facets
      figure_data["facet_embeddings"] = facet_embeddings
      print(f"  Embeddings generated for {len(facets)} facets")
    else:
      # Just extract facets without embeddings
      facets = _extract_facets_from_tags(figure_data["tags"])
      figure_data["facets"] = facets

  # Use name as document ID, sanitized
  doc_id = figure_data["name"].replace("/", "_").replace(".", "_")
  db.collection("historical_figures").document(doc_id).set(figure_data)

  facet_count = len(figure_data.get("facets", []))
  print(f"Saved figure: {figure_data['name']} ({facet_count} facets)")


def check_figure_exists(name: str) -> bool:
  if not db:
    return False
  doc_id = name.replace("/", "_").replace(".", "_")
  doc = db.collection("historical_figures").document(doc_id).get()
  return doc.exists


def get_all_figures() -> List[Dict[str, Any]]:
  if not db:
    return []
  docs = db.collection("historical_figures").stream()
  return [doc.to_dict() for doc in docs]


def query_by_facets_exact(
  selected_facets: List[str], limit: int = DEFAULT_RESULTS_LIMIT
) -> List[Dict[str, Any]]:
  """
  Query figures by exact facet matching using Firestore's array-contains-any.

  Args:
      selected_facets: List of facet values to match (ANY match, not ALL)
      limit: Maximum number of results

  Returns:
      List of figure dictionaries where at least one facet matches

  Note:
      Firestore limits array-contains-any to 30 values max.
  """
  if not db:
    return []

  if not selected_facets:
    # Return all if no facets selected
    docs = db.collection("historical_figures").limit(limit).stream()
  else:
    # Limit to first N facets (Firestore restriction)
    facets_to_query = selected_facets[:MAX_FACETS_PER_QUERY]
    docs = (
      db.collection("historical_figures")
      .where(filter=FieldFilter("facets", "array_contains_any", facets_to_query))
      .limit(limit)
      .stream()
    )

  return [doc.to_dict() for doc in docs]


def query_by_facets_semantic(
  selected_facets: List[str],
  limit: int = DEFAULT_RESULTS_LIMIT,
  candidate_limit: int = DEFAULT_CANDIDATE_LIMIT,
  min_similarity: float = DEFAULT_MIN_SIMILARITY,
) -> List[Tuple[Dict[str, Any], float, Dict[str, float]]]:
  """
  Query figures by semantic facet matching with similarity scores.

  Strategy:
  1. Use exact matching to get candidates (fast Firestore query)
  2. Calculate semantic similarity for each candidate
  3. Rank by similarity score
  4. Return top results

  Args:
      selected_facets: User's selected facet values
      limit: Number of results to return
      candidate_limit: Max candidates to fetch from Firestore
      min_similarity: Minimum similarity threshold (0-1)

  Returns:
      List of (figure_dict, similarity_score, facet_scores) tuples, sorted by score descending
      where facet_scores is a dict mapping each selected facet to its similarity score

  Example:
      User selects: ["Mexican", "neuroscience", "Atlanta, Georgia"]
      Figure has: ["Mexican", "biology", "Texas"]
      Returns: (figure_data, 0.85, {
          "Mexican": 1.0,
          "neuroscience": 0.7,
          "Atlanta, Georgia": 0.6
      })
  """
  if not db:
    return []

  if not selected_facets:
    # No facets selected, return all without scoring
    docs = db.collection("historical_figures").limit(limit).stream()
    return [(doc.to_dict(), 1.0, {}) for doc in docs]

  print(
    f"Query: {len(selected_facets)} facets selected: {selected_facets[:5]}{'...' if len(selected_facets) > 5 else ''}"
  )

  # Step 1: Get candidates via exact matching (or all if needed)
  # Use broader query to get more candidates for semantic matching
  try:
    if len(selected_facets) <= 30:
      candidates_query = (
        db.collection("historical_figures")
        .where(filter=FieldFilter("facets", "array_contains_any", selected_facets))
        .limit(candidate_limit)
      )
      candidates = list(candidates_query.stream())

      # If no exact matches found, fall back to fetching all figures
      # This enables true semantic matching even when no exact facets match
      if len(candidates) == 0:
        print(
          "  No exact matches found, falling back to all figures for semantic scoring"
        )
        candidates_query = db.collection("historical_figures").limit(candidate_limit)
        candidates = list(candidates_query.stream())
    else:
      # Too many facets for array_contains_any, fetch all and score
      candidates_query = db.collection("historical_figures").limit(candidate_limit)
      candidates = list(candidates_query.stream())
  except Exception as e:
    print(f"  [WARNING] Firestore query failed: {e}, returning empty results")
    return []

  print(f"  Fetched {len(candidates)} candidates")

  if not candidates:
    return []

  # Step 2: Build facet-to-field mapping and encode user's selected facets
  print("  Building facet-to-field mapping...")
  all_facets_by_field = get_all_facets()
  facet_to_field = {}
  for field, values in all_facets_by_field.items():
    for value in values:
      facet_to_field[value] = field

  print("  Encoding user facets...")
  user_facets_embeddings = encode_user_facets(selected_facets, facet_to_field)

  # Step 3: Score each candidate
  print("  Calculating similarities...")
  scored_results = []

  skipped_incompatible = 0
  for doc in candidates:
    data = doc.to_dict()
    facet_embeddings = data.get("facet_embeddings", {})

    if not facet_embeddings:
      # No embeddings stored, skip (shouldn't happen with new saves)
      continue

    # Calculate similarity with per-facet breakdown
    try:
      similarity, facet_scores = calculate_facet_similarity_detailed(
        user_facets_embeddings, facet_embeddings
      )
    except ValueError:
      # Dimension mismatch - figure has old embeddings, skip
      skipped_incompatible += 1
      continue

    # Apply exact-match boosting if enabled
    if EXACT_MATCH_BOOST_ENABLED and facet_scores:
      searchable_text = _extract_searchable_text(data)
      boosted_facet_scores = {}
      for facet, score in facet_scores.items():
        if check_exact_facet_match(facet, searchable_text, EXACT_MATCH_CASE_SENSITIVE):
          boosted_facet_scores[facet] = score  # exact match: keep original score
        else:
          boosted_facet_scores[facet] = (
            score * EXACT_MATCH_PENALTY_MULTIPLIER
          )  # no match: penalize
      facet_scores = boosted_facet_scores
      # Recalculate overall score as mean of boosted facet scores
      similarity = sum(facet_scores.values()) / len(facet_scores)

    if similarity >= min_similarity:
      scored_results.append((data, similarity, facet_scores))

  if skipped_incompatible > 0:
    print(f"  Skipped {skipped_incompatible} figures with incompatible embeddings")

  print(f"  Scored {len(scored_results)} figures above threshold {min_similarity}")

  # Step 4: Sort by similarity (descending) and limit
  scored_results.sort(key=lambda x: x[1], reverse=True)
  results = scored_results[:limit]

  print(f"  Returning {len(results)} results (min_sim={min_similarity})")

  return results


def get_all_facets() -> Dict[str, List[str]]:
  """
  Get all unique facets from the database, organized by field.
  Results are cached for 5 minutes to prevent Firestore query timeouts.

  Returns:
      Dictionary of {field_name: [sorted_unique_values]}

  Example:
      {
          "race": ["Asian", "Black", "White"],
          "ethnicity": ["Hispanic", "Mexican"],
          "interests": ["neuroscience", "compassion"],
          ...
      }
  """
  global _facets_cache, _facets_cache_time

  # Return cached result if still valid
  if _facets_cache and (time.time() - _facets_cache_time) < FACETS_CACHE_TTL_SECONDS:
    return _facets_cache

  if not db:
    return {}

  print("  Refreshing facets cache from Firestore...")

  try:
    # Limit the query to prevent timeouts
    docs = db.collection("historical_figures").limit(FACETS_REFRESH_LIMIT).stream()

    # Aggregate all facets by field
    facet_sets = {}

    for doc in docs:
      data = doc.to_dict()
      tags = data.get("tags", {})

      for field in [
        "race",
        "ethnicity",
        "cultural_background",
        "location",
        "gender",
        "sexuality",
        "interests",
        "aspirations",
      ]:
        if field in tags and tags[field]:
          if field not in facet_sets:
            facet_sets[field] = set()

          # Handle both list and single values
          field_values = tags[field] if isinstance(tags[field], list) else [tags[field]]
          facet_sets[field].update(field_values)

    # Convert sets to sorted lists
    facet_dict = {field: sorted(list(values)) for field, values in facet_sets.items()}

    # Cache the result
    _facets_cache = facet_dict
    _facets_cache_time = time.time()
  except Exception as e:
    print(f"  [WARNING] Firestore query failed in get_all_facets: {e}")
    # Return cached result if available, otherwise empty dict
    return _facets_cache if _facets_cache else {}

  return facet_dict
