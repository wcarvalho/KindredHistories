"""
Test script for faceted search with semantic similarity.

This script demonstrates:
1. Saving figures with per-facet embeddings
2. Exact facet matching
3. Semantic similarity matching
"""

from backend.database import (
  get_all_facets,
  query_by_facets_exact,
  query_by_facets_semantic,
  save_figure,
)


def create_test_figures():
  """Create test historical figures with various facets."""

  test_figures = [
    {
      "name": "Sylvia Mendez",
      "marginalization_context": "Mexican-American civil rights activist who fought school segregation in California.",
      "achievement": "Her family's lawsuit (Mendez v. Westminster) ended school segregation in California, paving the way for Brown v. Board of Education.",
      "image_url": "https://example.com/sylvia.jpg",
      "tags": {
        "race": ["Latino"],
        "ethnicity": ["Mexican-American"],
        "cultural_background": ["Mexican", "Californian"],
        "gender": ["female"],
        "interests": ["civil rights", "education equality"],
        "aspirations": ["end segregation", "equal education"],
      },
    },
    {
      "name": "Chien-Shiung Wu",
      "marginalization_context": "Chinese-American physicist who faced discrimination in academia despite groundbreaking work.",
      "achievement": "Made crucial contributions to the Manhattan Project and disproved the law of conservation of parity in physics.",
      "image_url": "https://example.com/wu.jpg",
      "tags": {
        "race": ["Asian"],
        "ethnicity": ["Chinese-American"],
        "cultural_background": ["Chinese", "New Yorker"],
        "gender": ["female"],
        "interests": ["physics", "nuclear research"],
        "aspirations": ["scientific discovery", "break barriers in science"],
      },
    },
    {
      "name": "Bayard Rustin",
      "marginalization_context": "Gay African-American civil rights leader who organized the March on Washington but was often sidelined due to his sexuality.",
      "achievement": "Chief organizer of the 1963 March on Washington and key strategist in the civil rights movement.",
      "image_url": "https://example.com/rustin.jpg",
      "tags": {
        "race": ["Black"],
        "ethnicity": ["African-American"],
        "cultural_background": ["Southern United States"],
        "gender": ["male"],
        "sexuality": ["gay"],
        "interests": ["civil rights", "nonviolent resistance", "social justice"],
        "aspirations": ["equality", "end discrimination"],
      },
    },
    {
      "name": "Jovita Idár",
      "marginalization_context": "Mexican-American journalist and activist who defended the rights of Mexican immigrants in Texas.",
      "achievement": "Founded La Liga Femenil Mexicanista and stood up to Texas Rangers trying to shut down her newspaper.",
      "image_url": "https://example.com/idar.jpg",
      "tags": {
        "race": ["Latino"],
        "ethnicity": ["Mexican-American"],
        "cultural_background": ["Mexican", "Texan"],
        "gender": ["female"],
        "interests": ["journalism", "immigrant rights", "women's rights"],
        "aspirations": ["protect immigrants", "empower women"],
      },
    },
    {
      "name": "Mary Golda Ross",
      "marginalization_context": "Cherokee aerospace engineer who was the first known Native American female engineer.",
      "achievement": "Worked on aerospace projects at Lockheed, including conceptual designs for interplanetary space travel.",
      "image_url": "https://example.com/ross.jpg",
      "tags": {
        "race": ["Native American"],
        "ethnicity": ["Cherokee"],
        "cultural_background": ["Cherokee Nation", "Oklahoma"],
        "gender": ["female"],
        "interests": ["aerospace engineering", "mathematics", "space exploration"],
        "aspirations": ["space travel", "represent Native Americans in STEM"],
      },
    },
  ]

  print("=" * 60)
  print("Creating test figures with embeddings...")
  print("=" * 60)

  for fig in test_figures:
    print(f"\nSaving: {fig['name']}")
    save_figure(fig, generate_embeddings=True)

  print("\n" + "=" * 60)
  print("Test figures created successfully!")
  print("=" * 60)


def test_exact_matching():
  """Test exact facet matching."""
  print("\n" + "=" * 60)
  print("TEST 1: EXACT FACET MATCHING")
  print("=" * 60)

  # Test 1: Search for Mexican-American figures
  print("\n1. Searching for 'Mexican-American' (exact match):")
  results = query_by_facets_exact(["Mexican-American"], limit=10)
  print(f"   Found {len(results)} figures:")
  for fig in results:
    print(f"   - {fig['name']}")

  # Test 2: Search for civil rights interest
  print("\n2. Searching for 'civil rights' interest (exact match):")
  results = query_by_facets_exact(["civil rights"], limit=10)
  print(f"   Found {len(results)} figures:")
  for fig in results:
    print(f"   - {fig['name']}")

  # Test 3: Multiple facets (ANY match)
  print("\n3. Searching for 'female' AND 'physics' (ANY match):")
  results = query_by_facets_exact(["female", "physics"], limit=10)
  print(f"   Found {len(results)} figures:")
  for fig in results:
    print(f"   - {fig['name']}")


def test_semantic_matching():
  """Test semantic facet matching."""
  print("\n" + "=" * 60)
  print("TEST 2: SEMANTIC SIMILARITY MATCHING")
  print("=" * 60)

  # Test 1: "Atlanta, Georgia" should match "Southern United States" and "Texas"
  print("\n1. Searching for 'Southern United States (Atlanta, Georgia)':")
  print("   (Should match figures from Texas, Southern US, etc.)")
  results = query_by_facets_semantic(
    ["Southern United States (Atlanta, Georgia)"], limit=10, min_similarity=0.4
  )
  print(f"   Found {len(results)} figures:")
  for fig_data, score, facet_scores in results:
    facets = fig_data.get("facets", [])
    cultural = [
      f
      for f in facets
      if any(geo in f for geo in ["Texas", "Southern", "California", "Oklahoma"])
    ]
    print(f"   - {fig_data['name']}: similarity={score:.3f}, cultural_bg={cultural}")
    print(f"     Per-facet scores: {facet_scores}")

  # Test 2: "neuroscience" should match "physics", "biology", etc.
  print("\n2. Searching for 'neuroscience':")
  print("   (Should match science-related interests like physics, mathematics)")
  results = query_by_facets_semantic(["neuroscience"], limit=10, min_similarity=0.3)
  print(f"   Found {len(results)} figures:")
  for fig_data, score, facet_scores in results:
    interests = fig_data.get("tags", {}).get("interests", [])
    print(f"   - {fig_data['name']}: similarity={score:.3f}, interests={interests}")
    print(f"     Per-facet scores: {facet_scores}")

  # Test 3: Multiple facets
  print("\n3. Searching for 'Mexican' + 'fighting for equality':")
  print("   (Should match civil rights activists, immigrant rights activists)")
  results = query_by_facets_semantic(
    ["Mexican", "fighting for equality"], limit=10, min_similarity=0.4
  )
  print(f"   Found {len(results)} figures:")
  for fig_data, score, facet_scores in results:
    aspirations = fig_data.get("tags", {}).get("aspirations", [])
    ethnicity = fig_data.get("tags", {}).get("ethnicity", [])
    print(
      f"   - {fig_data['name']}: similarity={score:.3f}, ethnicity={ethnicity}, aspirations={aspirations}"
    )
    print(f"     Per-facet scores: {facet_scores}")


def test_get_all_facets():
  """Test getting all unique facets."""
  print("\n" + "=" * 60)
  print("TEST 3: GET ALL FACETS")
  print("=" * 60)

  facets = get_all_facets()

  for field, values in facets.items():
    print(f"\n{field}:")
    for val in values:
      print(f"  - {val}")


if __name__ == "__main__":
  import sys

  if "--create" in sys.argv:
    create_test_figures()

  if "--test-exact" in sys.argv or "--test-all" in sys.argv:
    test_exact_matching()

  if "--test-semantic" in sys.argv or "--test-all" in sys.argv:
    test_semantic_matching()

  if "--test-facets" in sys.argv or "--test-all" in sys.argv:
    test_get_all_facets()

  if len(sys.argv) == 1:
    print("Usage:")
    print(
      "  uv run python -m backend.test_facet_search --create          # Create test figures"
    )
    print(
      "  uv run python -m backend.test_facet_search --test-exact      # Test exact matching"
    )
    print(
      "  uv run python -m backend.test_facet_search --test-semantic   # Test semantic matching"
    )
    print(
      "  uv run python -m backend.test_facet_search --test-facets     # Test get all facets"
    )
    print(
      "  uv run python -m backend.test_facet_search --test-all        # Run all tests"
    )
    print("\nRecommended: Run --create first, then --test-all")
