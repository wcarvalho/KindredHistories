"""Asyncio-based request coalescing for concurrent identical requests.

When multiple concurrent requests arrive for the same operation (e.g., extracting
facets for identical text), this module ensures the work is only done once and
the result is shared among all waiters.
"""

import asyncio
import hashlib
from typing import Any, Awaitable, Callable, Dict

# Store pending requests: key -> Future
_pending_requests: Dict[str, asyncio.Future] = {}
_lock = asyncio.Lock()


def _normalize_key(text: str) -> str:
  """Create a normalized key for coalescing."""
  normalized = text.strip().lower()
  return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


async def coalesced_request(
  key_text: str, async_work_fn: Callable[[], Awaitable[Any]]
) -> Any:
  """Execute work once for concurrent identical requests.

  If another request with the same key_text is already in progress,
  wait for its result instead of duplicating work.

  Args:
      key_text: Text to use for coalescing (e.g., user description)
      async_work_fn: Async function that performs the actual work

  Returns:
      The result from async_work_fn (either computed or shared)
  """
  key = _normalize_key(key_text)

  async with _lock:
    # Check if there's already a pending request for this key
    if key in _pending_requests:
      print(f"[COALESCE] Joining existing request for: {key_text[:50]}...")
      future = _pending_requests[key]
    else:
      # Create a new future and register it
      future = asyncio.get_event_loop().create_future()
      _pending_requests[key] = future
      print(f"[COALESCE] New request for: {key_text[:50]}...")

      # Start the work in a task (outside the lock)
      asyncio.create_task(_do_work_and_resolve(key, async_work_fn, future))

  # Wait for the result (this happens outside the lock)
  try:
    return await future
  except Exception as e:
    # If the work failed, propagate the exception
    raise e


async def _do_work_and_resolve(
  key: str, async_work_fn: Callable[[], Awaitable[Any]], future: asyncio.Future
) -> None:
  """Execute the work and resolve the future with the result."""
  try:
    result = await async_work_fn()
    future.set_result(result)
    print(f"[COALESCE] Completed request for key: {key[:16]}...")
  except Exception as e:
    future.set_exception(e)
    print(f"[COALESCE] Failed request for key: {key[:16]}... Error: {e}")
  finally:
    # Clean up the pending request
    async with _lock:
      if key in _pending_requests:
        del _pending_requests[key]


def get_pending_count() -> int:
  """Get the number of pending coalesced requests."""
  return len(_pending_requests)
