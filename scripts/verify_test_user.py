#!/usr/bin/env python3
"""Verify test user search history state."""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from backend.database import db

TEST_USER_ID = "test-user-puppeteer-001"


def get_search_count():
  """Get number of searches for test user."""
  if not db:
    print("[ERROR] Database not available")
    return -1

  docs = db.collection("user_searches").where("user_id", "==", TEST_USER_ID).stream()
  count = sum(1 for _ in docs)
  return count


def clear_searches():
  """Delete all searches for test user."""
  if not db:
    print("[ERROR] Database not available")
    return 0

  docs = db.collection("user_searches").where("user_id", "==", TEST_USER_ID).stream()
  deleted = 0
  for doc in docs:
    doc.reference.delete()
    deleted += 1
  return deleted


def main():
  parser = argparse.ArgumentParser(description="Verify test user search state")
  parser.add_argument("--clear", action="store_true", help="Clear all searches")
  parser.add_argument("--expect", type=int, help="Expected count (exit 1 if different)")
  args = parser.parse_args()

  if args.clear:
    deleted = clear_searches()
    print(f"[OK] Deleted {deleted} searches for test user")
    return

  count = get_search_count()
  print(f"[INFO] Test user has {count} searches")

  if args.expect is not None:
    if count != args.expect:
      print(f"[FAIL] Expected {args.expect}, got {count}")
      sys.exit(1)
    else:
      print(f"[PASS] Count matches expected ({args.expect})")


if __name__ == "__main__":
  main()
