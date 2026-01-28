#!/usr/bin/env python3
"""Generate figures for the Kindred Histories writeup.

This script generates:
1. Probability distribution plot for combination sampling
2. Screenshots of the application (requires running backend + frontend)
"""

import subprocess
import sys
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np


def generate_probability_plot(output_path: Path) -> None:
  """Generate the probability distribution plot for combination sampling."""
  # Parameters matching backend/agent.py
  lambda_decay = 0.7
  k_min = 2
  k_max = 7

  k_values = np.arange(k_min, k_max + 1)
  # P(k) ∝ exp(-λ * (k - k_min))
  raw_probs = np.exp(-lambda_decay * (k_values - k_min))
  probabilities = raw_probs / raw_probs.sum()

  fig, ax = plt.subplots(figsize=(4, 2.5))

  bars = ax.bar(k_values, probabilities, color="#7c4dff", edgecolor="white", width=0.7)

  ax.set_xlabel("Number of attributes (k)", fontsize=10)
  ax.set_ylabel("Probability P(k)", fontsize=10)
  ax.set_xticks(k_values)
  ax.set_ylim(0, max(probabilities) * 1.15)

  # Add probability values on top of bars
  for bar, prob in zip(bars, probabilities):
    ax.text(
      bar.get_x() + bar.get_width() / 2,
      bar.get_height() + 0.01,
      f"{prob:.2f}",
      ha="center",
      va="bottom",
      fontsize=8,
    )

  ax.spines["top"].set_visible(False)
  ax.spines["right"].set_visible(False)

  plt.tight_layout()
  plt.savefig(output_path, dpi=300, bbox_inches="tight")
  plt.close()
  print(f"Generated: {output_path}")


def generate_screenshots(output_dir: Path) -> None:
  """Generate application screenshots using Playwright.

  Requires:
  - Backend running: uv run uvicorn backend.main:app --reload
  - Frontend running: cd frontend && npm run dev
  - Playwright installed: uv add playwright && uv run playwright install chromium
  """
  try:
    from playwright.sync_api import sync_playwright
  except ImportError:
    print(
      "Playwright not installed. Run: uv add playwright && uv run playwright install chromium"
    )
    return

  frontend_url = "http://localhost:5173"

  with sync_playwright() as p:
    browser = p.chromium.launch()
    # MacBook resolution (1440x900) with 2x scale for retina quality
    page = browser.new_page(
      viewport={"width": 1440, "height": 900},
      device_scale_factor=2,
    )

    try:
      # Screenshot 1: Initial chat interface
      page.goto(frontend_url, timeout=10000)
      page.wait_for_load_state("networkidle", timeout=10000)

      # Wait a moment for any animations to settle
      page.wait_for_timeout(500)

      screenshot_path = output_dir / "screenshot_chat.png"
      page.screenshot(path=str(screenshot_path))
      print(f"Generated: {screenshot_path}")

      # Screenshot 2: Enter sample text to show the interface with input
      sample_text = "I'm a queer Latina interested in neuroscience from Georgia"
      textarea = page.locator("textarea").first
      if textarea.is_visible():
        textarea.fill(sample_text)
        page.wait_for_timeout(300)

        screenshot_path = output_dir / "screenshot_chat_filled.png"
        page.screenshot(path=str(screenshot_path))
        print(f"Generated: {screenshot_path}")

      # Screenshot 3: Submit the form and wait for actual results
      submit_button = page.locator("button:has-text('Begin Journey')")
      if submit_button.is_visible():
        submit_button.click()

        # Wait for results view to appear (up to 120 seconds for discovery)
        print("Waiting for results view (this may take up to 120 seconds)...")
        try:
          # Wait for the results view - look for "Your search:" text which only appears on results page
          page.wait_for_selector("text=Your search:", timeout=120000)

          # Then wait for actual result rows to load
          page.wait_for_selector(".fade-in", timeout=120000)
          page.wait_for_timeout(2000)  # Let animations settle

          screenshot_path = output_dir / "screenshot_results.png"
          page.screenshot(path=str(screenshot_path))
          print(f"Generated: {screenshot_path}")
        except Exception as e:
          print(f"Timeout waiting for results: {e}")
          # Take a screenshot anyway to see current state
          screenshot_path = output_dir / "screenshot_results_partial.png"
          page.screenshot(path=str(screenshot_path))
          print(f"Generated partial results: {screenshot_path}")

    except Exception as e:
      print(f"Could not capture screenshots: {e}")
      print("Make sure frontend is running: cd frontend && npm run dev")

    browser.close()


def main():
  script_dir = Path(__file__).parent
  figures_dir = script_dir / "figures"
  figures_dir.mkdir(exist_ok=True)

  print("Generating probability distribution plot...")
  generate_probability_plot(figures_dir / "combination_probability.pdf")

  if "--screenshots" in sys.argv:
    print("\nGenerating screenshots...")
    generate_screenshots(figures_dir)
  else:
    print("\nSkipping screenshots. Run with --screenshots to capture them.")
    print("(Requires backend + frontend running)")


if __name__ == "__main__":
  main()
