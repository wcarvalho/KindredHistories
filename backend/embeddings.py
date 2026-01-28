"""
Embedding utilities for semantic facet matching.

Uses BAAI/bge-small-en-v1.5 model via sentence-transformers.
- 384 dimensions
- 33M parameters
- Optimized for semantic retrieval
- ~30x faster than Gemini API
"""

import re
from typing import Dict, List, Tuple

import numpy as np
from sentence_transformers import SentenceTransformer

# Embedding model configuration
EMBEDDING_MODEL = "BAAI/bge-small-en-v1.5"

# Sentence templates for richer embeddings
FIELD_TEMPLATES = {
  "race": "This person's race is {value}.",
  "ethnicity": "This person's ethnicity is {value}.",
  "cultural_background": "This person's cultural background is {value}.",
  "location": "This person is from {value}.",
  "gender": "This person's gender is {value}.",
  "sexuality": "This person's sexuality is {value}.",
  "interests": "This person is interested in {value}.",
  "aspirations": "This person aspires to {value}.",
}


def format_facet_for_embedding(field: str, value: str) -> str:
  """
  Format a facet value as a full sentence for richer embedding.

  Args:
      field: The field name (e.g., "race", "interests")
      value: The facet value (e.g., "Black", "neuroscience")

  Returns:
      Full sentence like "This person's race is Black."
      or "This person is interested in neuroscience."
  """
  template = FIELD_TEMPLATES.get(field, "This person is associated with {value}.")
  return template.format(value=value)


# Global model instance (lazy initialization)
_model = None


def get_embedding_model() -> SentenceTransformer:
  """
  Get the SentenceTransformer model for embeddings.

  Uses bge-small-en-v1.5:
  - 384 dimensions
  - 33M parameters
  - Optimized for retrieval tasks
  - ~7ms for batch of 10 facets
  """
  global _model
  if _model is None:
    _model = SentenceTransformer(EMBEDDING_MODEL)
  return _model


def encode_facet(facet: str) -> List[float]:
  """
  Encode a single facet string into an embedding vector.

  Args:
      facet: A facet value (e.g., "Mexican", "neuroscience", "Atlanta, Georgia")

  Returns:
      List of 384 floats representing the embedding
  """
  model = get_embedding_model()
  embedding = model.encode(facet, convert_to_numpy=True)
  return embedding.tolist()


def encode_facets(facets: List[str]) -> Dict[str, List[float]]:
  """
  Encode multiple facets into embeddings.

  Args:
      facets: List of facet values

  Returns:
      Dictionary mapping each facet to its embedding vector
  """
  if not facets:
    return {}

  model = get_embedding_model()

  # Batch encode for efficiency
  embeddings = model.encode(facets, convert_to_numpy=True)

  return {facet: emb.tolist() for facet, emb in zip(facets, embeddings)}


def encode_user_facets(
  selected_facets: List[str], facet_to_field: Dict[str, str]
) -> Dict[str, List[float]]:
  """
  Encode user-selected facets using the same rich sentence format as figures.

  Args:
      selected_facets: List of raw facet values selected by user
      facet_to_field: Mapping from facet value to field name (e.g., {"Black": "race"})

  Returns:
      Dictionary mapping raw facet value to its embedding
  """
  if not selected_facets:
    return {}

  # Format each facet as a sentence using its field
  descriptions = []
  for facet in selected_facets:
    field = facet_to_field.get(facet, "")
    if field:
      descriptions.append(format_facet_for_embedding(field, facet))
    else:
      # Unknown field - use generic format
      descriptions.append(f"This person is associated with {facet}.")

  # Batch encode
  model = get_embedding_model()
  embeddings = model.encode(descriptions, convert_to_numpy=True)

  return {facet: emb.tolist() for facet, emb in zip(selected_facets, embeddings)}


def encode_facets_from_tags(
  tags: Dict[str, any],
) -> tuple[List[str], Dict[str, List[float]]]:
  """
  Extract facets from tags dict and encode with rich descriptions.

  Each facet is formatted with its field label (e.g., "Race: Black")
  before embedding, but the key in the returned dict is the raw value.

  Args:
      tags: Dictionary with fields like race, ethnicity, interests, etc.

  Returns:
      Tuple of (facets_list, facet_embeddings):
      - facets_list: Deduplicated list of raw facet values for display
      - facet_embeddings: Dict mapping raw facet value to its embedding
  """
  if not tags:
    return [], {}

  # Collect (field, value) pairs and deduplicate
  facet_pairs = []  # [(field, value), ...]
  seen_values = set()

  for field in FIELD_TEMPLATES.keys():
    if field in tags and tags[field]:
      values = tags[field] if isinstance(tags[field], list) else [tags[field]]
      for value in values:
        if value and value not in seen_values:
          facet_pairs.append((field, value))
          seen_values.add(value)

  if not facet_pairs:
    return [], {}

  # Create formatted descriptions for embedding
  raw_values = [value for _, value in facet_pairs]
  descriptions = [
    format_facet_for_embedding(field, value) for field, value in facet_pairs
  ]

  # Batch encode the descriptions
  model = get_embedding_model()
  embeddings = model.encode(descriptions, convert_to_numpy=True)

  # Map raw values to embeddings (so keys match user queries)
  facet_embeddings = {raw: emb.tolist() for raw, emb in zip(raw_values, embeddings)}

  return raw_values, facet_embeddings


def calculate_facet_similarity(
  user_facets_embeddings: Dict[str, List[float]],
  figure_facets_embeddings: Dict[str, List[float]],
) -> float:
  """
  Calculate semantic similarity between user facets and figure facets using matrix operations.

  Strategy (optimized with numpy):
  1. Stack user embeddings into matrix U (n_user × dim)
  2. Stack figure embeddings into matrix F (n_figure × dim)
  3. Compute cosine similarity matrix S = (U @ F.T) / (||U|| * ||F||)
     → S has shape (n_user × n_figure)
  4. For each user facet (row), take max similarity across all figure facets
  5. Average these max similarities

  This is much faster than nested loops for similarity computation.

  Args:
      user_facets_embeddings: {facet: embedding} for user's selected facets
      figure_facets_embeddings: {facet: embedding} for a historical figure

  Returns:
      Similarity score between 0 and 1
  """
  if not user_facets_embeddings or not figure_facets_embeddings:
    return 0.0

  # Stack embeddings into matrices
  user_matrix = np.array(list(user_facets_embeddings.values()))
  figure_matrix = np.array(list(figure_facets_embeddings.values()))

  # Normalize embeddings for cosine similarity
  user_norms = np.linalg.norm(user_matrix, axis=1, keepdims=True)
  figure_norms = np.linalg.norm(figure_matrix, axis=1, keepdims=True)

  # Avoid division by zero
  user_norms = np.maximum(user_norms, 1e-10)
  figure_norms = np.maximum(figure_norms, 1e-10)

  user_normalized = user_matrix / user_norms
  figure_normalized = figure_matrix / figure_norms

  # Compute cosine similarity matrix via dot product
  # similarity_matrix[i, j] = cosine_similarity(user_facet_i, figure_facet_j)
  similarity_matrix = user_normalized @ figure_normalized.T

  # For each user facet, find max similarity to any figure facet
  max_similarities = np.max(similarity_matrix, axis=1)

  # Return average of max similarities
  return float(np.mean(max_similarities))


def calculate_facet_similarity_detailed(
  user_facets_embeddings: Dict[str, List[float]],
  figure_facets_embeddings: Dict[str, List[float]],
) -> Tuple[float, Dict[str, float]]:
  """
  Calculate semantic similarity with per-facet breakdown.

  Returns both overall score and individual scores for each user facet.

  Args:
      user_facets_embeddings: {facet: embedding} for user's selected facets
      figure_facets_embeddings: {facet: embedding} for a historical figure

  Returns:
      Tuple of (overall_score, {facet: score}) where score is max similarity
      of that user facet to any figure facet
  """
  if not user_facets_embeddings or not figure_facets_embeddings:
    return 0.0, {}

  user_facets_list = list(user_facets_embeddings.keys())
  user_matrix = np.array(list(user_facets_embeddings.values()))
  figure_matrix = np.array(list(figure_facets_embeddings.values()))

  # Normalize embeddings for cosine similarity
  user_norms = np.linalg.norm(user_matrix, axis=1, keepdims=True)
  figure_norms = np.linalg.norm(figure_matrix, axis=1, keepdims=True)

  user_norms = np.maximum(user_norms, 1e-10)
  figure_norms = np.maximum(figure_norms, 1e-10)

  user_normalized = user_matrix / user_norms
  figure_normalized = figure_matrix / figure_norms

  # Compute cosine similarity matrix
  similarity_matrix = user_normalized @ figure_normalized.T

  # For each user facet, find max similarity to any figure facet
  max_similarities = np.max(similarity_matrix, axis=1)

  # Build per-facet scores dictionary
  facet_scores = {
    facet: float(score) for facet, score in zip(user_facets_list, max_similarities)
  }

  # Overall score is MEAN (AND behavior - must match ALL facets reasonably well)
  # This means a figure must score well across all user facets, not just one
  overall_score = float(np.mean(max_similarities))

  return overall_score, facet_scores


def check_exact_facet_match(
  facet: str, searchable_text: str, case_sensitive: bool = False
) -> bool:
  """
  Check if a facet appears as a complete phrase in the text.

  For single-word facets, uses word boundaries to avoid partial matches
  (e.g., "New" won't match inside "New Yorker").
  For multi-word facets, uses simple substring matching.

  Args:
      facet: The facet value to search for (e.g., "Bolivian", "New Yorker")
      searchable_text: The combined text from a figure's profile
      case_sensitive: Whether to perform case-sensitive matching

  Returns:
      True if the facet appears in the text, False otherwise
  """
  if not facet or not searchable_text:
    return False

  if not case_sensitive:
    facet = facet.lower()
    searchable_text = searchable_text.lower()

  # For single-word facets, use word boundaries to avoid partial matches
  if len(facet.split()) == 1:
    pattern = r"\b" + re.escape(facet) + r"\b"
    return bool(re.search(pattern, searchable_text))
  else:
    # Multi-word: simple substring match
    return facet in searchable_text
