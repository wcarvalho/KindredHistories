"""
Benchmark the matrix-based similarity calculation vs the old loop-based approach.
"""

import time
from typing import Dict, List

import numpy as np


def calculate_facet_similarity_old(
  user_facets_embeddings: Dict[str, List[float]],
  figure_facets_embeddings: Dict[str, List[float]],
) -> float:
  """Old loop-based implementation for comparison."""
  if not user_facets_embeddings or not figure_facets_embeddings:
    return 0.0

  figure_embeddings_array = [np.array(emb) for emb in figure_facets_embeddings.values()]
  similarities = []

  for user_facet, user_embedding in user_facets_embeddings.items():
    user_emb_array = np.array(user_embedding)

    # Find max similarity to any figure facet
    max_sim = max(
      np.dot(user_emb_array, fig_emb)
      / (np.linalg.norm(user_emb_array) * np.linalg.norm(fig_emb))
      for fig_emb in figure_embeddings_array
    )

    similarities.append(max_sim)

  return float(np.mean(similarities))


def calculate_facet_similarity_new(
  user_facets_embeddings: Dict[str, List[float]],
  figure_facets_embeddings: Dict[str, List[float]],
) -> float:
  """New matrix-based implementation."""
  if not user_facets_embeddings or not figure_facets_embeddings:
    return 0.0

  user_matrix = np.array(list(user_facets_embeddings.values()))
  figure_matrix = np.array(list(figure_facets_embeddings.values()))

  user_norms = np.linalg.norm(user_matrix, axis=1, keepdims=True)
  figure_norms = np.linalg.norm(figure_matrix, axis=1, keepdims=True)

  user_norms = np.maximum(user_norms, 1e-10)
  figure_norms = np.maximum(figure_norms, 1e-10)

  user_normalized = user_matrix / user_norms
  figure_normalized = figure_matrix / figure_norms

  similarity_matrix = user_normalized @ figure_normalized.T
  max_similarities = np.max(similarity_matrix, axis=1)

  return float(np.mean(max_similarities))


def benchmark():
  """Run benchmark comparing old vs new implementation."""

  # Create synthetic embeddings
  n_user_facets = 10
  n_figure_facets = 15
  embedding_dim = 384

  user_embeddings = {
    f"user_facet_{i}": np.random.randn(embedding_dim).tolist()
    for i in range(n_user_facets)
  }

  figure_embeddings = {
    f"figure_facet_{i}": np.random.randn(embedding_dim).tolist()
    for i in range(n_figure_facets)
  }

  # Warmup
  for _ in range(10):
    calculate_facet_similarity_old(user_embeddings, figure_embeddings)
    calculate_facet_similarity_new(user_embeddings, figure_embeddings)

  # Benchmark old implementation
  n_iterations = 1000
  start = time.perf_counter()
  for _ in range(n_iterations):
    result_old = calculate_facet_similarity_old(user_embeddings, figure_embeddings)
  time_old = time.perf_counter() - start

  # Benchmark new implementation
  start = time.perf_counter()
  for _ in range(n_iterations):
    result_new = calculate_facet_similarity_new(user_embeddings, figure_embeddings)
  time_new = time.perf_counter() - start

  print("=" * 60)
  print("SIMILARITY CALCULATION BENCHMARK")
  print("=" * 60)
  print(f"Setup: {n_user_facets} user facets × {n_figure_facets} figure facets")
  print(f"Iterations: {n_iterations}")
  print()
  print(
    f"Old (loop-based):   {time_old * 1000:.2f}ms total, {time_old / n_iterations * 1000:.4f}ms per call"
  )
  print(
    f"New (matrix-based): {time_new * 1000:.2f}ms total, {time_new / n_iterations * 1000:.4f}ms per call"
  )
  print()
  print(f"Speedup: {time_old / time_new:.2f}x faster")
  print()
  print(
    f"Verification: old={result_old:.4f}, new={result_new:.4f}, diff={abs(result_old - result_new):.6f}"
  )
  print("=" * 60)


if __name__ == "__main__":
  benchmark()
