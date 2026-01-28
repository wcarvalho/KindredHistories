#!/usr/bin/env python3
"""
Fix malformed names in Firestore database.

Uses Gemini to extract proper person names from malformed entries by analyzing
ALL available context about the figure (achievement, marginalization_context, etc).

Usage:
    uv run python scripts/update_names.py           # Dry run (preview changes)
    uv run python scripts/update_names.py --apply  # Apply changes to database
"""

import argparse
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# Add parent dir to path for backend imports
sys.path.insert(0, str(Path(__file__).parent.parent))

import dspy
from backend.agent import clean_name, is_valid_person_name
from backend.database import db, get_all_figures
from backend.gemini import make_gemini_lm

# Configuration
MAX_WORKERS = 10
MODEL_NAME = "gemini-2.5-flash-lite"


class ExtractPersonNameFromProfile(dspy.Signature):
  """Extract the historical figure's full name from their profile information.

  You are given profile information about a historical figure. The 'name' field
  may be malformed (containing markdown, descriptions, or garbage text).
  Use the OTHER fields (achievement, marginalization_context, challenges_faced,
  how_they_overcame) to determine the person's actual name.

  RULES:
  1. Return ONLY the person's full name (e.g., "Marie Curie", "Malcolm X")
  2. Do NOT include titles like Dr., Prof., etc.
  3. Do NOT include markdown formatting like ** or *
  4. Do NOT include descriptions or explanations
  5. If you cannot determine a valid person name, return exactly: UNKNOWN

  Examples of GOOD outputs: "Anna Lauren Hoffmann", "Chelsea Manning", "Tortuguita"
  Examples of BAD outputs: "**Anna Hoffmann**", "Dr. Chelsea Manning", "A professor at Georgia Tech"
  """

  name_field = dspy.InputField(desc="The potentially malformed name field")
  achievement = dspy.InputField(desc="What this person achieved")
  marginalization_context = dspy.InputField(desc="Context about their marginalization")
  challenges_faced = dspy.InputField(desc="Challenges they faced (may be empty)")
  how_they_overcame = dspy.InputField(
    desc="How they overcame challenges (may be empty)"
  )

  person_name = dspy.OutputField(
    desc="The person's full name only (e.g., 'Marie Curie'), or 'UNKNOWN' if cannot determine"
  )


class IsPersonName(dspy.Signature):
  """Determine if text is a person's name (not a topic, description, or concept).

  You are given text that may or may not be a person's name. Determine if this
  is actually a real person's name vs. a topic, concept, organization, or description.

  RULES:
  1. Answer 'yes' ONLY if this is clearly a person's full or partial name
  2. Answer 'no' if this is a topic (e.g., "Financial Technology and Inclusion")
  3. Answer 'no' if this is a description (e.g., "A pioneer in civil rights")
  4. Answer 'no' if this is an organization or concept
  5. Single words that could be names (e.g., "Malcolm", "Rosa") should be 'yes'

  Examples:
  - "Marie Curie" -> yes
  - "Financial Technology and Inclusion" -> no
  - "Dr. Martin Luther King Jr." -> yes
  - "Civil Rights Movement" -> no
  - "Harriet" -> yes
  - "Indigenous Environmental Activism" -> no
  """

  text = dspy.InputField(desc="Text to evaluate")
  is_person_name = dspy.OutputField(
    desc="Answer 'yes' if this is a real person's name, 'no' if it's a topic, description, or not a name"
  )


# Global LM instance for LLM validation (set in main())
_global_lm = None


def llm_validate_name(name: str) -> bool:
  """Use LLM to verify a name is actually a person's name."""
  if _global_lm is None:
    return True  # Fail open if LM not initialized

  validator = dspy.Predict(IsPersonName)

  try:
    with dspy.context(lm=_global_lm):
      result = validator(text=name)
      answer = result.is_person_name.strip().lower()
      return answer.startswith("yes")
  except Exception:
    return True  # Fail open - don't reject on error


def detect_malformed_name(name: str) -> tuple[bool, str]:
  """
  Detect if a name is malformed and return reason.

  Returns:
      (is_malformed, reason)
  """
  if not name:
    return True, "empty"

  # Check for markdown
  if "**" in name or "*" in name:
    return True, "has_markdown"

  # Check for description separators
  if " – " in name or (" - " in name and len(name) > 50):
    return True, "has_description"

  # Check for names that are too long (likely descriptions)
  if len(name) > 50:
    return True, "too_long"

  # Check for topic/concept words that indicate this isn't a person name
  topic_starters = [
    "financial",
    "digital",
    "technology",
    "social",
    "political",
    "economic",
    "security",
    "privacy",
  ]
  name_lower = name.lower()
  for word in topic_starters:
    if name_lower.startswith(word):
      return True, "topic_word"

  # Check with validation function
  cleaned = clean_name(name)
  if cleaned != name:
    return True, "needs_cleaning"

  if not is_valid_person_name(cleaned):
    return True, "invalid_format"

  return False, "ok"


def is_plausible_person_name(name: str) -> bool:
  """
  Check if a name looks like an actual person's name.
  """
  if not name or len(name) < 2:
    return False

  # Reject if too long
  if len(name) > 60:
    return False

  # Reject UNKNOWN marker
  if name.upper() == "UNKNOWN":
    return False

  # Reject common failure patterns (case-insensitive)
  failure_patterns = [
    r"^not\s+(specified|mentioned|provided)",
    r"^this\s+",
    r"^no\s+(person|name|valid)",
    r"^empty",
    r"^n/a$",
    r"^none$",
    r"^unknown$",
    r"^the\s+",
    r"^a\s+",
    r"^an\s+",
    r"###",
    r"\*\*",
    # Common non-name patterns from clean_name output
    r"^demographic\s+fit",
    r"^field\s*&?\s*contributions?",
    r"^hacking\s+the",
    r"^why\s+i\s+am",
    r"^misgendering\s+machines",
  ]
  for pattern in failure_patterns:
    if re.search(pattern, name, re.IGNORECASE):
      return False

  # Must start with capital (but allow known lowercase names)
  known_lowercase_names = ["maia arson crimew"]
  if not name[0].isupper() and name.lower() not in known_lowercase_names:
    return False

  # Check reasonable word count (1-5 words for a name)
  words = name.split()
  if len(words) > 5:
    return False

  # Final check: use LLM to verify this is actually a person name
  # This catches things like "Financial Technology and Inclusion"
  if not llm_validate_name(name):
    return False

  return True


def strip_titles(name: str) -> str:
  """Remove common titles from the beginning of a name."""
  title_patterns = [
    r"^Dr\.?\s+",
    r"^Prof\.?\s+",
    r"^Professor\s+",
    r"^Mr\.?\s+",
    r"^Mrs\.?\s+",
    r"^Ms\.?\s+",
    r"^Sir\s+",
    r"^Dame\s+",
    r"^Rev\.?\s+",
    r"^Reverend\s+",
  ]
  result = name
  for pattern in title_patterns:
    result = re.sub(pattern, "", result, flags=re.IGNORECASE)
  return result.strip()


def extract_name_with_llm(figure: dict, lm) -> str | None:
  """
  Use Gemini to extract a person's name using ALL available profile context.
  """
  extractor = dspy.Predict(ExtractPersonNameFromProfile)

  try:
    with dspy.context(lm=lm):
      result = extractor(
        name_field=figure.get("name", ""),
        achievement=figure.get("achievement", ""),
        marginalization_context=figure.get("marginalization_context", ""),
        challenges_faced=figure.get("challenges_faced", "") or "",
        how_they_overcame=figure.get("how_they_overcame", "") or "",
      )
      name = result.person_name.strip()

      if not name or name.upper() == "UNKNOWN":
        return None

      # Clean, strip titles, and validate
      name = clean_name(name)
      name = strip_titles(name)
      if not name or not is_valid_person_name(name):
        return None

      if not is_plausible_person_name(name):
        return None

      return name
  except Exception as e:
    print(f"  [ERROR] LLM extraction failed: {e}")
    return None


def process_figure(figure: dict, lm, dry_run: bool) -> dict | None:
  """
  Process a single figure, fixing its name if malformed.

  Returns:
      Dict with update info if changed, None otherwise
  """
  name = figure.get("name", "")
  doc_id = name.replace("/", "_").replace(".", "_")

  is_malformed, reason = detect_malformed_name(name)

  if not is_malformed:
    return None

  # First try simple cleaning for obvious cases like "**John Smith**"
  cleaned = clean_name(name)
  if (
    cleaned
    and is_valid_person_name(cleaned)
    and cleaned != name
    and is_plausible_person_name(cleaned)
  ):
    new_name = cleaned
    method = "clean_name"
  else:
    # Use LLM with full profile context
    new_name = extract_name_with_llm(figure, lm)
    method = "llm_extract"

  if not new_name:
    # Delete entries that can't be fixed (not valid person names)
    if not dry_run and db:
      db.collection("historical_figures").document(doc_id).delete()
    return {
      "old_name": name,
      "new_name": None,
      "reason": reason,
      "method": "deleted",
      "applied": not dry_run,
    }

  # Apply update if not dry run
  if not dry_run and db:
    new_doc_id = new_name.replace("/", "_").replace(".", "_")

    if doc_id != new_doc_id:
      # Name change requires document rename (copy + delete)
      figure["name"] = new_name
      db.collection("historical_figures").document(new_doc_id).set(figure)
      db.collection("historical_figures").document(doc_id).delete()
    else:
      # Just update the name field
      db.collection("historical_figures").document(doc_id).update({"name": new_name})

  return {
    "old_name": name,
    "new_name": new_name,
    "reason": reason,
    "method": method,
    "applied": not dry_run,
  }


def main():
  parser = argparse.ArgumentParser(description="Fix malformed names in database")
  parser.add_argument(
    "--apply", action="store_true", help="Apply changes (default is dry run)"
  )
  parser.add_argument(
    "--workers", type=int, default=MAX_WORKERS, help="Max parallel workers"
  )
  parser.add_argument(
    "--limit", type=int, default=0, help="Limit number of figures to process (0 = all)"
  )
  args = parser.parse_args()

  dry_run = not args.apply

  print("=" * 60)
  print("NAME FIXER SCRIPT")
  print("=" * 60)
  print(f"Mode: {'DRY RUN (preview only)' if dry_run else 'APPLY CHANGES'}")
  print()

  # Initialize LM and set global for LLM validation
  global _global_lm
  print(f"Initializing {MODEL_NAME}...")
  lm = make_gemini_lm(model_name=MODEL_NAME)
  _global_lm = lm

  # Fetch all figures
  print("Fetching all figures from database...")
  figures = get_all_figures()
  print(f"Found {len(figures)} figures")

  # Identify malformed names
  malformed = []
  for fig in figures:
    name = fig.get("name", "")
    is_bad, reason = detect_malformed_name(name)
    if is_bad:
      malformed.append((fig, reason))

  print(f"Found {len(malformed)} malformed names:")
  for fig, reason in malformed[:10]:
    print(f"  - [{reason}] {fig.get('name', '')[:60]}...")
  if len(malformed) > 10:
    print(f"  ... and {len(malformed) - 10} more")
  print()

  if not malformed:
    print("No malformed names found. Exiting.")
    return

  # Apply limit if specified
  if args.limit > 0:
    malformed = malformed[: args.limit]
    print(f"Limited to {args.limit} figures")

  # Process in parallel
  print(f"Processing {len(malformed)} figures with {args.workers} workers...")
  results = []

  with ThreadPoolExecutor(max_workers=args.workers) as executor:
    futures = {
      executor.submit(process_figure, fig, lm, dry_run): fig for fig, _ in malformed
    }

    for future in as_completed(futures):
      result = future.result()
      if result:
        results.append(result)

  # Report
  print()
  print("=" * 60)
  print("RESULTS")
  print("=" * 60)

  fixed = [r for r in results if r["new_name"]]
  deleted = [r for r in results if not r["new_name"]]

  print(f"Fixed: {len(fixed)}")
  print(f"Deleted: {len(deleted)}")

  if fixed:
    print("\nFixed names:")
    for r in fixed[:20]:
      print(f"  {r['old_name'][:40]}...")
      print(f"    -> {r['new_name']} [{r['method']}]")
    if len(fixed) > 20:
      print(f"  ... and {len(fixed) - 20} more")

  if deleted:
    print("\nDeleted (no valid person name):")
    for r in deleted[:10]:
      print(f"  [{r['reason']}] {r['old_name'][:60]}...")
    if len(deleted) > 10:
      print(f"  ... and {len(deleted) - 10} more")

  if dry_run:
    print()
    print("This was a DRY RUN. To apply changes, run:")
    print("  uv run python scripts/update_names.py --apply")


if __name__ == "__main__":
  main()
