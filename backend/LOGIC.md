# Backend Logic & Pipeline Documentation

This document explains the logical flow of the `story-generator-2` backend, specifically focusing on the `StoryGeneratorAgent` pipeline. This is intended to assist in writing tests and understanding the system architecture.

## High-Level Overview

The system takes a user description (e.g., "I am a Mexican neuroscientist..."), identifies their identity attributes, searches for "forgotten" historical figures matching those attributes, and then autonomously researches and profiles those figures.

### Core Components

1.  **API (`backend/main.py`)**: Entry point. Receives HTTP requests and offloads work to the Orchestrator.
2.  **Orchestrator (`backend/logic.py`)**: Manages concurrency. Splits the work into identifying people (sequential/serial) and researching them (parallel).
3.  **Agent (`backend/agent.py`)**: Contains the core business logic and LLM interactions using DSPy.

---

## Detailed Pipeline Flow

### 1. `process_user_request(description)`
**Location:** `backend/agent.py` -> `StoryGeneratorAgent.process_user_request`

This is the first stage of the pipeline, responsible for taking raw text and turning it into a list of candidate historical figures.

#### Step 1.1: Infer Attributes
*   **Goal**: Extract structured identity markers from natural language.
*   **Module**: `DemographicExtraction` (DSPy ChainOfThought)
*   **Input**: `description` (str)
*   **Output**: `DemographicExtraction` prediction (race, ethnicity, etc.) mapped to `SocialModel` object.

#### Step 1.2: Generate Combinations
*   **Goal**: Create search angles to find people based on the attributes.
*   **Method**: `sample_demographic_combinations` (Helper Function)
*   **Input**: `demographics` (SocialModel)
*   **Output**: List of `(demographic_string, demographic_dict)` tuples.
*   **Logic**: Probabilistically samples attributes favoring smaller combinations (2-3 attributes) for broader search.

#### Step 1.3: Find People (Loop)
*   **Goal**: Execute searches using Gemini + Google Search to find historical figures.
*   **Method**: `search_figures_for_demographic_gemini` (Helper Function)
*   **Iterates over**: The list of samples from Step 1.2.
*   **Underlying Signature**: `SearchFiguresWithGoogleSearch` (DSPy Predict with tools)
*   **Input**: `demographics`, `demographic_str`
*   **Output**: List of `HistoricalFigure` objects.
*   **Yields**: Unique names from the found figures.

---

### 2. `process_person(name)`
**Location:** `backend/agent.py` -> `StoryGeneratorAgent.process_person`

This is the second stage, often run in parallel processes by the Orchestrator. It takes a name and builds a full profile.

#### Step 2.1: Existence Check
*   Checks `database.check_figure_exists(name)`. If true, skips processing.

#### Step 2.2: Research & Verification Loop (The "Modeller" Loop)
This loop continues until the profile is "complete" or `max_attempts` (default 3) is reached.

**Loop Iteration:**
1.  **Plan Search**:
### 2. process_person (Refined Loop)

Takes a name, checks if it exists in the DB, and if not, researches it thoroughly.

1.  **Check DB**: Skips if person already exists.
2.  **Research Loop** (max attempts):
    *   **Check Completeness**: Programatically checks for required fields:
        *   Demographics (at least one of race, ethnicity, cultural_background)
        *   `marginalization_context` (non-empty string)
        *   `achievement` (non-empty string)
    *   **Research**: If incomplete, calls `ResearchHistoricalFigure` using `dspy.Predict` with `tools=[{"googleSearch": {}}]`.
        *   **Signature**: `ResearchHistoricalFigure` (Inputs: `person_name`, `missing_fields` -> Outputs: individual fields for `race`, `ethnicity`, `bio`, etc.)
    *   **Update**: Merges new non-empty fields into the profile.
3.  **Finalize**:
    *   **Image**: Fetches image URL via Google Image Search if missing.
    *   **Tags**: Constructs `SocialModel` tags from gathered demographics.
    *   **Save**: Saves `HistoricalFigure` to Firestore (triggering embedding generation).

---

## Test & Debug Helpers (`backend/test_agent.py`)

The file `backend/test_agent.py` contains individual functions that map directly to these steps (`debug_attributes`, `debug_combinations`, etc.). When writing new tests, you can mock `dspy.ChainOfThought` or the underlying `dspy.LM` to return deterministic responses for these modules.
