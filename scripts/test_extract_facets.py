"""
Test the /api/extract-facets endpoint.
"""

import requests
import json

API_BASE = "http://localhost:8000"

def test_extract_facets():
    """Test facet extraction from user description."""
    print("=" * 60)
    print("Testing POST /api/extract-facets")
    print("=" * 60)

    # Test case 1: Mexican neuroscientist
    description1 = """
    I am Mexican. I am a neuroscientist. I crossed the border to the USA when I was 12.
    I think a lot about how to be a more compassionate person and have to move with compassion
    I feel the suffering of others a lot and I want to make something out of that something good out of it.
    """

    print("\nTest 1: Mexican neuroscientist")
    print(f"Description: {description1.strip()[:100]}...")

    response = requests.post(
        f"{API_BASE}/api/extract-facets",
        json={"text": description1}
    )

    if response.status_code == 200:
        data = response.json()
        print("\n✅ Success!")
        print(f"\nExtracted Facets ({len(data['facets'])} total):")
        for facet in data['facets']:
            print(f"  - {facet}")

        print("\nSocial Model (by field):")
        for field, values in data['social_model'].items():
            if values:
                print(f"  {field}: {', '.join(values)}")
    else:
        print(f"\n❌ Failed with status {response.status_code}")
        print(response.text)

    # Test case 2: Non-binary coder
    description2 = """
    i am girl but also boy. I am super duper into privacy and security and coding
    but I also hate technology and people call me a luddite. I am from atlanta georgia and white passing.
    """

    print("\n" + "=" * 60)
    print("\nTest 2: Non-binary coder from Atlanta")
    print(f"Description: {description2.strip()[:100]}...")

    response = requests.post(
        f"{API_BASE}/api/extract-facets",
        json={"text": description2}
    )

    if response.status_code == 200:
        data = response.json()
        print("\n✅ Success!")
        print(f"\nExtracted Facets ({len(data['facets'])} total):")
        for facet in data['facets']:
            print(f"  - {facet}")

        print("\nSocial Model (by field):")
        for field, values in data['social_model'].items():
            if values:
                print(f"  {field}: {', '.join(values)}")
    else:
        print(f"\n❌ Failed with status {response.status_code}")
        print(response.text)


if __name__ == "__main__":
    print("\n*** Make sure the backend is running first! ***")
    print("    Run: uv run uvicorn backend.main:app --reload\n")

    try:
        test_extract_facets()
        print("\n" + "=" * 60)
        print("✅ All tests passed!")
        print("=" * 60)
    except requests.exceptions.ConnectionError:
        print("❌ Could not connect to backend. Make sure it's running on http://localhost:8000")
    except Exception as e:
        print(f"❌ Test failed: {e}")
        import traceback
        traceback.print_exc()
