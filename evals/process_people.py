"""
Eval script to measure person research efficiency.

This script evaluates the process_person() function which researches
individual historical figures after name discovery.

TODO: Implement metrics for:
- Research loop iterations per person
- Profile completeness rate
- Image search success rate
- API calls per person
- Time per person

Usage:
    uv run python evals/process_people.py
    uv run python evals/process_people.py --names "Marie Curie" "Ada Lovelace"
"""

import argparse
import os
import sys

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


def main():
  parser = argparse.ArgumentParser(
    description="Evaluate person research efficiency (not yet implemented)"
  )
  parser.add_argument(
    "--names",
    nargs="+",
    help="Names of historical figures to research",
  )
  args = parser.parse_args()

  print("=" * 60)
  print("PROCESS PEOPLE EVALUATION")
  print("=" * 60)
  print("\nThis evaluation script is not yet implemented.")
  print("\nPlanned metrics:")
  print("  - Research loop iterations per person")
  print("  - Profile completeness rate")
  print("  - Image search success rate")
  print("  - API calls per person")
  print("  - Time per person")
  print("\nSee evals/generate_people.py for the name discovery evaluation.")


if __name__ == "__main__":
  main()
