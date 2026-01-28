import os
import time
from typing import List

import dspy
import uvicorn
from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware

from backend.agent import DemographicExtraction, ensure_list
from backend.auth import get_current_user, require_auth
from backend.cache import get_cached_search
from backend.facet_cache import get_cached_facets, save_facets_to_cache
from backend.request_coalescing import coalesced_request
from backend.config import (
  API_DEFAULT_LIMIT,
  API_MAX_LIMIT,
  DEFAULT_MIN_SIMILARITY,
  IMMEDIATE_RESULTS_LIMIT,
  RERUN_MIN_SIMILARITY,
)
from backend.database import (
  db,
  get_all_facets,
  get_all_figures,
  query_by_facets_exact,
  query_by_facets_semantic,
)
from backend.embeddings import encode_facet, get_embedding_model
from backend.gemini import make_gemini_lm
from backend.logic import Orchestrator
from backend.models import SocialModel, UserDescription
from backend.user_service import (
  _unflatten_social_model,
  delete_all_user_searches,
  delete_user_search,
  get_user_searches,
  save_or_update_user,
  save_user_search,
)

app = FastAPI()


@app.on_event("startup")
async def warmup_models():
  """Pre-load embedding model at startup."""
  print("Initializing embedding model...")
  get_embedding_model()  # Load model into memory
  encode_facet("warmup")  # Trigger first inference to warm up
  print("Warmup complete")


# Enable CORS for frontend
# Get allowed origins from environment variable (comma-separated)
# Default includes localhost for development
ALLOWED_ORIGINS = os.getenv(
  "ALLOWED_ORIGINS",
  "http://localhost:5173,http://localhost:5174,http://localhost:8000,http://localhost:3000,https://kindred-histories.firebaseapp.com,https://kindred-histories.web.app",
).split(",")

app.add_middleware(
  CORSMiddleware,
  allow_origins=ALLOWED_ORIGINS,  # Restrict to specific domains in production
  allow_credentials=True,
  allow_methods=["*"],
  allow_headers=["*"],
)

orchestrator = Orchestrator()

# Lazy-load LM for facet extraction
_extraction_lm = None


def get_extraction_lm():
  global _extraction_lm
  if _extraction_lm is None:
    _extraction_lm = make_gemini_lm()
  return _extraction_lm


@app.get("/health")
async def health_check():
  """
  Health check endpoint for Cloud Run and monitoring.
  Returns service status and timestamp.
  """
  return {
    "status": "healthy",
    "service": "kindred-histories-backend",
    "timestamp": time.time(),
  }


@app.post("/api/auth/login")
async def login_user(user=Depends(get_current_user)):
  """
  Called after frontend Google Sign-In.
  Creates/updates user profile.

  Requires: Authorization header with Firebase ID token
  """
  user = require_auth(user)
  save_or_update_user(user)

  return {
    "uid": user["uid"],
    "email": user.get("email"),
    "display_name": user.get("name"),
    "photo_url": user.get("picture"),
  }


@app.post("/api/analyze")
async def analyze_profile(
  description: UserDescription,
  background_tasks: BackgroundTasks,
  user=Depends(get_current_user),
):
  """
  Start analysis pipeline with immediate results + background discovery.

  Flow:
  1. Check cache for exact search text
  2. If cache hit: Return cached results immediately
  3. If cache miss:
     a. Extract facets (or use provided facets)
     b. Query DB for existing matches
     c. Return facets + existing figures immediately
     d. Start background discovery task
  4. If user authenticated: Save to search history
  """
  # Check cache first
  cached = get_cached_search(description.text)

  if cached:
    print(f"[CACHE HIT] Using cached results for: {description.text[:50]}...")

    # If authenticated, still save to user history
    if user:
      background_tasks.add_task(
        save_user_search,
        user["uid"],
        description.text,
        cached["social_model"],
        cached["figure_names"],
        cached["facets"],
      )

    return {
      "status": "cache_hit",
      "message": "Results found in cache",
      "social_model": cached["social_model"],
      "figure_names": cached["figure_names"],
      "facets": cached["facets"],
    }

  # Cache miss - extract facets and query DB immediately
  user_id = user["uid"] if user else None

  try:
    # Validate that social_model has at least one non-empty field if provided
    provided_social_model = description.social_model
    if provided_social_model:
      has_facets = any(
        provided_social_model.get(field)
        for field in [
          "race",
          "ethnicity",
          "cultural_background",
          "gender",
          "sexuality",
          "interests",
          "aspirations",
          "location",
        ]
      )

      if not has_facets:
        raise HTTPException(
          status_code=400, detail="social_model must have at least one non-empty field"
        )

    # Phase 1: Immediate - Extract facets + query existing matches
    social_model, facets, existing_figures = orchestrator.extract_and_query_immediate(
      description.text,
      provided_facets=description.facets,
      provided_social_model=description.social_model,
    )

    # Convert social model to dict
    social_model_dict = {
      "race": social_model.race or [],
      "ethnicity": social_model.ethnicity or [],
      "cultural_background": social_model.cultural_background or [],
      "gender": social_model.gender or [],
      "sexuality": social_model.sexuality or [],
      "interests": social_model.interests or [],
      "aspirations": social_model.aspirations or [],
    }

    # Save search immediately if authenticated (before background discovery)
    # This ensures the search is persisted even if discovery fails
    # Include existing figure names from immediate query results
    search_id = None
    if user_id:
      existing_figure_names = [
        fig.get("name", "") for fig in existing_figures if fig.get("name")
      ]
      search_id = save_user_search(
        user_id,
        description.text,
        social_model_dict,
        existing_figure_names,  # Start with existing matches
        facets,
      )

    # Phase 2: Background - Discover new figures
    background_tasks.add_task(
      orchestrator.run_background_discovery,
      description.text,
      social_model,
      facets,
      user_id,
      search_id,  # Pass search_id so it can update instead of create
    )

    return {
      "status": "processing",
      "message": "Showing existing matches, discovering new figures",
      "social_model": social_model_dict,
      "facets": facets,
      "initial_figures": existing_figures,
      "count": len(existing_figures),
    }

  except Exception as e:
    print(f"[ERROR] Failed to extract and query: {e}")
    import traceback

    traceback.print_exc()

    # Fallback to old behavior
    background_tasks.add_task(
      orchestrator.run_analysis, description.text, user_id=user_id
    )

    return {"status": "processing", "message": "Analysis started"}


@app.post("/api/extract-facets")
async def extract_user_facets(description: UserDescription):
  """
  Extract facets from user's self-description.

  This endpoint analyzes the user's text and returns their inferred
  identity facets (race, ethnicity, interests, aspirations, etc.).

  Features:
  - In-memory caching (1 hour TTL) to avoid redundant LLM calls
  - Request coalescing to deduplicate concurrent identical requests

  Args:
      description: User's self-description text

  Returns:
      {
          "facets": ["Mexican", "neuroscience", "compassion", ...],
          "social_model": {
              "race": ["..."],
              "ethnicity": ["..."],
              ...
          }
      }
  """
  # 1. Check cache first
  cached = get_cached_facets(description.text)
  if cached:
    return cached

  # 2. Use request coalescing to avoid duplicate work for concurrent requests
  async def do_extraction():
    lm = get_extraction_lm()

    # Extract demographics using DSPy
    extractor = dspy.ChainOfThought(DemographicExtraction)

    with dspy.context(lm=lm):
      pred = extractor(user_input=description.text)

    # Build social model
    social_model = SocialModel(
      race=ensure_list(pred.race),
      ethnicity=ensure_list(pred.ethnicity),
      cultural_background=ensure_list(pred.cultural_background),
      gender=ensure_list(pred.gender),
      sexuality=ensure_list(pred.sexuality),
      interests=ensure_list(pred.interests),
      aspirations=ensure_list(pred.aspirations),
    )

    # Get flattened list of all facets
    facets = social_model.as_list(include_goals=True)

    result = {
      "facets": facets,
      "social_model": {
        "race": social_model.race or [],
        "ethnicity": social_model.ethnicity or [],
        "cultural_background": social_model.cultural_background or [],
        "gender": social_model.gender or [],
        "sexuality": social_model.sexuality or [],
        "interests": social_model.interests or [],
        "aspirations": social_model.aspirations or [],
      },
    }

    # Save to cache
    save_facets_to_cache(description.text, result["facets"], result["social_model"])

    return result

  return await coalesced_request(description.text, do_extraction)


@app.get("/api/results")
async def get_results():
  """Retrieve all found historical figures."""
  figures = get_all_figures()
  return figures


@app.get("/api/facets")
async def get_facets():
  """
  Get all unique facets from the database, organized by field.

  Returns:
      Dictionary of {field_name: [sorted_unique_values]}

  Example response:
      {
          "facets": {
              "race": ["Asian", "Black", "White"],
              "ethnicity": ["Hispanic", "Mexican"],
              "interests": ["neuroscience", "compassion"],
              ...
          }
      }
  """
  facets = get_all_facets()
  return {"facets": facets}


@app.get("/api/figures")
async def get_figures_by_facets_exact(
  facets: List[str] = Query(default=None, description="Facet values to filter by"),
  limit: int = Query(
    default=API_DEFAULT_LIMIT, le=API_MAX_LIMIT, description="Max number of results"
  ),
):
  """
  Get historical figures filtered by facets using EXACT matching.

  Query params:
  - facets: List of facet values to match (ANY match, not ALL)
  - limit: Max number of results (default 50, max 200)

  Example:
      /api/figures?facets=Mexican&facets=neuroscience&limit=20

  Returns:
      List of figures where at least one facet matches exactly
  """
  if facets is None:
    facets = []

  results = query_by_facets_exact(facets, limit)
  return {
    "figures": results,
    "count": len(results),
    "query": {"facets": facets, "mode": "exact"},
  }


@app.get("/api/figures/semantic")
async def get_figures_by_facets_semantic(
  facets: List[str] = Query(default=None, description="Facet values to filter by"),
  limit: int = Query(
    default=API_DEFAULT_LIMIT, le=API_MAX_LIMIT, description="Max number of results"
  ),
  min_similarity: float = Query(
    default=DEFAULT_MIN_SIMILARITY,
    ge=0.0,
    le=1.0,
    description="Minimum similarity score",
  ),
):
  """
  Get historical figures filtered by facets using SEMANTIC SIMILARITY.

  This endpoint uses embeddings to find semantically similar facets.
  For example, "Atlanta, Georgia" will match figures with "Texas" based on
  semantic similarity (both are Southern US locations).

  Query params:
  - facets: List of facet values to match
  - limit: Max number of results (default 50, max 200)
  - min_similarity: Minimum similarity threshold 0-1 (default 0.5)

  Example:
      /api/figures/semantic?facets=Mexican&facets=neuroscience&min_similarity=0.6

  Returns:
      List of figures with similarity scores, sorted by relevance

  Example response:
      {
          "figures": [
              {
                  "name": "...",
                  "similarity_score": 0.92,
                  "marginalization_context": "...",
                  ...
              },
              ...
          ],
          "count": 15,
          "query": {...}
      }
  """
  if facets is None:
    facets = []

  # Returns list of (figure_dict, score, facet_scores) tuples
  results_with_scores = query_by_facets_semantic(
    facets, limit=limit, min_similarity=min_similarity
  )

  # Add similarity_score and facet_scores to each figure dict
  figures = []
  for figure_data, score, facet_scores in results_with_scores:
    figure_with_score = {
      **figure_data,
      "similarity_score": round(score, 3),
      "facet_scores": {k: round(v, 3) for k, v in facet_scores.items()},
    }
    figures.append(figure_with_score)

  return {
    "figures": figures,
    "count": len(figures),
    "query": {"facets": facets, "mode": "semantic", "min_similarity": min_similarity},
  }


@app.get("/api/user/searches")
async def get_my_searches(user=Depends(get_current_user)):
  """Get authenticated user's search history."""
  user = require_auth(user)

  searches = get_user_searches(user["uid"])
  return {"searches": searches}


@app.post("/api/user/searches/{search_id}/rerun")
async def rerun_search(search_id: str, user=Depends(get_current_user)):
  """
  Re-execute a past search query.

  This does NOT re-run the analysis pipeline.
  Instead, it queries the database using the saved SocialModel
  to show current matching figures.
  """
  user = require_auth(user)

  # Get the search record
  if not db:
    raise HTTPException(500, "Database not available")

  search_doc = db.collection("user_searches").document(search_id).get()

  if not search_doc.exists:
    raise HTTPException(404, "Search not found")

  search_data = search_doc.to_dict()

  # Verify ownership
  if search_data["user_id"] != user["uid"]:
    raise HTTPException(403, "Not authorized")

  # Extract saved social model and facets
  # social_model is stored flattened (comma-separated strings), unflatten it
  social_model_raw = search_data.get("social_model", {})
  social_model = _unflatten_social_model(social_model_raw)
  facets = search_data.get("facets", [])

  # Query database with these facets
  results_with_scores = query_by_facets_semantic(
    facets, limit=IMMEDIATE_RESULTS_LIMIT, min_similarity=RERUN_MIN_SIMILARITY
  )

  # Format response
  figures = []
  for figure_data, score, facet_scores in results_with_scores:
    figure_with_score = {
      **figure_data,
      "similarity_score": round(score, 3),
      "facet_scores": {k: round(v, 3) for k, v in facet_scores.items()},
    }
    figures.append(figure_with_score)

  return {
    "search_text": search_data.get("search_text"),
    "social_model": social_model,
    "facets": facets,
    "figures": figures,
    "count": len(figures),
  }


@app.delete("/api/user/searches/all")
async def delete_all_searches(user=Depends(get_current_user)):
  """Delete all searches for the authenticated user."""
  user = require_auth(user)

  deleted_count = delete_all_user_searches(user["uid"])

  return {"message": f"Deleted {deleted_count} searches", "deleted": deleted_count}


@app.delete("/api/user/searches/{search_id}")
async def delete_search(search_id: str, user=Depends(get_current_user)):
  """Delete a user's search history entry."""
  user = require_auth(user)

  success = delete_user_search(search_id, user["uid"])

  if not success:
    raise HTTPException(404, "Search not found or unauthorized")

  return {"message": "Search deleted successfully"}


if __name__ == "__main__":
  host = os.getenv("HOST", "0.0.0.0")
  port = int(os.getenv("PORT", "8000"))
  reload = os.getenv("RELOAD", "false").lower() == "true"
  workers = int(os.getenv("WORKERS", "1"))

  uvicorn.run(
    "backend.main:app",
    host=host,
    port=port,
    reload=reload,
    workers=workers if not reload else 1,
  )
