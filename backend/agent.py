import os
import random
import re
import threading
import time
from collections import deque
from concurrent.futures import ThreadPoolExecutor, as_completed
from pprint import pprint
from typing import Any, Dict, List, Optional, Tuple, Union

import dspy
import numpy as np

from backend.config import (
  ASPIRATION_PROBABILITY,
  BASE_RETRY_DELAY,
  DECAY_RATE,
  DEFAULT_COMBINATION_COUNT,
  DEFAULT_MAX_WORKERS,
  DEFAULT_RATE_LIMIT_RPM,
  FIGURES_PER_SEARCH,
  IMAGES_TO_SEARCH,
  INTEREST_PROBABILITY,
  JITTER_FACTOR,
  MAX_NAME_LENGTH,
  MAX_RESEARCH_ATTEMPTS,
  MAX_RETRIES,
  MAX_RETRY_DELAY,
  MAX_WORDS_IN_NAME,
  MIN_ATTRIBUTES_PER_COMBO,
  MIN_WORDS_IN_NAME,
  PROFESSION_PROBABILITY,
  RATE_LIMIT_DELAY_MULTIPLIER,
  RATE_LIMIT_WINDOW_SECONDS,
  RETRY_ATTEMPTS_MULTIPLIER,
)
from backend.database import check_figure_exists, save_figure
from backend.gemini import make_gemini_lm
from backend.models import HistoricalFigure, SocialModel
from backend.tools import search_images_google

# --- Rate Limiting & Retry ---


class RateLimiter:
  """Simple token bucket rate limiter for API calls."""

  def __init__(self, requests_per_minute: int = DEFAULT_RATE_LIMIT_RPM):
    self.requests_per_minute = requests_per_minute
    self.window_seconds = RATE_LIMIT_WINDOW_SECONDS
    self.timestamps = deque()
    self.lock = threading.Lock()

  def acquire(self):
    """Block until a request can be made within rate limits."""
    with self.lock:
      now = time.time()
      # Remove timestamps outside the window
      while self.timestamps and self.timestamps[0] < now - self.window_seconds:
        self.timestamps.popleft()

      # If at capacity, wait
      if len(self.timestamps) >= self.requests_per_minute:
        sleep_time = self.timestamps[0] - (now - self.window_seconds) + 0.1
        if sleep_time > 0:
          time.sleep(sleep_time)
          return self.acquire()

      self.timestamps.append(time.time())


def retry_with_backoff(
  func,
  max_retries=MAX_RETRIES,
  base_delay=BASE_RETRY_DELAY,
  max_delay=MAX_RETRY_DELAY,
):
  """Execute function with exponential backoff retry on failure."""
  for attempt in range(max_retries + 1):
    try:
      return func()
    except Exception as e:
      if attempt == max_retries:
        raise

      # Check if rate limit error
      is_rate_limit = "429" in str(e) or "rate" in str(e).lower()

      delay = min(base_delay * (2**attempt), max_delay)
      delay += random.uniform(0, delay * JITTER_FACTOR)  # Add jitter

      if is_rate_limit:
        delay = min(delay * RATE_LIMIT_DELAY_MULTIPLIER, max_delay)

      print(f"  [RETRY] Attempt {attempt + 1} failed: {e}. Waiting {delay:.1f}s...")
      time.sleep(delay)


# --- Professions for Search Diversity ---

PROFESSIONS = [
  "scientist",
  "artist",
  "writer",
  "musician",
  "activist",
  "politician",
  "inventor",
  "educator",
  "engineer",
  "physician",
  "lawyer",
  "journalist",
  "philosopher",
  "mathematician",
  "architect",
  "entrepreneur",
  "athlete",
  "military leader",
  "religious leader",
  "social worker",
  "economist",
  "historian",
  "psychologist",
  "chef",
  "filmmaker",
]


# --- Helpers ---


def create_demographic_string(combo: Dict[str, str]) -> str:
  """Create a readable string from a demographic combination dictionary."""
  parts = []
  # prioritize certain keys for readability
  order = [
    "race",
    "ethnicity",
    "cultural_background",
    "gender",
    "sexuality",
    "profession",
    "interest",
    "aspiration",
  ]

  for key in order:
    if key in combo:
      parts.append(combo[key])

  # append any others
  for k, v in combo.items():
    if k not in order:
      parts.append(v)

  return ", ".join(parts)


def sample_demographic_combinations(
  demographics: SocialModel,
  num_attribution_combinations: int = DEFAULT_COMBINATION_COUNT,
) -> List[Tuple[str, Dict[str, str]]]:
  """
  Sample diverse demographic combinations from the user's social model.

  Strategy:
  - For each sample, decide whether to include aspiration (50/50 if available)
  - Sample N attributes where N favors smaller numbers (1-2 most common)
  - Sample N specific values (one from each category)
  - Return unique combinations only

  Args:
      demographics: The user's social model
      num_samples: Number of combinations to sample

  Returns:
      List of (demographic_string, demographic_dict) tuples
  """
  # Organize non-empty demographic categories
  demographic_categories = {
    "race": demographics.race or [],
    "ethnicity": demographics.ethnicity or [],
    "cultural_background": demographics.cultural_background or [],
    "gender": demographics.gender or [],
    "sexuality": demographics.sexuality or [],
  }

  # Remove empty categories
  demographic_categories = {k: v for k, v in demographic_categories.items() if v}

  if not demographic_categories:
    return []

  # Check for aspirations and interests
  aspirations = demographics.aspirations or []
  has_aspirations = len(aspirations) > 0

  interests = demographics.interests or []
  has_interests = len(interests) > 0

  # Create flat list of (category, attribute) pairs
  options = []
  for category, values in demographic_categories.items():
    for value in values:
      options.append((category, value))

  combinations = set()
  samples = []

  # Sample with retries to get diverse combinations
  max_attempts = num_attribution_combinations * RETRY_ATTEMPTS_MULTIPLIER
  attempts = 0

  while len(samples) < num_attribution_combinations and attempts < max_attempts:
    attempts += 1

    # Sample number of attributes (favor smaller combinations)
    # Uses exponential decay: P(n) ∝ exp(-λ * (n-2)) for n >= 2
    # This naturally favors smaller values and scales to any max_n
    # Always uses at least MIN_ATTRIBUTES_PER_COMBO attributes (unless only 1 exists)
    max_n = len(options)
    if max_n == 1:
      n_attributes = 1
    else:
      n_values = np.arange(MIN_ATTRIBUTES_PER_COMBO, max_n + 1)
      weights = np.exp(-DECAY_RATE * (n_values - MIN_ATTRIBUTES_PER_COMBO))
      probabilities = weights / weights.sum()
      n_attributes = np.random.choice(n_values, p=probabilities)

    # Sample M attribute pairs (without replacement)
    selected_pairs = random.sample(options, n_attributes)

    # Build demographic combo from selected pairs
    # Deduplicate by value to avoid "Mexican,Mexican" when same value in multiple categories
    demographic_combo = {}
    seen_values = set()
    for category, value in selected_pairs:
      # Skip if we've already seen this value (even in a different category)
      if value in seen_values:
        continue
      demographic_combo[category] = value
      seen_values.add(value)

    # Optionally add interest (configured probability if available)
    if has_interests and random.random() < INTEREST_PROBABILITY:
      demographic_combo["interest"] = random.choice(interests)

    # Optionally add aspiration (configured probability if available)
    if has_aspirations and random.random() < ASPIRATION_PROBABILITY:
      demographic_combo["aspiration"] = random.choice(aspirations)

    # Optionally add profession for search diversity (configured probability)
    if random.random() < PROFESSION_PROBABILITY:
      demographic_combo["profession"] = random.choice(PROFESSIONS)

    # Create string representation
    demographic_str = create_demographic_string(demographic_combo)

    # Check for uniqueness
    if demographic_str not in combinations:
      combinations.add(demographic_str)
      samples.append((demographic_str, demographic_combo))

  return samples


# --- Name Validation ---


def clean_name(name: str) -> str:
  """Clean a name string by removing markdown, quotes, parentheticals, and descriptions."""
  # Remove markdown formatting
  cleaned = re.sub(r"\*+", "", name)
  # Remove trailing parentheticals like "(Top Floor Club)"
  cleaned = re.sub(r"\s*\([^)]*\)\s*$", "", cleaned)
  # Remove leading/trailing quotes
  cleaned = re.sub(r'^["\']+|["\']+$', "", cleaned)
  # Remove " – description" or " - description" suffixes
  cleaned = re.sub(r"\s*[–-]\s+.*$", "", cleaned)
  # Remove ": description" suffixes
  cleaned = re.sub(r":\s+.*$", "", cleaned)
  return cleaned.strip()


def is_valid_person_name(name: str) -> bool:
  """Check if a string looks like a valid person name."""
  if not name:
    return False

  # Reject markdown formatting
  if re.search(r"\*+", name):
    return False

  # Reject quotes at start
  if name.startswith('"') or name.startswith("'"):
    return False

  # Reject if mostly non-alpha characters
  alpha_ratio = sum(c.isalpha() or c.isspace() for c in name) / len(name)
  if alpha_ratio < 0.7:
    return False

  # Reject parenthetical suffixes
  if re.search(r"\([^)]+\)$", name):
    return False

  # Reject if it looks like a description or organization
  org_patterns = [
    r"^(The|A|An)\s",  # Articles at start suggest org/thing, not person
    r"\b(Club|Society|Foundation|Organization|Institute|Company|Inc|LLC|Corp|Corporation)\b",
    r"\b(Movement|Campaign|Project|Initiative|Committee)\b",
  ]
  for pattern in org_patterns:
    if re.search(pattern, name, re.IGNORECASE):
      return False

  # Reject descriptive phrases that are not person names
  descriptive_patterns = [
    r"^(Born|Called|Known|Named|From|Located|Based|Living)\s",  # Start with descriptor
    r"\b(born|from|located|based)\s+(in|at|near)\s+",  # "born in X", "from X"
    r"^(Is|Was|Are|Were|Has|Have|Had)\s",  # Starts with auxiliary verb
    r"^(A|An)\s+\w+\s+(of|from|in)\b",  # "A person of/from/in"
  ]
  for pattern in descriptive_patterns:
    if re.search(pattern, name, re.IGNORECASE):
      return False

  return True


# --- Rejected Names Queue for LLM Extraction ---

# Module-level queue for rejected texts
_rejected_texts = []
_rejected_lock = threading.Lock()


def queue_for_name_extraction(text: str, reason: str):
  """Queue rejected text for later name extraction."""
  with _rejected_lock:
    _rejected_texts.append({"text": text, "reason": reason})


def get_and_clear_rejected_texts():
  """Get all rejected texts and clear the queue."""
  with _rejected_lock:
    texts = _rejected_texts.copy()
    _rejected_texts.clear()
    return texts


def process_rejected_names(existing_names: set = None) -> List[str]:
  """Process queued rejects with LLM to extract valid names.

  Args:
      existing_names: Set of names already found (to avoid duplicates)

  Returns:
      List of extracted valid person names
  """
  rejected = get_and_clear_rejected_texts()
  if not rejected:
    return []

  print(
    f"\n[NAME_EXTRACT] Processing {len(rejected)} rejected texts for salvageable names..."
  )

  # Use fast/cheap model for extraction
  lite_lm = make_gemini_lm(model_name="gemini-2.5-flash-lite")
  extractor = dspy.Predict(ExtractPersonName)

  extracted_names = []
  existing = existing_names or set()

  with dspy.context(lm=lite_lm):
    for item in rejected:
      try:
        result = extractor(text=item["text"])
        name = result.person_name.strip()

        # Validate extracted name
        if not name:
          continue

        # Clean the extracted name too
        name = clean_name(name)

        if not name or not is_valid_person_name(name):
          continue

        # Check word count
        words = name.split()
        if len(words) < MIN_WORDS_IN_NAME or len(words) > MAX_WORDS_IN_NAME:
          continue

        # Skip if already in existing names (case-insensitive)
        if name.lower() in {n.lower() for n in existing}:
          continue

        print(f"  [NAME_EXTRACT] Salvaged: {name}")
        extracted_names.append(name)
        existing.add(name)

      except Exception as e:
        print(f"  [NAME_EXTRACT] Error: {e}")

  print(f"[NAME_EXTRACT] Salvaged {len(extracted_names)} names from rejected text")
  return extracted_names


# --- Signatures ---


class ExtractPersonName(dspy.Signature):
  """Extract a person's full name from text, if one exists.

  Return ONLY the person's name (e.g., "Marie Curie"), or empty string if no valid person name.
  Do NOT return organization names, event names, or descriptions.
  """

  text = dspy.InputField(desc="Text that may contain a person's name")
  person_name = dspy.OutputField(
    desc="Full name of a person, or empty string if none found"
  )


class DemographicExtraction(dspy.Signature):
  """Extract demographic information from user input text.

  CRITICAL: Use | (pipe character) to separate multiple values. ONE concept per value.

  GOOD: interests = "privacy|security|coding|technology criticism"
  GOOD: gender = "non-binary|bigender"
  GOOD: cultural_background = "Southern|Georgian|American"

  BAD: interests = "privacy, security, coding"  <- used comma instead of |
  BAD: gender = "non-binary/bigender"  <- used slash instead of |
  BAD: gender = "bigender (both girl and boy)"  <- has parenthetical explanation
  """

  user_input = dspy.InputField(
    desc="User's text describing their identity and background"
  )
  race = dspy.OutputField(
    desc="Race separated by |. Example: 'Black|White'. Empty string if not mentioned.",
    type=str,
  )
  ethnicity = dspy.OutputField(
    desc="Ethnicity separated by |. Example: 'Hispanic|Irish'. Empty string if not mentioned.",
    type=str,
  )
  cultural_background = dspy.OutputField(
    desc="Cultural background separated by |. Example: 'Southern|Georgian|American'. Empty string if not mentioned.",
    type=str,
  )
  gender = dspy.OutputField(
    desc="Gender identity separated by |. Example: 'non-binary|bigender'. Empty string if not mentioned.",
    type=str,
  )
  sexuality = dspy.OutputField(
    desc="Sexual orientation separated by |. Empty string if not mentioned.",
    type=str,
  )
  interests = dspy.OutputField(
    desc="Interests/hobbies separated by |. Example: 'privacy|security|coding'. Empty string if not mentioned.",
    type=str,
  )
  aspirations = dspy.OutputField(
    desc="Goals/aspirations separated by |. Empty string if not mentioned.",
    type=str,
  )


class ResearchHistoricalFigure(dspy.Signature):
  """Research a historical figure to gather comprehensive biographical and demographic details.

  You are an expert biographer and historian. Your goal is to find accurate, detailed information about a specific historical figure.
  If a field is not applicable or information is unfindable, return an empty list or string.
  """

  person_name = dspy.InputField(desc="Name of the historical figure")
  missing_fields = dspy.InputField(
    desc="List of fields that are currently missing or need more detail"
  )

  # Demographics
  race = dspy.OutputField(
    desc="List of race(s), e.g. ['Black', 'Mixed'].", type=List[str]
  )
  ethnicity = dspy.OutputField(
    desc="List of ethnicity/ethnicities, e.g. ['Hispanic', 'Irish'].", type=List[str]
  )
  cultural_background = dspy.OutputField(
    desc="List of cultural backgrounds, e.g. ['Bolivian', 'New Yorker'].",
    type=List[str],
  )
  location = dspy.OutputField(
    desc="List of locations associated with them, e.g. ['Atlanta, Georgia'].",
    type=List[str],
  )
  gender = dspy.OutputField(desc="Gender identity.", type=List[str])
  sexuality = dspy.OutputField(desc="Sexual orientation.", type=List[str])

  # Interests & Goals
  interests = dspy.OutputField(desc="Interests and hobbies.", type=List[str])
  aspirations = dspy.OutputField(
    desc="Inferred goals, values, and aspirations.", type=List[str]
  )

  # Biography
  marginalization_context = dspy.OutputField(
    desc="Brief context on their marginalized identity (e.g. 'She was a black woman in 19th century America').",
    type=str,
  )
  challenges_faced = dspy.OutputField(
    desc="Detailed description of the specific challenges and obstacles they faced due to their identity or external circumstances (1-2 paragraphs).",
    type=str,
  )
  how_they_overcame = dspy.OutputField(
    desc="Detailed description of how they navigated, resisted, or overcame these challenges to achieve their goals (1-2 paragraphs).",
    type=str,
  )
  achievement = dspy.OutputField(
    desc="1-2 paragraphs describing their major achievements and contributions.",
    type=str,
  )


class FindFiguresWithGoogleSearch(dspy.Signature):
  """Search for forgotten historical figures matching specific demographic combinations.

  Use Google Search to find historical figures from marginalized backgrounds who match
  the given demographic context and goals. You are a cultural historian specializing in
  overlooked narratives, seeking figures whose stories have been marginalized or forgotten.

  CRITICAL: Return ONLY the full legal names of real historical people.
  """

  demographic_context = dspy.InputField(
    desc="Demographic combination to search for (e.g., 'Mexican, neuroscience')"
  )
  goals_context = dspy.InputField(
    desc="Goals and aspirations context to help match relevant figures"
  )
  limit = dspy.InputField(desc="Maximum number of figures to return")
  figure_names = dspy.OutputField(
    desc="ONLY full names of real people, separated by |. Example: 'Marie Curie|Ada Lovelace|Alan Turing'. NO descriptions, NO titles, NO phrases - ONLY names like 'Firstname Lastname'."
  )


# --- Helpers for Search ---


def search_figures_for_demographic_gemini(
  demographic_dict: Dict[str, str],
  goals: Optional[List[str]] = None,
  limit: int = 10,
  debug: bool = False,
  lm=None,
  return_metrics: bool = False,
) -> Union[List[str], Dict[str, Any]]:
  """Search for historical figures using Gemini with Google Search.

  Args:
      demographic_dict: Demographic combination to search for
      goals: User's goals/aspirations for context
      limit: Max figures to return
      debug: Enable debug output
      lm: Language model to use
      return_metrics: If True, return detailed metrics dict instead of just names

  Returns:
      If return_metrics=False: List of valid figure names
      If return_metrics=True: Dict with raw_names, valid_names, rejections, timing
  """
  print("\n" + "=" * 30)
  print(f"Searching via Gemini+Google for (limit: {limit}):")
  pprint(demographic_dict)
  print("=" * 30)

  goals_str = ", ".join(goals) if goals else "their goals and aspirations"

  # Use DSPy Predict with Google Search signature
  searcher = dspy.Predict(
    FindFiguresWithGoogleSearch,
    tools=[{"googleSearch": {}}],
  )

  with dspy.context(lm=lm):
    start_gemini = time.perf_counter()
    result = searcher(
      demographic_context=str(demographic_dict),
      goals_context=goals_str,
      limit=str(limit),
    )
    gemini_time = time.perf_counter() - start_gemini

  if debug:
    print(f"  [TIMING] Gemini+Google search call: {gemini_time:.3f}s")

  # Parse names - split by multiple possible separators
  names_str = result.figure_names.strip()

  raw_names = []
  # Split by pipe first (our preferred separator), then newline, then comma
  for part in names_str.split("|"):
    for line in part.split("\n"):
      for name_part in line.split(","):
        raw_names.append(name_part.strip())

  # Track rejections by category for metrics
  rejections: Dict[str, List[str]] = {
    "too_long": [],
    "sentence_pattern": [],
    "wrong_word_count": [],
    "non_name_pattern": [],
    "bad_start": [],
    "invalid_name": [],
  }

  # Clean up and validate names
  names = []
  for name in raw_names:
    if not name:
      continue
    # Remove leading numbering like "1. ", "2. ", etc.
    cleaned = re.sub(r"^\d+\.\s*", "", name).strip()

    # Use clean_name() for comprehensive cleaning
    cleaned = clean_name(cleaned)

    if not cleaned:
      continue

    # Check with is_valid_person_name() first (catches markdown, quotes, etc.)
    if not is_valid_person_name(cleaned):
      print(f"  [SKIP] Invalid name format: {cleaned[:50]}...")
      rejections["invalid_name"].append(cleaned[:100])
      # Queue for potential LLM extraction if it's long enough to contain a name
      if len(cleaned) > 10:
        queue_for_name_extraction(cleaned, "invalid_format")
      continue

    # Validate: reject entries that are clearly not names
    # Names should be short (typically 2-5 words, max configured chars)
    if len(cleaned) > MAX_NAME_LENGTH:
      print(f"  [SKIP] Too long to be a name: {cleaned[:50]}...")
      rejections["too_long"].append(cleaned[:100])
      # Queue for LLM extraction - may contain a valid name buried in description
      queue_for_name_extraction(cleaned, "too_long")
      continue

    # Reject entries with sentence-like patterns
    sentence_patterns = [
      r"\b(is|was|are|were|has|have|had|the|a|an|who|which|that|this|these|those)\b",
      r"\b(represents|explores|discusses|earned|received|wrote|published|works|worked)\b",
      r"(?<!Dr)(?<!Mr)(?<!Ms)(?<!Mrs)(?<!Jr)(?<!Sr)\.\s+[A-Z]",  # Sentence break (excluding honorifics)
      r"^\s*[\"']",  # Starts with quote
      r"specifically|regarding|intersection|infrastructure|including|extensively",
      r"\bshe\b|\bhe\b|\bher\b|\bhis\b|\btheir\b",  # Pronouns
      r"^(born|called|known|named|from|located)\s",  # Descriptive starts
    ]
    is_sentence = False
    for pattern in sentence_patterns:
      if re.search(pattern, cleaned, re.IGNORECASE):
        is_sentence = True
        break

    if is_sentence:
      print(f"  [SKIP] Looks like description, not name: {cleaned[:50]}...")
      rejections["sentence_pattern"].append(cleaned[:100])
      # Queue for LLM extraction - description may contain a person's name
      queue_for_name_extraction(cleaned, "sentence_pattern")
      continue

    # Validate: names typically have 2-6 capitalized words
    words = cleaned.split()
    if len(words) < MIN_WORDS_IN_NAME or len(words) > MAX_WORDS_IN_NAME:
      print(f"  [SKIP] Wrong word count for name ({len(words)} words): {cleaned}")
      rejections["wrong_word_count"].append(cleaned)
      # Queue longer ones for extraction
      if len(words) > MAX_WORDS_IN_NAME:
        queue_for_name_extraction(cleaned, "wrong_word_count")
      continue

    # Reject common non-name words/phrases
    non_name_patterns = [
      r"^(cultural|values|design|teams|scale|technology|modeling|reality)$",
      r"^(Microsoft|Google|Apple|Amazon|Facebook|Netflix|Adobe)$",  # Company names
      r"^(XR|VR|AR|AI|UX|UI)(\s|$)",  # Tech acronyms at start
      r"\b(at scale|in 3D|bridging|gap)\b",
    ]
    is_non_name = False
    for pattern in non_name_patterns:
      if re.search(pattern, cleaned, re.IGNORECASE):
        is_non_name = True
        break

    if is_non_name:
      print(f"  [SKIP] Detected non-name pattern: {cleaned}")
      rejections["non_name_pattern"].append(cleaned)
      continue

    # Names should start with a capital letter (or Dr./Mr./etc)
    if not re.match(r"^(Dr\.|Mr\.|Ms\.|Mrs\.|[A-Z])", cleaned):
      print(f"  [SKIP] Doesn't start like a name: {cleaned}")
      rejections["bad_start"].append(cleaned)
      continue

    names.append(cleaned)

  print(f"Gemini returned {len(names)} valid figure names")

  if return_metrics:
    return {
      "raw_names": [n for n in raw_names if n],  # Filter empty strings
      "valid_names": names,
      "rejections": rejections,
      "gemini_time_ms": int(gemini_time * 1000),
      "demographic_dict": demographic_dict,
    }

  return names


def _search_worker(args):
  """Worker for parallel demographic search with retry."""
  demo_str, demo_dict, goals, limit, lm, rate_limiter = args
  try:
    rate_limiter.acquire()

    def do_search():
      return search_figures_for_demographic_gemini(
        demographic_dict=demo_dict,
        goals=goals,
        limit=limit,
        lm=lm,
      )

    figures = retry_with_backoff(do_search, max_retries=MAX_RETRIES)
    return (demo_str, demo_dict, figures, None)
  except Exception as e:
    print(f"Error searching for {demo_str}: {e}")
    return (demo_str, demo_dict, [], e)


# --- Modules ---


PLACEHOLDER_VALUES = [
  "none",
  "n/a",
  "not specified",
  "not mentioned",
  "unknown",
  "unspecified",
]


def normalize_facet(value: str) -> Optional[str]:
  """Simple string cleanup for facets - strips punctuation and whitespace."""
  if not value:
    return None
  # Strip whitespace and trailing punctuation
  value = value.strip().rstrip(".,:;!?")
  # Check against existing PLACEHOLDER_VALUES
  if value.lower() in PLACEHOLDER_VALUES:
    return None
  return value if value else None


def ensure_list(val) -> List[str]:
  """Ensure the value is a list of strings, filtering out empty/invalid values.

  Splits items by |, ;, , and / to handle LLM outputs that combine
  multiple values into single items.
  """
  if val is None:
    return []

  # Handle string representations of Python lists (e.g., "['music']")
  if isinstance(val, str):
    val = val.strip()
    if val.startswith("[") and val.endswith("]"):
      try:
        import ast

        parsed = ast.literal_eval(val)
        if isinstance(parsed, list):
          val = parsed
      except (ValueError, SyntaxError):
        pass  # Not a valid Python list literal, treat as regular string

  # First, collect raw items
  raw_items = []
  if isinstance(val, list):
    for v in val:
      if v and str(v).strip():
        raw_items.append(str(v).strip())
  elif isinstance(val, str):
    val = val.strip()
    if val:
      raw_items.append(val)
  else:
    raw_items.append(str(val))

  # Split each item by multiple separators: | ; , /
  final_result = []
  for item in raw_items:
    # First, remove ALL parenthetical content before splitting
    item = re.sub(r"\s*\([^)]*\)", "", item)

    # Split by pipe first (our preferred separator)
    parts = item.split("|")
    for part in parts:
      # Then split by semicolon
      for subpart in part.split(";"):
        # Then split by comma
        for subsubpart in subpart.split(","):
          # Then split by slash
          for value in subsubpart.split("/"):
            value = value.strip()
            # Remove any remaining unmatched parentheses
            value = re.sub(r"[()]", "", value).strip()
            # Normalize the facet (strips punctuation, checks placeholders)
            normalized = normalize_facet(value)
            if normalized:
              final_result.append(normalized)

  # Deduplicate while preserving order (case-insensitive)
  seen = set()
  deduplicated = []
  for item in final_result:
    if item.lower() not in seen:
      seen.add(item.lower())
      deduplicated.append(item)
  return deduplicated


class StoryGeneratorAgent(dspy.Module):
  def __init__(self):
    super().__init__()
    # Configure LM - use context manager instead of global configure
    # to avoid "dspy.settings can only be changed by thread that initially configured it"
    # error when running in ProcessPoolExecutor subprocesses
    self.lm = make_gemini_lm()

    self.extract_demographics = dspy.ChainOfThought(DemographicExtraction)

  def extract_demographics_from_text(self, user_input: str) -> SocialModel:
    """Extract demographics from user input without discovering figures."""
    print("\n" + "=" * 30)
    print("Extracting demographics from:")
    print(user_input)
    print("=" * 30)

    with dspy.context(lm=self.lm):
      pred = self.extract_demographics(user_input=user_input)

    social_model = SocialModel(
      race=ensure_list(pred.race),
      ethnicity=ensure_list(pred.ethnicity),
      cultural_background=ensure_list(pred.cultural_background),
      gender=ensure_list(pred.gender),
      sexuality=ensure_list(pred.sexuality),
      interests=ensure_list(pred.interests),
      aspirations=ensure_list(pred.aspirations),
    )

    print(f"\nInferred attributes:\n{social_model.as_str()}")
    return social_model

  def process_user_request_from_social_model(
    self,
    demographics: SocialModel,
    num_attribution_combinations: int = DEFAULT_COMBINATION_COUNT,
    max_workers: int = DEFAULT_MAX_WORKERS,
  ) -> List[Tuple[str, str]]:
    """Discover figures using parallel searches across demographic combinations."""
    samples = sample_demographic_combinations(
      demographics=demographics,
      num_attribution_combinations=num_attribution_combinations,
    )
    print(f"\nGenerated {len(samples)} combinations")

    if not samples:
      return []

    # Configure rate limiter
    rate_limit_rpm = int(
      os.environ.get("GEMINI_RATE_LIMIT", str(DEFAULT_RATE_LIMIT_RPM))
    )
    rate_limiter = RateLimiter(requests_per_minute=rate_limit_rpm)

    goals = demographics.goals()
    worker_args = [
      (demo_str, demo_dict, goals, FIGURES_PER_SEARCH, self.lm, rate_limiter)
      for demo_str, demo_dict in samples
    ]

    unique_names = set()
    results = []

    print(f"Starting parallel search with {max_workers} workers...")
    start_time = time.perf_counter()

    with ThreadPoolExecutor(max_workers=max_workers) as executor:
      futures = {executor.submit(_search_worker, args): args[0] for args in worker_args}

      for future in as_completed(futures):
        demo_str = futures[future]
        try:
          _, demo_dict, figures, error = future.result()
          if error:
            continue
          for fig in figures:
            if fig not in unique_names:
              unique_names.add(fig)
              results.append((fig, str(demo_dict)))
        except Exception as e:
          print(f"Unexpected error for '{demo_str}': {e}")

    elapsed = time.perf_counter() - start_time
    print(
      f"Parallel search completed in {elapsed:.2f}s, found {len(results)} unique figures"
    )

    # Process rejected names to salvage any valid names from rejected text
    salvaged_names = process_rejected_names(existing_names=unique_names)
    for name in salvaged_names:
      if name not in unique_names:
        unique_names.add(name)
        results.append((name, "salvaged_from_reject"))

    if salvaged_names:
      print(f"Total figures after salvage: {len(results)}")

    return results

  def process_user_request(
    self,
    description: str,
    num_attribution_combinations: int = DEFAULT_COMBINATION_COUNT,
  ) -> List[Tuple[str, str]]:
    """Extract demographics and discover figures (legacy method for backward compatibility)."""
    # 1. Extract demographics
    demographics = self.extract_demographics_from_text(description)

    # 2. Discover figures from social model (now returns list)
    return self.process_user_request_from_social_model(
      demographics, num_attribution_combinations
    )

  def process_person(self, name: str, search_query: str = "", initial: bool = False):
    if check_figure_exists(name):
      print(f"Person {name} already exists in DB. Skipping.")
      return

    print(f"\nProcessing person: {name} (initial={initial})")

    # Initialize profile with available info (just name for now)
    current_data = {"name": name, "search_query": search_query}

    # Research Loop
    attempts = 0

    while attempts < MAX_RESEARCH_ATTEMPTS:
      # Check completeness programmatically
      is_complete, missing_str = self._check_profile_completeness(current_data)

      if is_complete:
        print(f"  Profile for {name} is complete.")
        break
      print(f"  Status: {missing_str}")

      # Research Step
      researcher = dspy.Predict(
        ResearchHistoricalFigure,
        tools=[{"googleSearch": {}}],
      )

      try:
        with dspy.context(lm=self.lm):
          result = researcher(person_name=name, missing_fields=missing_str)

        # Directly access fields from the prediction result
        # We prioritize new non-empty info
        # Note: image_url excluded - Gemini search returns poor image URLs
        # We rely on search_images_google() + validation instead
        for field in [
          "race",
          "ethnicity",
          "cultural_background",
          "location",
          "gender",
          "sexuality",
          "interests",
          "aspirations",
          "marginalization_context",
          "challenges_faced",
          "how_they_overcame",
          "achievement",
        ]:
          if hasattr(result, field):
            val = getattr(result, field)
            # Basic validation/cleaning
            if val:
              if isinstance(val, list):
                # Clean list - filter out placeholder values
                cleaned = [
                  str(v)
                  for v in val
                  if v and str(v).strip().lower() not in PLACEHOLDER_VALUES
                ]
                if cleaned:
                  current_data[field] = cleaned
              elif isinstance(val, str):
                if val.strip().lower() not in PLACEHOLDER_VALUES:
                  current_data[field] = val

      except Exception as e:
        print(f"  Error during research step: {e}")

      attempts += 1

    # Finalize and Save
    print(f"  Finalizing profile for {name}...")

    # Search for valid image (already validated by search_images_google with parallel validation)
    print("  Searching for valid image via Google Image Search...")

    # Build descriptive image search query for disambiguation
    image_query_parts = [name]

    # Add achievement or interests for disambiguation
    achievement = current_data.get("achievement", "")
    if achievement:
      # Extract key descriptor (first sentence fragment, up to 50 chars)
      short_achievement = achievement.split(".")[0][:50].strip()
      image_query_parts.append(short_achievement)
    elif current_data.get("interests"):
      image_query_parts.append(current_data["interests"][0])

    image_query = " ".join(image_query_parts)
    validated_images = search_images_google(image_query, num_images=IMAGES_TO_SEARCH)

    if validated_images:
      current_data["image_url"] = validated_images[0]
      print("    Found valid image")
    else:
      print("    No valid images found")
      current_data["image_url"] = None

    # Construct SocialModel tags
    tags = SocialModel(
      race=ensure_list(current_data.get("race")),
      ethnicity=ensure_list(current_data.get("ethnicity")),
      cultural_background=ensure_list(current_data.get("cultural_background")),
      location=ensure_list(current_data.get("location")),
      gender=ensure_list(current_data.get("gender")),
      sexuality=ensure_list(current_data.get("sexuality")),
      interests=ensure_list(current_data.get("interests")),
      aspirations=ensure_list(current_data.get("aspirations")),
    )

    # Construct HistoricalFigure
    # Ensure we have strings for text fields
    fig = HistoricalFigure(
      name=current_data.get("name", name),
      marginalization_context=str(current_data.get("marginalization_context", "")),
      challenges_faced=str(current_data.get("challenges_faced", "")),
      how_they_overcame=str(current_data.get("how_they_overcame", "")),
      achievement=str(current_data.get("achievement", "")),
      image_url=current_data.get("image_url"),
      tags=tags,
      search_queries_used=[current_data.get("search_query", "")],
      initial=initial,
    )

    # Save
    save_figure(fig.model_dump())

  def _check_profile_completeness(self, data: Dict[str, Any]) -> Tuple[bool, str]:
    """
    Programmatically check if the profile has sufficient information.

    Required:
    - At least one demographic tag (race, ethnicity, or cultural_background)
    - marginalization_context (non-empty)
    - achievement (non-empty)
    """
    missing = []

    # Check demographics
    has_demographics = False
    for field in ["race", "ethnicity", "cultural_background"]:
      val = data.get(field)
      # either list of things or single thing
      if val and isinstance(val, list) and len(val) > 0:
        has_demographics = True
        break
      elif val and isinstance(val, str) and len(val) > 0:
        has_demographics = True
        break

    if not has_demographics:
      missing.append("Demographics (race/ethnicity/cultural_background)")

    # Check bio fields
    if not data.get("marginalization_context"):
      missing.append("marginalization_context")
    if not data.get("challenges_faced"):
      missing.append("challenges_faced")
    if not data.get("how_they_overcame"):
      missing.append("how_they_overcame")
    if not data.get("achievement"):
      missing.append("achievement")

    if missing:
      return False, f"Missing fields: {', '.join(missing)}"
    return True, "Complete"


if __name__ == "__main__":
  import sys

  import dspy

  dspy.settings.configure(cache=False)

  user_description = (
    " ".join(sys.argv[1:])
    if len(sys.argv) > 1
    else "Significant historical figures from marginalized backgrounds in science."
  )

  agent = StoryGeneratorAgent()
  for name, query in agent.process_user_request(
    user_description, num_attribution_combinations=1
  ):
    agent.process_person(name, search_query=query)
