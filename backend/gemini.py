"""
Gemini API integration for DSPy and direct API calls.

This module provides:
1. GeminiLM - DSPy Language Model wrapper for Gemini
2. Helper functions for creating Gemini clients
"""

import os
from functools import lru_cache

import dspy
import litellm
from dotenv import load_dotenv
from google import genai
from google.genai import types

gemini_litellm_models = [
  m.removeprefix("gemini/") for m in litellm.model_list if "gemini" in m
]
gemini_litellm_models = list(set(gemini_litellm_models))

load_dotenv()


def extract_text(response):
  if not response or not response.candidates:
    return ""
  texts = []
  for candidate in response.candidates:
    if not candidate.content or not candidate.content.parts:
      continue
    for part in candidate.content.parts:
      if getattr(part, "text", None):
        texts.append(part.text)
  return "\n".join(texts).strip()


class GeminiLM(dspy.LM):
  """DSPy Language Model wrapper for Gemini"""

  def __init__(
    self,
    model_name: str = "gemini-3-flash-preview",
    temperature: float = None,
    client: genai.Client = None,
    **kwargs,
  ):
    super().__init__(model_name, **kwargs)
    self.model_name = model_name
    self.temperature = temperature
    self.client = client or genai.Client(api_key=os.environ.get("GEMINI_API_KEY"))
    self.kwargs = kwargs

  def __call__(self, prompt=None, messages=None, **kwargs):
    """Override DSPy's __call__ to use direct Gemini API instead of litellm"""
    # Handle both prompt and messages formats
    if messages:
      # Convert DSPy messages format to Gemini format
      prompt = (
        messages[-1].get("content", "")
        if isinstance(messages[-1], dict)
        else str(messages[-1])
      )

    # Merge kwargs: call-time kwargs overwrite init-time self.kwargs
    all_kwargs = self.kwargs.copy()
    all_kwargs.update(kwargs)

    # Check if tools are configured
    use_search = False
    if "tools" in all_kwargs:
      for tool in all_kwargs["tools"]:
        if isinstance(tool, dict) and "googleSearch" in tool:
          use_search = True
          break

    # Runtime override
    if "use_search" in all_kwargs:
      use_search = all_kwargs["use_search"]

    # Build the request
    contents = [types.Content(role="user", parts=[types.Part.from_text(text=prompt)])]

    config_kwargs = {}
    if all_kwargs.get("thinking", False):
      config_kwargs["thinking_config"] = types.ThinkingConfig(thinking_budget=-1)

    if use_search:
      config_kwargs["tools"] = [types.Tool(googleSearch=types.GoogleSearch())]

    # Add temperature if specified
    if "temperature" in all_kwargs:
      config_kwargs["temperature"] = all_kwargs["temperature"]
    elif self.temperature is not None:
      config_kwargs["temperature"] = self.temperature

    config = types.GenerateContentConfig(**config_kwargs)

    response = self.client.models.generate_content(
      model=self.model_name, contents=contents, config=config
    )

    output = [extract_text(response)]

    return output


@lru_cache(maxsize=128)
def llm_available_in_litllm(model_name: str):
  try:
    lm = dspy.LM(model_name, api_key=os.environ.get("GEMINI_API_KEY"))
    lm(prompt="hello world")
    return True
  except Exception:
    return False


def make_gemini_lm(model_name: str = None, client: genai.Client = None, **kwargs):
  if model_name is None:
    model_name = os.environ.get("MODEL_NAME")

  if llm_available_in_litllm(model_name) and client is None:
    print(f"Using dspy.LM for {model_name}")
    lm = dspy.LM(f"{model_name}", api_key=os.environ.get("GEMINI_API_KEY"), **kwargs)
  else:
    print(f"Using GeminiLM for {model_name}")
    lm = GeminiLM(model_name=model_name, client=client, **kwargs)

  return lm


if __name__ == "__main__":
  """Test the GeminiLM wrapper with different models."""
  import sys

  # Get model name from command line or use default
  model_name = sys.argv[1] if len(sys.argv) > 1 else "gemini-3-flash-preview"

  print(f"Testing GeminiLM with model: {model_name}")
  print("=" * 60)

  # Test 1: Basic DSPy Predict (no tools)
  print("\nTest 1: Basic DSPy Predict (no tools)")
  print("-" * 60)
  lm = GeminiLM(model_name=model_name)
  dspy.configure(lm=lm)
  pred = dspy.Predict("question -> answer")
  result = pred(question="What is 2 + 2?")
  print("Question: What is 2 + 2?")
  print(f"Answer: {result.answer}")

  # Test 2: DSPy Predict with Google Search tool
  print("\nTest 2: DSPy Predict with Google Search")
  print("-" * 60)
  tools = [{"googleSearch": {}}]
  lm_with_search = GeminiLM(model_name=model_name)
  dspy.configure(lm=lm_with_search)
  pred = dspy.Predict("question -> answer", tools=tools)
  result = pred(question="What is the weather in San Francisco?")
  print("Question: What is the weather in San Francisco?")
  print(f"Answer: {result.answer}")

  # Test 3: DSPy Predict with Google Search tool
  print("\nTest 3: DSPy Predict with Google Search")
  print("-" * 60)
  tools = [{"googleSearch": {}}]
  lm_with_search = GeminiLM(model_name=model_name, tools=tools)
  dspy.configure(lm=lm_with_search)
  pred = dspy.Predict("question -> answer")
  result = pred(question="What is the weather in San Francisco?")
  print("Question: What is the weather in San Francisco?")
  print(f"Answer: {result.answer}")
