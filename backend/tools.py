import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List

import requests


def validate_image_url(url: str, timeout: int = 5) -> bool:
  """Check if a URL points to an actual accessible image.

  Args:
      url: The URL to validate
      timeout: Request timeout in seconds

  Returns:
      True if the URL points to a valid image, False otherwise
  """
  try:
    # Make a HEAD request to check content type without downloading the full image
    response = requests.head(url, timeout=timeout, allow_redirects=True)

    # Check if the response is successful
    if response.status_code != 200:
      return False

    # Check if the content-type indicates an image
    content_type = response.headers.get("Content-Type", "").lower()
    valid_image_types = [
      "image/jpeg",
      "image/jpg",
      "image/png",
      "image/gif",
      "image/webp",
      "image/bmp",
    ]

    if any(img_type in content_type for img_type in valid_image_types):
      return True

    return False
  except Exception:
    # If any error occurs (timeout, connection error, etc.), consider it invalid
    return False


def validate_images_parallel(
  candidate_urls: List[str],
  num_valid_needed: int = 1,
  max_workers: int = 5,
  timeout_per_image: int = 5,
) -> List[str]:
  """Validate multiple image URLs in parallel, return first N valid ones.

  Args:
      candidate_urls: List of URLs to validate
      num_valid_needed: Stop after finding this many valid URLs
      max_workers: Number of concurrent validation threads
      timeout_per_image: Timeout for each HEAD request

  Returns:
      List of valid URLs (up to num_valid_needed), preserving original order
  """
  if not candidate_urls:
    return []

  valid_urls = []
  url_to_index = {url: i for i, url in enumerate(candidate_urls)}

  with ThreadPoolExecutor(max_workers=max_workers) as executor:
    future_to_url = {
      executor.submit(validate_image_url, url, timeout_per_image): url
      for url in candidate_urls
    }

    for future in as_completed(future_to_url):
      url = future_to_url[future]
      try:
        if future.result():
          valid_urls.append((url_to_index[url], url))
          if len(valid_urls) >= num_valid_needed:
            for f in future_to_url:
              f.cancel()
            break
      except Exception:
        pass

  valid_urls.sort(key=lambda x: x[0])
  return [url for _, url in valid_urls]


def search_images_google(query: str, num_images: int = 4) -> List[str]:
  """Search for images using Google Custom Search API and validate URLs.

  Args:
      query: Search query string (e.g., "Ai 1999 National Book Award poet")
      num_images: Number of valid images to return (max 10 per API call)

  Returns:
      List of validated image URLs
  """
  api_key = os.getenv("GOOGLE_CSE_API_KEY")
  cse_id = os.getenv("GOOGLE_CSE_ID")

  if not api_key or not cse_id:
    print(
      "  Warning: GOOGLE_CSE_API_KEY or GOOGLE_CSE_ID not configured. Skipping image search."
    )
    return []

  url = "https://www.googleapis.com/customsearch/v1"
  params = {
    "key": api_key,
    "cx": cse_id,
    "q": query,
    "searchType": "image",
    "num": 10,  # Request max to have more candidates for validation
  }

  print(f"  [API CALL] Google Image Search for '{query}'")
  start_time = time.perf_counter()
  try:
    response = requests.get(url, params=params, timeout=10)
    print(
      f"    [TIMING] Google Image Search API: {time.perf_counter() - start_time:.3f}s"
    )
    response.raise_for_status()

    data = response.json()
    items = data.get("items", [])

    candidate_urls = [item.get("link") for item in items if item.get("link")]
    print(f"    Found {len(candidate_urls)} candidate image URLs")

    # Validate URLs in parallel (replaces sequential loop)
    validation_start = time.perf_counter()
    validated_urls = validate_images_parallel(
      candidate_urls,
      num_valid_needed=num_images,
      max_workers=5,
      timeout_per_image=5,
    )
    print(
      f"    [TIMING] Parallel URL validation: {time.perf_counter() - validation_start:.3f}s"
    )
    print(f"    Returning {len(validated_urls)} validated image URLs")
    return validated_urls
  except Exception as e:
    print(f"Error in image search: {e}")
    return []


def google_search_text(query: str, num_results: int = 5) -> str:
  """Perform a Google text search."""
  api_key = os.getenv("GOOGLE_CSE_API_KEY")
  cse_id = os.getenv("GOOGLE_CSE_ID")

  if not api_key or not cse_id:
    return "Search API keys missing."

  url = "https://www.googleapis.com/customsearch/v1"
  params = {"key": api_key, "cx": cse_id, "q": query, "num": min(num_results, 10)}

  try:
    response = requests.get(url, params=params, timeout=10)
    response.raise_for_status()
    data = response.json()

    results = []
    for item in data.get("items", []):
      title = item.get("title", "")
      snippet = item.get("snippet", "")
      results.append(f"Title: {title}\nSnippet: {snippet}\n")

    return "\n".join(results)
  except Exception as e:
    return f"Search failed: {e}"
