"""
Evaluation script to measure the "Begin Journey" flow timing.

This script simulates what happens when a user clicks "Begin Journey":
1. POST /api/extract-facets - Extract user's facets from description
2. POST /api/analyze - Start analysis (immediate phase + background discovery)

Usage:
    uv run python evals/begin_journey.py

The script measures and reports timing for each step.
"""

import time

import requests

BASE_URL = "http://127.0.0.1:8000"

# Sample user description (same as in the logs)
SAMPLE_DESCRIPTION = """I am Mexican. I am a neuroscientist. I crossed the border to the USA when I was 12. I think a lot about how to be a more compassionate person and have to move with compassion I feel the suffering of others a lot and I want to make something out of that something good out of it. I am fighter."""


def measure_begin_journey():
  """Measure the full "Begin Journey" flow timing."""
  print("=" * 60)
  print("Begin Journey Timing Evaluation")
  print("=" * 60)
  print()

  total_start = time.perf_counter()

  # Step 1: Extract facets
  print("Step 1: POST /api/extract-facets")
  step1_start = time.perf_counter()

  try:
    response1 = requests.post(
      f"{BASE_URL}/api/extract-facets",
      json={"text": SAMPLE_DESCRIPTION},
      timeout=120,
    )
    response1.raise_for_status()
    facet_data = response1.json()
  except requests.exceptions.RequestException as e:
    print(f"  ERROR: {e}")
    return

  step1_time = time.perf_counter() - step1_start
  print(f"  Status: {response1.status_code}")
  print(f"  Time: {step1_time:.2f}s")
  print(f"  Facets extracted: {len(facet_data.get('facets', []))}")
  print()

  # Step 2: Analyze (with pre-extracted facets)
  print("Step 2: POST /api/analyze (with pre-extracted facets)")
  step2_start = time.perf_counter()

  try:
    response2 = requests.post(
      f"{BASE_URL}/api/analyze",
      json={
        "text": SAMPLE_DESCRIPTION,
        "facets": facet_data.get("facets"),
        "social_model": facet_data.get("social_model"),
      },
      timeout=120,
    )
    response2.raise_for_status()
    analyze_data = response2.json()
  except requests.exceptions.RequestException as e:
    print(f"  ERROR: {e}")
    return

  step2_time = time.perf_counter() - step2_start
  print(f"  Status: {response2.status_code}")
  print(f"  Time: {step2_time:.2f}s")
  print(f"  Initial figures: {analyze_data.get('count', 0)}")
  print()

  total_time = time.perf_counter() - total_start

  # Summary
  print("=" * 60)
  print("SUMMARY")
  print("=" * 60)
  print(f"  extract-facets: {step1_time:.2f}s")
  print(f"  analyze:        {step2_time:.2f}s")
  print(f"  TOTAL:          {total_time:.2f}s")
  print()

  # Verdict
  if total_time < 3:
    print("PASS: Response time is acceptable (< 3s)")
  elif total_time < 5:
    print("WARN: Response time is slow (3-5s)")
  else:
    print(f"FAIL: Response time is too slow (> 5s)")


if __name__ == "__main__":
  measure_begin_journey()
