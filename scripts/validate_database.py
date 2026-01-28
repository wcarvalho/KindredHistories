#!/usr/bin/env python3
"""
Database Validation Script for Kindred Histories

This script validates all historical figures in the Firestore database:
1. Checks that all required fields are present and non-empty
2. Validates that image URLs are accessible and point to valid images
3. Optionally fixes broken image URLs by searching for new ones

Usage:
  # Check only (no modifications)
  uv run python validate_database.py

  # Check and fix broken images immediately
  uv run python validate_database.py --fix

  # Check a specific figure by name
  uv run python validate_database.py --name "Ralph Abernathy"

  # Check and fix a specific figure
  uv run python validate_database.py --name "Ralph Abernathy" --fix

  # Use more workers for faster processing (default: 10)
  uv run python validate_database.py --fix --workers 20

  # Detailed output
  uv run python validate_database.py --verbose
"""

import argparse
import os
import threading
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Dict, List, Tuple

from dotenv import load_dotenv

from backend.database import get_all_figures, save_figure
from backend.tools import search_images_google, validate_image_url

# Load environment variables from .env file
load_dotenv()

# Thread-safe printing
print_lock = threading.Lock()


def thread_safe_print(*args, **kwargs):
  """Thread-safe print function."""
  with print_lock:
    print(*args, **kwargs)


def check_required_fields(figure: Dict[str, Any]) -> Tuple[bool, List[str]]:
  """
  Check if a figure has all required fields with non-empty values.

  Required fields:
    - name
    - marginalization_context
    - challenges_faced
    - how_they_overcame
    - achievement
    - tags (with at least one demographic field: race, ethnicity, or cultural_background)

  Args:
      figure: Figure dictionary from database

  Returns:
      (is_valid, missing_fields) tuple
  """
  missing = []

  # Check basic text fields
  required_text_fields = [
    "name",
    "marginalization_context",
    "challenges_faced",
    "how_they_overcame",
    "achievement",
  ]

  for field in required_text_fields:
    value = figure.get(field)
    if not value or (isinstance(value, str) and not value.strip()):
      missing.append(field)

  # Check tags/demographics
  tags = figure.get("tags", {})
  if not tags or not isinstance(tags, dict):
    missing.append("tags")
  else:
    # Need at least one demographic field
    has_demographics = False
    for demo_field in ["race", "ethnicity", "cultural_background"]:
      demo_value = tags.get(demo_field)
      if demo_value:
        if isinstance(demo_value, list) and len(demo_value) > 0:
          has_demographics = True
          break
        elif isinstance(demo_value, str) and demo_value.strip():
          has_demographics = True
          break

    if not has_demographics:
      missing.append("demographics (race/ethnicity/cultural_background)")

  return len(missing) == 0, missing


def validate_figure(
  figure: Dict[str, Any], verbose: bool = False
) -> Tuple[bool, Dict[str, Any]]:
  """
  Validate a single figure for completeness and image validity.

  Args:
      figure: Figure dictionary from database
      verbose: Print detailed info

  Returns:
      (is_valid, issues) tuple where issues contains:
        - missing_fields: list of missing required fields
        - image_status: "valid", "invalid", "missing", or None
        - image_url: the image URL (if present)
  """
  name = figure.get("name", "Unknown")
  issues = {"name": name, "missing_fields": [], "image_status": None, "image_url": None}

  # Check required fields
  is_complete, missing_fields = check_required_fields(figure)
  issues["missing_fields"] = missing_fields

  # Check image URL
  image_url = figure.get("image_url")
  if not image_url:
    issues["image_status"] = "missing"
  else:
    issues["image_url"] = image_url
    if verbose:
      thread_safe_print(f"  Validating image URL: {image_url[:80]}...")

    if validate_image_url(image_url):
      issues["image_status"] = "valid"
      if verbose:
        thread_safe_print("    ✓ Image URL is valid")
    else:
      issues["image_status"] = "invalid"
      if verbose:
        thread_safe_print("    ✗ Image URL is invalid or inaccessible")

  is_valid = is_complete and issues["image_status"] == "valid"
  return is_valid, issues


def fix_broken_image(figure: Dict[str, Any], verbose: bool = False) -> Tuple[bool, str]:
  """
  Attempt to fix a broken image URL by searching for a new one.

  Strategy:
  - Get 10 candidate images from Google Image Search
  - Validate each candidate URL individually
  - Use the first one that passes validation
  - This increases success rate since first result often fails

  Args:
      figure: Figure dictionary from database
      verbose: Print detailed info

  Returns:
      (success, reason) tuple - success is True if fixed, reason explains failure
  """
  name = figure.get("name", "Unknown")

  if verbose:
    thread_safe_print(f"  Searching for new image for {name}...")

  try:
    # Get 10 candidate images (already pre-validated by search_images_google)
    candidate_images = search_images_google(name, num_images=10)

    if not candidate_images or len(candidate_images) == 0:
      reason = "Google Image Search returned no images"
      if verbose:
        thread_safe_print(f"    ✗ {reason}")
      return False, reason

    if verbose:
      thread_safe_print(f"    Found {len(candidate_images)} candidate images, validating each...")

    # Try each candidate until we find one that works
    for i, candidate_url in enumerate(candidate_images, 1):
      if verbose:
        thread_safe_print(f"    Trying candidate {i}/{len(candidate_images)}: {candidate_url[:60]}...")

      # Double-check validation (images can become invalid quickly)
      if validate_image_url(candidate_url):
        # This one works! Use it.
        figure["image_url"] = candidate_url

        # Save updated figure
        save_figure(figure, generate_embeddings=False)  # Don't regenerate embeddings

        if verbose:
          thread_safe_print(f"    ✓ Fixed with candidate {i}: {candidate_url[:80]}...")
        return True, f"Fixed successfully with candidate {i}/{len(candidate_images)}"
      else:
        if verbose:
          thread_safe_print(f"      ✗ Candidate {i} failed validation")

    # None of the candidates worked
    reason = f"All {len(candidate_images)} candidate images failed validation"
    if verbose:
      thread_safe_print(f"    ✗ {reason}")
    return False, reason

  except Exception as e:
    reason = f"Error during fix attempt: {str(e)}"
    if verbose:
      thread_safe_print(f"    ✗ {reason}")
    return False, reason


def process_figure(
  figure: Dict[str, Any], index: int, total: int, args, show_index: bool = True
) -> Dict[str, Any]:
  """
  Process a single figure: validate and optionally fix.
  Returns a result dictionary with validation status and fix results.
  """
  name = figure.get("name", "Unknown")

  # Show progress
  if show_index:
    thread_safe_print(f"{index}/{total}. {name}")
  else:
    thread_safe_print(f"Checking: {name}")

  # Validate
  is_valid, issues = validate_figure(figure, verbose=args.verbose)

  result = {
    "name": name,
    "is_valid": is_valid,
    "issues": issues,
    "fixed": False,
    "fix_failed": False,
    "fix_failure_reason": None,
    "original_image_url": issues.get("image_url"),
  }

  if is_valid:
    thread_safe_print(f"  ✓ Valid\n")
  else:
    # Print issues
    thread_safe_print(f"  ✗ Invalid")
    if issues["missing_fields"]:
      thread_safe_print(f"    Missing fields: {', '.join(issues['missing_fields'])}")
    if issues["image_status"] == "missing":
      thread_safe_print(f"    Image: Missing")
      if issues["image_url"]:
        thread_safe_print(f"      URL: {issues['image_url'][:80]}...")
    elif issues["image_status"] == "invalid":
      thread_safe_print(f"    Image: Invalid/Broken URL")
      if issues["image_url"]:
        thread_safe_print(f"      URL: {issues['image_url'][:80]}...")

    # Fix image immediately if requested and image is the problem
    if args.fix and issues["image_status"] in ["invalid", "missing"]:
      thread_safe_print(f"    🔧 Attempting to fix image...")
      success, reason = fix_broken_image(figure, verbose=args.verbose)
      if success:
        result["fixed"] = True
        thread_safe_print(f"    ✅ Image fixed!")
      else:
        result["fix_failed"] = True
        result["fix_failure_reason"] = reason
        thread_safe_print(f"    ❌ Could not fix image")

    thread_safe_print()

  return result


def main():
  parser = argparse.ArgumentParser(
    description="Validate historical figures in the database"
  )
  parser.add_argument(
    "--fix",
    action="store_true",
    help="Attempt to fix broken image URLs immediately when found",
  )
  parser.add_argument(
    "--verbose", "-v", action="store_true", help="Print detailed validation info"
  )
  parser.add_argument(
    "--name",
    type=str,
    help="Check a specific figure by name (e.g., 'Ralph Abernathy')",
  )
  parser.add_argument(
    "--workers",
    type=int,
    default=10,
    help="Number of parallel workers for validation (default: 10)",
  )
  args = parser.parse_args()

  print("=" * 60)
  print("Kindred Histories - Database Validation")
  print("=" * 60)
  print()

  # Check if API keys are configured
  if not os.getenv("GOOGLE_CSE_API_KEY") or not os.getenv("GOOGLE_CSE_ID"):
    print("⚠️  Warning: GOOGLE_CSE_API_KEY or GOOGLE_CSE_ID not configured")
    if args.fix:
      raise RuntimeError("Cannot fix broken images without Google API keys")

  # Fetch figures
  if args.name:
    # Check specific figure
    print(f"Fetching figure: {args.name}...")
    all_figures = get_all_figures()
    figures = [f for f in all_figures if f.get("name") == args.name]
    if not figures:
      print(f"❌ Figure '{args.name}' not found in database")
      return
    print(f"Found figure: {args.name}\n")
  else:
    # Check all figures
    print("Fetching all figures from database...")
    figures = get_all_figures()
    print(f"Found {len(figures)} figures in database\n")

  if not figures:
    print("No figures found. Exiting.")
    return

  # Validation results (streaming approach - fix immediately when found)
  valid_count = 0
  invalid_count = 0
  fixed_count = 0
  failed_to_fix_count = 0
  failed_fixes = []  # Store details of failed fixes

  # Validate each figure (parallel execution)
  show_index = not args.name
  print(f"Validating figures with {args.workers} parallel workers...\n")

  with ThreadPoolExecutor(max_workers=args.workers) as executor:
    # Submit all tasks
    future_to_figure = {
      executor.submit(
        process_figure, figure, i + 1, len(figures), args, show_index
      ): figure
      for i, figure in enumerate(figures)
    }

    # Process results as they complete
    for future in as_completed(future_to_figure):
      result = future.result()

      # Update counters
      if result["is_valid"]:
        valid_count += 1
      else:
        invalid_count += 1

      if result["fixed"]:
        fixed_count += 1
      if result["fix_failed"]:
        failed_to_fix_count += 1
        # Store details for later display
        failed_fixes.append({
          "name": result["name"],
          "reason": result["fix_failure_reason"],
          "original_url": result["original_image_url"],
          "missing_fields": result["issues"]["missing_fields"],
          "image_status": result["issues"]["image_status"],
        })

  # Print summary
  print("=" * 60)
  print("Validation Summary")
  print("=" * 60)
  print(f"Total figures:   {len(figures)}")
  print(f"Valid:           {valid_count} ({valid_count / len(figures) * 100:.1f}%)")
  print(f"Invalid:         {invalid_count} ({invalid_count / len(figures) * 100:.1f}%)")

  if args.fix:
    print()
    print("Fix Summary:")
    print(f"  Images fixed:    {fixed_count}")
    print(f"  Failed to fix:   {failed_to_fix_count}")

    # Show detailed list of failed fixes
    if failed_fixes:
      print()
      print("=" * 60)
      print("Failed Fixes - Detailed Report")
      print("=" * 60)
      print(f"\nShowing {len(failed_fixes)} figures that could not be fixed:\n")

      for i, failed in enumerate(sorted(failed_fixes, key=lambda x: x["name"]), 1):
        print(f"{i}. {failed['name']}")

        # Show reason
        print(f"   Reason: {failed['reason']}")

        # Show image status
        if failed['image_status'] == 'missing':
          print(f"   Original Image: None (missing)")
        elif failed['image_status'] == 'invalid':
          if failed['original_url']:
            url_display = failed['original_url'][:70] + "..." if len(failed['original_url']) > 70 else failed['original_url']
            print(f"   Original Image: {url_display}")
            print(f"   Status: Invalid/Broken")

        # Show other issues if any
        if failed['missing_fields']:
          print(f"   Other Issues: Missing fields - {', '.join(failed['missing_fields'])}")

        print()

  print()


if __name__ == "__main__":
  main()
