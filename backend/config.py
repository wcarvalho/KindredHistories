"""
Centralized configuration constants for the Kindred Histories backend.

This module contains all tunable parameters organized by functional area.
Constants that work together are documented in groups explaining their
interactions.
"""

# ============================================================================
# CACHE CONFIGURATION
# ============================================================================
# These control how long different types of cached data remain valid.

FACETS_CACHE_TTL_SECONDS = 300
"""How long (seconds) to cache the aggregated facets from all figures.
Used by get_all_facets() in database.py to avoid repeated Firestore scans.
5 minutes balances freshness with query performance."""

SEARCH_CACHE_TTL_DAYS = 30
"""How long (days) to cache search results in Firestore's search_cache collection.
When a user submits the same search text within this period, results are
returned from cache without re-running the discovery pipeline."""

# ============================================================================
# DATABASE QUERY LIMITS
# ============================================================================
# These constants work together to control Firestore query behavior.
# The semantic search pipeline uses them in sequence:
#   1. Fetch up to DEFAULT_CANDIDATE_LIMIT figures for scoring
#   2. Score and filter to DEFAULT_RESULTS_LIMIT results
#   3. MAX_FACETS_PER_QUERY limits Firestore's array-contains-any

MAX_FACETS_PER_QUERY = 30
"""Firestore hard limit for array-contains-any queries. Cannot be changed."""

DEFAULT_CANDIDATE_LIMIT = 200
"""Max figures to fetch from Firestore before semantic scoring.
Higher = better recall but slower. Used by query_by_facets_semantic()."""

DEFAULT_RESULTS_LIMIT = 50
"""Default number of results returned by query endpoints.
This is the final output limit after scoring and ranking."""

FACETS_REFRESH_LIMIT = 500
"""Max figures to scan when rebuilding the facets cache.
Prevents Firestore timeout on get_all_facets() for large collections."""

# ============================================================================
# SEMANTIC SEARCH THRESHOLDS
# ============================================================================
# Similarity thresholds control result quality vs quantity tradeoff.

DEFAULT_MIN_SIMILARITY = 0.2
"""Minimum similarity score (0-1) for initial/immediate search results.
Lower threshold shows more results with weaker matches. Used when user
first submits a search via /api/analyze and /api/figures/semantic."""

RERUN_MIN_SIMILARITY = 0.3
"""Minimum similarity for re-running past searches from user history.
Slightly higher than default because user explicitly chose to revisit."""

API_MAX_LIMIT = 200
"""Maximum value allowed for 'limit' query parameter in API endpoints.
Prevents clients from requesting unbounded result sets."""

# ============================================================================
# NAME VALIDATION
# ============================================================================
# Used by search_figures_for_demographic_gemini() in agent.py to filter
# LLM output. Gemini sometimes returns descriptions instead of names.

MAX_NAME_LENGTH = 60
"""Maximum character length for a valid person name.
Entries longer than this are rejected as likely descriptions."""

SPLIT_THRESHOLD_LENGTH = 40
"""When parsing "Name - Description" patterns, only split if the
name portion is shorter than this. Prevents splitting actual names
that contain hyphens."""

MIN_WORDS_IN_NAME = 2
"""Minimum words in a valid name (e.g., "Marie Curie" = 2 words).
Single words are rejected as incomplete names."""

MAX_WORDS_IN_NAME = 6
"""Maximum words in a valid name. Names like
"Martin Luther King Jr." (4 words) pass; longer entries are likely
descriptions or titles."""

# ============================================================================
# DEMOGRAPHIC SAMPLING
# ============================================================================
# These control sample_demographic_combinations() which generates diverse
# search queries from the user's social model. The algorithm:
#   1. Generate DEFAULT_COMBINATION_COUNT unique combinations
#   2. Each has MIN_ATTRIBUTES_PER_COMBO+ attributes, favoring smaller via DECAY_RATE
#   3. Optionally add interest/aspiration/profession based on probabilities
#   4. Retry up to (count * RETRY_ATTEMPTS_MULTIPLIER) times to find unique combos

DEFAULT_COMBINATION_COUNT = 15
"""Number of demographic combinations to generate for parallel search.
More = wider coverage but more API calls."""

MIN_ATTRIBUTES_PER_COMBO = 2
"""Minimum demographic attributes per search combination.
At least 2 ensures meaningful intersection (e.g., "Mexican" + "scientist")."""

DECAY_RATE = 0.7
"""Exponential decay rate for attribute count sampling.
Higher = stronger preference for smaller combinations.
P(n attributes) ~ exp(-DECAY_RATE * (n - MIN_ATTRIBUTES_PER_COMBO))"""

INTEREST_PROBABILITY = 0.5
"""Probability of including a user interest in each combination."""

ASPIRATION_PROBABILITY = 0.5
"""Probability of including a user aspiration in each combination."""

PROFESSION_PROBABILITY = 0.5
"""Probability of adding a random profession for search diversity.
Helps find figures across different career paths."""

RETRY_ATTEMPTS_MULTIPLIER = 3
"""Max sampling attempts = DEFAULT_COMBINATION_COUNT * this value.
Ensures we find enough unique combinations even with collisions."""

# ============================================================================
# RETRY & RATE LIMITING
# ============================================================================
# These work together in retry_with_backoff() and RateLimiter class.
# Exponential backoff formula: delay = min(BASE * 2^attempt, MAX) + jitter
# Rate limit errors get extra delay via RATE_LIMIT_DELAY_MULTIPLIER.

DEFAULT_RATE_LIMIT_RPM = 1000
"""Gemini API rate limit (requests per minute) for paid tier.
Can be overridden via GEMINI_RATE_LIMIT environment variable."""

RATE_LIMIT_WINDOW_SECONDS = 60
"""Sliding window size for rate limiter. Tracks requests within this period."""

MAX_RETRIES = 3
"""Maximum retry attempts before failing permanently."""

BASE_RETRY_DELAY = 1.0
"""Initial delay (seconds) before first retry. Doubles each attempt."""

MAX_RETRY_DELAY = 30.0
"""Maximum delay between retries, caps exponential growth."""

BACKOFF_MULTIPLIER = 2
"""Multiplier for exponential backoff (delay doubles each retry)."""

JITTER_FACTOR = 0.1
"""Random jitter as fraction of delay. Prevents thundering herd.
Actual jitter = random(0, delay * JITTER_FACTOR)."""

RATE_LIMIT_DELAY_MULTIPLIER = 2
"""Extra delay multiplier when rate limit (429) errors are detected.
Rate limit delay = normal_delay * this value."""

# ============================================================================
# FIGURE PROCESSING
# ============================================================================
# Control the research loop in process_person() and discovery phase.

MAX_RESEARCH_ATTEMPTS = 3
"""Maximum LLM research iterations per historical figure.
Each attempt tries to fill missing profile fields."""

FIGURES_PER_SEARCH = 3
"""Target number of figure names to request from each demographic search.
Total discovered ~ DEFAULT_COMBINATION_COUNT * FIGURES_PER_SEARCH (minus duplicates)."""

IMAGES_TO_SEARCH = 1
"""Number of validated images to fetch per figure via Google Image Search."""

# ============================================================================
# CONCURRENCY
# ============================================================================
# Control parallel processing in Orchestrator and agent.

DEFAULT_MAX_WORKERS = 10
"""Thread pool size for parallel demographic searches and figure processing.
Balances throughput with API rate limits."""

DEBUG_MAX_WORKERS = 1
"""Worker count when DEBUG=1 env var is set. Sequential processing for debugging."""

IMMEDIATE_RESULTS_LIMIT = 100
"""Max existing figures to return immediately from DB before background
discovery starts. Provides instant results while new figures are researched."""

# ============================================================================
# API DEFAULTS
# ============================================================================

API_DEFAULT_LIMIT = 50
"""Default 'limit' parameter for /api/figures endpoints when not specified."""

USER_SEARCH_HISTORY_LIMIT = 20
"""Default number of past searches to return in user history endpoint."""

# ============================================================================
# EXACT-MATCH BOOSTING
# ============================================================================
# When a facet phrase appears verbatim in a figure's profile text, boost
# that facet's similarity score. This helps prioritize figures that explicitly
# mention the searched trait over semantic-only matches.
# Example: "Bolivian" facet should rank actual Bolivians higher than
# semantically similar Hispanics who aren't from Bolivia.

EXACT_MATCH_BOOST_ENABLED = True
"""Enable exact-match boosting for facet similarity scores.
When True, facets that appear verbatim in figure text get their score multiplied."""

EXACT_MATCH_BOOST_MULTIPLIER = 2.0
"""Score multiplier for facets with exact text matches.
Final score is capped at 1.0 (e.g., 0.6 * 2.0 = 1.0, not 1.2)."""

EXACT_MATCH_CASE_SENSITIVE = False
"""Whether exact matching is case-sensitive.
False (default): 'bolivian' matches 'Bolivian'."""

EXACT_MATCH_PENALTY_MULTIPLIER = 0.3
"""Score multiplier for facets WITHOUT exact text matches.
Penalizes semantic-only matches to create separation between
exact and non-exact matches for AND/OR filtering."""
