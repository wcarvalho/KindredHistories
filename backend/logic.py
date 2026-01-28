import multiprocessing
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Dict, List, Optional, Tuple

from backend.agent import StoryGeneratorAgent
from backend.cache import save_to_cache
from backend.config import (
  DEBUG_MAX_WORKERS,
  DEFAULT_MIN_SIMILARITY,
  IMMEDIATE_RESULTS_LIMIT,
)
from backend.database import query_by_facets_semantic
from backend.models import SocialModel
from backend.user_service import save_user_search, update_user_search


def process_single_person(name: str):
  """Function to be run in a separate process."""
  try:
    agent = StoryGeneratorAgent()
    agent.process_person(name)
    return f"Success: {name}"
  except Exception as e:
    return f"Error processing {name}: {e}"


class Orchestrator:
  def __init__(self):
    self.agent = StoryGeneratorAgent()
    # Determine N (max processes)
    # For debug, use 1, otherwise CPU count
    self.max_workers = (
      DEBUG_MAX_WORKERS if os.environ.get("DEBUG") else multiprocessing.cpu_count()
    )
    print(f"Orchestrator initialized with {self.max_workers} workers.")

  def extract_and_query_immediate(
    self,
    description: str,
    provided_facets: Optional[List[str]] = None,
    provided_social_model: Optional[Dict] = None,
  ) -> Tuple[SocialModel, List[str], List[Dict]]:
    """
    Phase 1: Extract facets and query existing DB matches.
    Returns immediately with (social_model, facets, existing_figures).
    """
    print(f"[Immediate Phase] Starting for: {description[:50]}...")

    # 1. Extract or use provided facets
    if provided_facets and provided_social_model:
      print("[Immediate Phase] Using provided facets")
      social_model = SocialModel(**provided_social_model)
      facets = provided_facets
    else:
      print("[Immediate Phase] Extracting facets from text")
      social_model = self.agent.extract_demographics_from_text(description)
      facets = social_model.as_list(include_goals=True)

    # 2. Query database for existing matches
    print(f"[Immediate Phase] Querying DB for {len(facets)} facets...")
    results_with_scores = query_by_facets_semantic(
      facets, limit=IMMEDIATE_RESULTS_LIMIT, min_similarity=DEFAULT_MIN_SIMILARITY
    )

    # 3. Format figures with scores
    figures = []
    for figure_data, score, facet_scores in results_with_scores:
      figure_with_score = {
        **figure_data,
        "similarity_score": round(score, 3),
        "facet_scores": {k: round(v, 3) for k, v in facet_scores.items()},
      }
      figures.append(figure_with_score)

    print(f"[Immediate Phase] Found {len(figures)} existing matches")
    return social_model, facets, figures

  def run_background_discovery(
    self,
    description: str,
    social_model: SocialModel,
    facets: List[str],
    user_id: Optional[str] = None,
    search_id: Optional[str] = None,
  ):
    """
    Phase 2: Discover and research new figures (background task).

    Args:
        description: User's search text
        social_model: Extracted social model
        facets: List of facets for searching
        user_id: Firebase UID if authenticated
        search_id: If provided, update this existing search record instead of creating new
    """
    print(f"[Background Phase] Starting discovery for: {description[:50]}...")

    # Discover new names (now returns a list, not iterator)
    discovered_pairs = self.agent.process_user_request_from_social_model(social_model)

    # Collect names and submit parallel processing
    discovered_names = []

    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
      futures = []
      for name, demo_str in discovered_pairs:
        discovered_names.append(name)
        print(
          f"[Background Phase] Submitting task for: {name} (demographics: {demo_str})"
        )
        future = executor.submit(process_single_person, name)
        futures.append(future)

      # Monitor completion
      for future in as_completed(futures):
        try:
          result = future.result()
          print(f"[Background Phase] Task completion: {result}")
        except Exception as e:
          print(f"[Background Phase] Task exception: {e}")

    # Save to cache and user history
    social_model_dict = {
      "race": social_model.race or [],
      "ethnicity": social_model.ethnicity or [],
      "cultural_background": social_model.cultural_background or [],
      "gender": social_model.gender or [],
      "sexuality": social_model.sexuality or [],
      "interests": social_model.interests or [],
      "aspirations": social_model.aspirations or [],
    }

    save_to_cache(description, social_model_dict, discovered_names, facets)

    # Update or create user search history
    if search_id and discovered_names:
      # Update existing search record by adding newly discovered names
      # (existing names from immediate query are already saved)
      update_user_search(search_id, discovered_names, append=True)
    elif user_id:
      # Fallback: create new search record (for direct calls without search_id)
      save_user_search(
        user_id, description, social_model_dict, discovered_names, facets
      )

    print(
      f"[Background Phase] Discovery complete. Found {len(discovered_names)} new figures."
    )

  def run_analysis(self, description: str, user_id: Optional[str] = None):
    """
    Main entry point with caching and history support.

    Args:
      description: User's search text
      user_id: Firebase UID if authenticated, None if anonymous

    1. Infers attributes and combinations.
    2. Finds names.
    3. Spawns processes to research people.
    4. Saves results to cache and user history (if authenticated).
    """
    print(f"Starting analysis for: {description[:30]}...")

    # Extract demographics first
    social_model = self.agent.extract_demographics_from_text(description)

    # Discover names (now returns a list with parallel search)
    discovered_pairs = self.agent.process_user_request_from_social_model(social_model)

    # Collect names for caching
    discovered_names = []

    with ThreadPoolExecutor(max_workers=self.max_workers) as executor:
      futures = []
      for name, demo_str in discovered_pairs:
        discovered_names.append(name)
        print(f"Submitting task for: {name} (demographics: {demo_str})")
        future = executor.submit(process_single_person, name)
        futures.append(future)

      # Monitoring
      for future in as_completed(futures):
        try:
          result = future.result()
          print(f"Task completion: {result}")
        except Exception as e:
          print(f"Task exception: {e}")

    # After completion, save to cache and user history
    if social_model:
      # Convert to dict for storage
      social_model_dict = {
        "race": social_model.race or [],
        "ethnicity": social_model.ethnicity or [],
        "cultural_background": social_model.cultural_background or [],
        "gender": social_model.gender or [],
        "sexuality": social_model.sexuality or [],
        "interests": social_model.interests or [],
        "aspirations": social_model.aspirations or [],
      }

      facets = social_model.as_list(include_goals=True)

      # Save to global cache
      save_to_cache(description, social_model_dict, discovered_names, facets)

      # Save to user history if authenticated
      if user_id:
        save_user_search(
          user_id, description, social_model_dict, discovered_names, facets
        )

      print(f"Analysis complete. Found {len(discovered_names)} figures.")
