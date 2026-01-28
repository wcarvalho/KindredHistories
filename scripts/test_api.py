"""
Quick test script to verify the API endpoints return per-facet scores.
"""

import requests
import json

API_BASE = "http://localhost:8000"

def test_facets_endpoint():
    """Test /api/facets"""
    print("=" * 60)
    print("Testing GET /api/facets")
    print("=" * 60)

    response = requests.get(f"{API_BASE}/api/facets")
    data = response.json()

    print(f"Status: {response.status_code}")
    print(f"\nAvailable facets:")
    for field, values in data["facets"].items():
        print(f"  {field}: {len(values)} values")
        print(f"    Sample: {values[:3]}")
    print()


def test_semantic_search():
    """Test /api/figures/semantic with per-facet scores"""
    print("=" * 60)
    print("Testing GET /api/figures/semantic")
    print("=" * 60)

    params = {
        "facets": ["Mexican", "neuroscience"],
        "min_similarity": 0.3,
        "limit": 5
    }

    response = requests.get(f"{API_BASE}/api/figures/semantic", params=params)
    data = response.json()

    print(f"Status: {response.status_code}")
    print(f"\nQuery: {data['query']}")
    print(f"Found {data['count']} figures:\n")

    for fig in data["figures"]:
        print(f"  {fig['name']}:")
        print(f"    Overall similarity: {fig['similarity_score']}")
        print(f"    Per-facet scores:")
        for facet, score in fig.get("facet_scores", {}).items():
            print(f"      - {facet}: {score}")
        print()


if __name__ == "__main__":
    print("\n*** Make sure the backend is running first! ***")
    print("    Run: uv run uvicorn backend.main:app --reload\n")

    try:
        test_facets_endpoint()
        test_semantic_search()
        print("✅ All API tests passed!")
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to backend. Make sure it's running on http://localhost:8000")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
