"""
Compare embedding performance between Gemini API and local SentenceTransformer.

Use cases (from compute_embeddings.py):
1. Batch processing - Recomputing embeddings for all figures in Firestore
2. Cold start - Cloud Run containers need fast warmup
3. API requests - Real-time embedding for user queries

Metrics compared:
1. Warmup time - Model initialization/first call latency
2. Single embedding - Time to encode one facet
3. Batch embedding - Time to encode multiple facets (typical: 5-15 facets per figure)

Usage:
    uv run python -m backend.evals_compare_embeddings_time
    uv run python -m backend.evals_compare_embeddings_time --batch-sizes 5,10,20
    uv run python -m backend.evals_compare_embeddings_time --iterations 50
"""

import argparse
import gc
import os
import time
from typing import Callable, List, Tuple

from dotenv import load_dotenv

load_dotenv()


# Sample facets (realistic examples from the app)
SAMPLE_FACETS = [
  "This person's race is Black.",
  "This person's ethnicity is African-American.",
  "This person's cultural background is Southern United States.",
  "This person is from Atlanta, Georgia.",
  "This person's gender is female.",
  "This person is interested in civil rights.",
  "This person is interested in neuroscience.",
  "This person aspires to fight for equality.",
  "This person aspires to advance scientific research.",
  "This person's race is Latino.",
  "This person's ethnicity is Mexican-American.",
  "This person is interested in education.",
  "This person is interested in mathematics.",
  "This person aspires to break barriers in STEM.",
  "This person is from Texas.",
]


def measure_warmup_gemini() -> Tuple[float, Callable[[List[str]], List[List[float]]]]:
  """
  Measure Gemini API warmup time.

  Returns:
      Tuple of (warmup_time_seconds, encode_function)
  """
  from google import genai

  start = time.perf_counter()

  # Initialize client
  client = genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))

  # First API call (includes connection setup, auth, etc.)
  result = client.models.embed_content(
    model="text-embedding-004", contents=["warmup test"]
  )
  _ = result.embeddings[0].values

  warmup_time = time.perf_counter() - start

  def encode_batch(texts: List[str]) -> List[List[float]]:
    result = client.models.embed_content(model="text-embedding-004", contents=texts)
    return [list(emb.values) for emb in result.embeddings]

  return warmup_time, encode_batch


def measure_warmup_sentence_transformer() -> Tuple[
  float, Callable[[List[str]], List[List[float]]]
]:
  """
  Measure SentenceTransformer warmup time.

  Returns:
      Tuple of (warmup_time_seconds, encode_function)
  """
  from sentence_transformers import SentenceTransformer

  start = time.perf_counter()

  # Load model (downloads if needed, loads weights into memory)
  model = SentenceTransformer("all-MiniLM-L6-v2")

  # First encode (triggers any lazy initialization)
  _ = model.encode(["warmup test"])

  warmup_time = time.perf_counter() - start

  def encode_batch(texts: List[str]) -> List[List[float]]:
    embeddings = model.encode(texts)
    return [emb.tolist() for emb in embeddings]

  return warmup_time, encode_batch


def benchmark_encoding(
  encode_fn: Callable[[List[str]], List[List[float]]],
  batch_sizes: List[int],
  iterations: int,
) -> dict:
  """
  Benchmark encoding performance for various batch sizes.

  Returns:
      Dictionary with timing results
  """
  results = {}

  for batch_size in batch_sizes:
    # Use cycling through sample facets if batch_size > len(SAMPLE_FACETS)
    batch = []
    for i in range(batch_size):
      batch.append(SAMPLE_FACETS[i % len(SAMPLE_FACETS)])

    # Warmup for this batch size
    for _ in range(3):
      encode_fn(batch)

    # Measure
    times = []
    for _ in range(iterations):
      start = time.perf_counter()
      embeddings = encode_fn(batch)
      elapsed = time.perf_counter() - start
      times.append(elapsed)

    results[batch_size] = {
      "total_ms": sum(times) * 1000,
      "avg_ms": (sum(times) / len(times)) * 1000,
      "min_ms": min(times) * 1000,
      "max_ms": max(times) * 1000,
      "per_item_ms": (sum(times) / len(times) / batch_size) * 1000,
      "embedding_dim": len(embeddings[0]),
    }

  return results


def run_comparison(batch_sizes: List[int], iterations: int):
  """Run full comparison between Gemini and SentenceTransformer."""

  print("=" * 70)
  print("EMBEDDING MODEL COMPARISON: Gemini vs SentenceTransformer")
  print("=" * 70)
  print(f"Batch sizes: {batch_sizes}")
  print(f"Iterations per batch: {iterations}")
  print()

  # Force garbage collection before measurements
  gc.collect()

  # Measure Gemini
  print("Initializing Gemini (text-embedding-004)...")
  try:
    gemini_warmup, gemini_encode = measure_warmup_gemini()
    print(f"  Warmup time: {gemini_warmup * 1000:.0f}ms")
    print("  Benchmarking...")
    gemini_results = benchmark_encoding(gemini_encode, batch_sizes, iterations)
  except Exception as e:
    print(f"  ERROR: {e}")
    gemini_warmup = None
    gemini_results = None

  gc.collect()

  # Measure SentenceTransformer
  print("\nInitializing SentenceTransformer (all-MiniLM-L6-v2)...")
  try:
    st_warmup, st_encode = measure_warmup_sentence_transformer()
    print(f"  Warmup time: {st_warmup * 1000:.0f}ms")
    print("  Benchmarking...")
    st_results = benchmark_encoding(st_encode, batch_sizes, iterations)
  except Exception as e:
    print(f"  ERROR: {e}")
    st_warmup = None
    st_results = None

  # Print results
  print("\n" + "=" * 70)
  print("RESULTS")
  print("=" * 70)

  # Warmup comparison
  print("\n1. WARMUP TIME (model initialization + first call)")
  print("-" * 50)
  if gemini_warmup is not None:
    print(f"   Gemini API:          {gemini_warmup * 1000:>8.0f}ms")
  if st_warmup is not None:
    print(f"   SentenceTransformer: {st_warmup * 1000:>8.0f}ms")
  if gemini_warmup and st_warmup:
    if gemini_warmup < st_warmup:
      print(f"   → Gemini is {st_warmup / gemini_warmup:.1f}x faster to warm up")
    else:
      print(
        f"   → SentenceTransformer is {gemini_warmup / st_warmup:.1f}x faster to warm up"
      )

  # Embedding dimension
  print("\n2. EMBEDDING DIMENSIONS")
  print("-" * 50)
  if gemini_results:
    dim = list(gemini_results.values())[0]["embedding_dim"]
    print(f"   Gemini:              {dim} dimensions")
  if st_results:
    dim = list(st_results.values())[0]["embedding_dim"]
    print(f"   SentenceTransformer: {dim} dimensions")

  # Per-batch timing
  print("\n3. ENCODING TIME BY BATCH SIZE")
  print("-" * 50)
  print(f"   {'Batch':<8} {'Gemini (ms)':<15} {'ST (ms)':<15} {'Winner':<20}")
  print(f"   {'-' * 8} {'-' * 15} {'-' * 15} {'-' * 20}")

  for batch_size in batch_sizes:
    gemini_avg = gemini_results[batch_size]["avg_ms"] if gemini_results else None
    st_avg = st_results[batch_size]["avg_ms"] if st_results else None

    gemini_str = f"{gemini_avg:.2f}" if gemini_avg else "N/A"
    st_str = f"{st_avg:.2f}" if st_avg else "N/A"

    if gemini_avg and st_avg:
      if gemini_avg < st_avg:
        winner = f"Gemini ({st_avg / gemini_avg:.1f}x faster)"
      else:
        winner = f"ST ({gemini_avg / st_avg:.1f}x faster)"
    else:
      winner = "N/A"

    print(f"   {batch_size:<8} {gemini_str:<15} {st_str:<15} {winner:<20}")

  # Per-item timing (amortized)
  print("\n4. PER-ITEM ENCODING TIME (amortized)")
  print("-" * 50)
  print(f"   {'Batch':<8} {'Gemini (ms)':<15} {'ST (ms)':<15}")
  print(f"   {'-' * 8} {'-' * 15} {'-' * 15}")

  for batch_size in batch_sizes:
    gemini_per = gemini_results[batch_size]["per_item_ms"] if gemini_results else None
    st_per = st_results[batch_size]["per_item_ms"] if st_results else None

    gemini_str = f"{gemini_per:.3f}" if gemini_per else "N/A"
    st_str = f"{st_per:.3f}" if st_per else "N/A"

    print(f"   {batch_size:<8} {gemini_str:<15} {st_str:<15}")

  # Use case analysis
  print("\n" + "=" * 70)
  print("USE CASE ANALYSIS")
  print("=" * 70)

  if gemini_warmup and st_warmup and gemini_results and st_results:
    print("\n1. CLOUD RUN COLD START (warmup matters)")
    print("   " + "-" * 40)
    if gemini_warmup < st_warmup:
      print(f"   Gemini saves {(st_warmup - gemini_warmup) * 1000:.0f}ms on cold start")
      print("   → Prefer Gemini for cold start latency")
    else:
      print(
        f"   SentenceTransformer saves {(gemini_warmup - st_warmup) * 1000:.0f}ms on cold start"
      )
      print("   → Prefer SentenceTransformer for cold start latency")

    print("\n2. BATCH RECOMPUTATION (e.g., 500 figures × 10 facets = 5000 embeddings)")
    print("   " + "-" * 40)
    # Estimate: 500 API calls of batch size 10
    gemini_batch_time = gemini_warmup + (500 * gemini_results[10]["avg_ms"] / 1000)
    st_batch_time = st_warmup + (500 * st_results[10]["avg_ms"] / 1000)
    print(f"   Gemini total:              {gemini_batch_time:.1f}s")
    print(f"   SentenceTransformer total: {st_batch_time:.1f}s")
    if gemini_batch_time < st_batch_time:
      print(
        f"   → Gemini is {st_batch_time / gemini_batch_time:.1f}x faster for batch jobs"
      )
    else:
      print(
        f"   → SentenceTransformer is {gemini_batch_time / st_batch_time:.1f}x faster for batch jobs"
      )

    print("\n3. REAL-TIME USER QUERY (single request, post-warmup)")
    print("   " + "-" * 40)
    # Typical: 3-5 user facets
    gemini_query = gemini_results[5]["avg_ms"]
    st_query = st_results[5]["avg_ms"]
    print(f"   Gemini (5 facets):              {gemini_query:.1f}ms")
    print(f"   SentenceTransformer (5 facets): {st_query:.1f}ms")
    if gemini_query < st_query:
      print(f"   → Gemini is {st_query / gemini_query:.1f}x faster for user queries")
    else:
      print(
        f"   → SentenceTransformer is {gemini_query / st_query:.1f}x faster for user queries"
      )

  print("\n" + "=" * 70)


if __name__ == "__main__":
  parser = argparse.ArgumentParser(
    description="Compare Gemini vs SentenceTransformer embedding performance"
  )
  parser.add_argument(
    "--batch-sizes",
    type=str,
    default="1,5,10,15",
    help="Comma-separated batch sizes to test (default: 1,5,10,15)",
  )
  parser.add_argument(
    "--iterations",
    type=int,
    default=20,
    help="Iterations per batch size (default: 20)",
  )
  args = parser.parse_args()

  batch_sizes = [int(x.strip()) for x in args.batch_sizes.split(",")]
  run_comparison(batch_sizes, args.iterations)
