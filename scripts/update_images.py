#!/usr/bin/env python3
"""
Script to update images for all historical figures in the database.

Uses the improved descriptive query approach (name + achievement/interest)
to get more relevant images for figures with ambiguous names.

Usage:
    uv run python scripts/update_images.py [--dry-run] [--limit N]
"""

import argparse
import sys
import time
from pathlib import Path

from dotenv import load_dotenv

# Add parent directory to path so we can import from backend
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
load_dotenv(project_root / ".env")

from backend.database import db, get_all_figures  # noqa: E402
from backend.tools import search_images_google  # noqa: E402

IMAGES_TO_SEARCH = 4


def build_image_query(figure: dict) -> str:
  """Build a descriptive image search query for a figure."""
  name = figure.get("name", "")
  query_parts = [name]

  # Add achievement or interests for disambiguation
  achievement = figure.get("achievement", "")
  if achievement:
    # Extract key descriptor (first sentence fragment, up to 50 chars)
    short_achievement = achievement.split(".")[0][:50].strip()
    query_parts.append(short_achievement)
  elif figure.get("tags", {}).get("interests"):
    interests = figure["tags"]["interests"]
    if interests:
      query_parts.append(interests[0])

  return " ".join(query_parts)


def update_figure_image(figure: dict, dry_run: bool = False) -> tuple[bool, str]:
  """
  Update the image for a single figure.

  Returns:
      (success, message) tuple
  """
  name = figure.get("name", "Unknown")
  old_image = figure.get("image_url")

  # Build descriptive query
  image_query = build_image_query(figure)

  if dry_run:
    return True, f"[DRY RUN] Would search: '{image_query}'"

  # Search for new image
  validated_images = search_images_google(image_query, num_images=IMAGES_TO_SEARCH)

  if not validated_images:
    return False, "No valid images found"

  new_image = validated_images[0]

  # Update in Firestore
  doc_id = name.replace("/", "_").replace(".", "_")
  db.collection("historical_figures").document(doc_id).update({"image_url": new_image})

  if old_image == new_image:
    return True, "Image unchanged"
  elif old_image:
    return True, f"Updated image (was: {old_image[:50]}...)"
  else:
    return True, "Added new image"


def main():
  parser = argparse.ArgumentParser(
    description="Update images for historical figures in the database"
  )
  parser.add_argument(
    "--dry-run",
    action="store_true",
    help="Show what would be done without making changes",
  )
  parser.add_argument(
    "--limit",
    type=int,
    default=None,
    help="Limit number of figures to process",
  )
  parser.add_argument(
    "--name",
    type=str,
    default=None,
    help="Update only a specific figure by name",
  )
  parser.add_argument(
    "--missing-only",
    action="store_true",
    help="Only update figures without images",
  )
  args = parser.parse_args()

  if not db:
    print("ERROR: Database not initialized. Check Firebase credentials.")
    sys.exit(1)

  print("Fetching all figures from database...")
  figures = get_all_figures()
  print(f"Found {len(figures)} figures")

  # Filter by name if specified
  if args.name:
    figures = [f for f in figures if args.name.lower() in f.get("name", "").lower()]
    print(f"Filtered to {len(figures)} figures matching '{args.name}'")

  # Filter to missing-only if specified
  if args.missing_only:
    figures = [f for f in figures if not f.get("image_url")]
    print(f"Filtered to {len(figures)} figures without images")

  # Apply limit
  if args.limit:
    figures = figures[: args.limit]
    print(f"Limited to {len(figures)} figures")

  if not figures:
    print("No figures to process")
    return

  print()
  print("=" * 60)

  success_count = 0
  failure_count = 0

  for i, figure in enumerate(figures, 1):
    name = figure.get("name", "Unknown")
    print(f"\n[{i}/{len(figures)}] {name}")

    try:
      success, message = update_figure_image(figure, dry_run=args.dry_run)
      print(f"  {message}")
      if success:
        success_count += 1
      else:
        failure_count += 1
    except Exception as e:
      print(f"  ERROR: {e}")
      failure_count += 1

    # Rate limiting to avoid API throttling
    if not args.dry_run and i < len(figures):
      time.sleep(0.5)

  print()
  print("=" * 60)
  print(f"Complete: {success_count} succeeded, {failure_count} failed")


if __name__ == "__main__":
  main()
