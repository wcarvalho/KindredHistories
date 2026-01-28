"""
Compute embeddings for all historical figures in Firestore.

This script can be run anytime to recompute embeddings, e.g.:
- After changing the embedding model
- After modifying how figure descriptions are generated
- To migrate from old embeddings to new ones

Usage:
    uv run python -m backend.compute_embeddings           # Process all
    uv run python -m backend.compute_embeddings --debug   # Process only 3 figures
    uv run python -m backend.compute_embeddings --batch-size 100  # Custom batch size
"""

import argparse
import os

import firebase_admin
from dotenv import load_dotenv
from firebase_admin import credentials, firestore

from backend.embeddings import (
  FIELD_TEMPLATES,
  format_facet_for_embedding,
  get_embedding_model,
)

load_dotenv()


def init_firestore():
  """Initialize Firestore connection."""
  cred_path = os.path.expanduser("~/firebase-keys/kindred-histories-firebase-key.json")

  if os.path.exists("/secrets/firebase-key.json"):
    cred_path = "/secrets/firebase-key.json"
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
  elif os.path.exists(cred_path):
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
  elif os.path.exists("firebase-key.json"):
    cred_path = "firebase-key.json"
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path
  elif os.path.exists("service-account-key.json"):
    cred_path = "service-account-key.json"
    os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = cred_path

  if not firebase_admin._apps:
    cred = credentials.Certificate(cred_path)
    firebase_admin.initialize_app(cred)
    print(f"Firebase initialized with credentials from {cred_path}")

  return firestore.client()


def extract_facets_from_tags(tags: dict) -> list[tuple[str, str, str]]:
  """
  Extract (field, value, description) tuples from tags dict.

  Returns:
      List of (field, raw_value, formatted_description) tuples
  """
  if not tags:
    return []

  facet_tuples = []
  seen_values = set()

  for field in FIELD_TEMPLATES.keys():
    if field in tags and tags[field]:
      values = tags[field] if isinstance(tags[field], list) else [tags[field]]
      for value in values:
        if value and value not in seen_values:
          description = format_facet_for_embedding(field, value)
          facet_tuples.append((field, value, description))
          seen_values.add(value)

  return facet_tuples


def compute_all_embeddings(debug: bool = False, batch_size: int = 64):
  """
  Fetch all figures from Firestore and recompute their embeddings using batch processing.

  Args:
      debug: If True, only process 3 figures for testing
      batch_size: Number of texts to encode in each batch (default 64)
  """
  print("Initializing Firestore...")
  db = init_firestore()

  print("Loading embedding model...")
  model = get_embedding_model()
  print(f"Model loaded: {model.get_sentence_embedding_dimension()} dimensions")

  print("Fetching all historical figures...")
  docs = list(db.collection("historical_figures").stream())
  print(f"Found {len(docs)} figures")

  if debug:
    docs = docs[:3]
    print(f"DEBUG MODE: Processing only {len(docs)} figures")

  # Phase 1: Extract all facets and build batch
  print("\nPhase 1: Extracting facets...")
  figures_data = []  # [(doc_id, name, [(field, value, desc), ...])]

  for doc in docs:
    doc_data = doc.to_dict()
    name = doc_data.get("name", doc.id)
    tags = doc_data.get("tags", {})
    facet_tuples = extract_facets_from_tags(tags)
    figures_data.append((doc.id, name, facet_tuples))

  # Collect all unique descriptions for batch encoding
  all_descriptions = []
  desc_to_idx = {}  # description -> index in all_descriptions

  for _, _, facet_tuples in figures_data:
    for _, _, desc in facet_tuples:
      if desc not in desc_to_idx:
        desc_to_idx[desc] = len(all_descriptions)
        all_descriptions.append(desc)

  print(f"Total unique facet descriptions: {len(all_descriptions)}")

  # Phase 2: Batch encode all descriptions
  print(
    f"\nPhase 2: Encoding {len(all_descriptions)} descriptions (batch_size={batch_size})..."
  )

  all_embeddings = []
  for i in range(0, len(all_descriptions), batch_size):
    batch = all_descriptions[i : i + batch_size]
    embeddings = model.encode(batch, convert_to_numpy=True, show_progress_bar=False)
    all_embeddings.extend(embeddings)
    print(
      f"  Encoded {min(i + batch_size, len(all_descriptions))}/{len(all_descriptions)}",
      flush=True,
    )

  # Phase 3: Write to Firestore (individual writes - embeddings too large for batching)
  print("\nPhase 3: Writing to Firestore...", flush=True)
  updated = 0
  deleted = 0
  errors = 0

  for i, (doc_id, name, facet_tuples) in enumerate(figures_data, 1):
    doc_ref = db.collection("historical_figures").document(doc_id)

    try:
      if not facet_tuples:
        doc_ref.delete()
        deleted += 1
      else:
        facets = [value for _, value, _ in facet_tuples]
        facet_embeddings = {
          value: all_embeddings[desc_to_idx[desc]].tolist()
          for _, value, desc in facet_tuples
        }
        doc_ref.update({"facets": facets, "facet_embeddings": facet_embeddings})
        updated += 1

      if i % 50 == 0:
        print(f"  Progress: {i}/{len(figures_data)} figures", flush=True)
    except Exception as e:
      errors += 1
      print(f"  Error writing {name[:40]}...: {e}", flush=True)

  print("\n" + "=" * 60)
  print("SUMMARY")
  print("=" * 60)
  print(f"Total figures: {len(docs)}")
  print(f"Updated: {updated}")
  print(f"Deleted: {deleted}")
  print(f"Errors: {errors}")


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description="Compute embeddings for historical figures"
  )
  parser.add_argument(
    "--debug", action="store_true", help="Only process 3 figures for testing"
  )
  parser.add_argument(
    "--batch-size",
    type=int,
    default=64,
    help="Batch size for encoding (default: 64)",
  )
  args = parser.parse_args()

  compute_all_embeddings(debug=args.debug, batch_size=args.batch_size)
