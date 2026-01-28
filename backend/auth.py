"""Authentication middleware and utilities for Firebase Auth."""

import os
from typing import Optional

from fastapi import Header, HTTPException
from firebase_admin import auth

# Test mode configuration
TEST_TOKEN = "test-token-for-puppeteer"
TEST_USER = {
  "uid": "test-user-puppeteer-001",
  "email": "test@kindredhistories.test",
  "name": "Test User",
  "picture": "https://ui-avatars.com/api/?name=Test+User&background=7c4dff&color=fff",
}


def is_test_auth_enabled() -> bool:
  """Check if test auth mode is enabled via environment variable."""
  return os.getenv("ALLOW_TEST_AUTH", "").lower() == "true"


async def get_current_user(
  authorization: Optional[str] = Header(None),
) -> Optional[dict]:
  """
  Extract and verify Firebase ID token from Authorization header.

  Returns user info dict if authenticated, None if anonymous.
  Raises HTTPException if token is invalid.

  Test Mode:
    Set ALLOW_TEST_AUTH=true environment variable to allow test tokens.
    The test token "test-token-for-puppeteer" will authenticate as a test user.

  Usage:
    @app.get("/api/protected")
    async def protected_endpoint(user = Depends(get_current_user)):
      if not user:
        raise HTTPException(401, "Authentication required")
      user_id = user['uid']
  """
  if not authorization:
    return None  # Anonymous user

  if not authorization.startswith("Bearer "):
    raise HTTPException(401, "Invalid authorization header format")

  token = authorization.replace("Bearer ", "")

  # Allow test token in development/test mode
  if token == TEST_TOKEN and is_test_auth_enabled():
    return TEST_USER

  try:
    decoded_token = auth.verify_id_token(token)
    return decoded_token
  except Exception as e:
    raise HTTPException(401, f"Invalid token: {str(e)}")


def require_auth(user: Optional[dict]) -> dict:
  """Helper to require authentication."""
  if not user:
    raise HTTPException(401, "Authentication required")
  return user
