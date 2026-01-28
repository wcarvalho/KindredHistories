"""
Eval script to measure name generation efficiency and waste.

This script runs the name discovery pipeline on test cases and measures:
- How many raw names Gemini returns before validation
- How many valid names pass validation
- Breakdown of rejection reasons
- Waste rate and API efficiency

Usage:
    uv run python evals/generate_people.py
    uv run python evals/generate_people.py --examples 5 --combos 3
    uv run python evals/generate_people.py --examples 3 --combos 5 --save
"""

import argparse
import json
import os
import sys
from datetime import datetime
from typing import Any, Dict, List

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from backend.agent import (
  StoryGeneratorAgent,
  sample_demographic_combinations,
  search_figures_for_demographic_gemini,
)

# Test cases - same as backend/generate_examples.py
TEST_CASES = {
  "example_0": "I am Mexican. I am a neuroscientist. I crossed the border to the USA when I was 12. I think a lot about how to be a more compassionate person and have to move with compassion I feel the suffering of others a lot and I want to make something out of that something good out of it.",
  "example_1": "i am girl but also boy. I am super duper into privacy and security and coding but I also hate technology and people call me a luddite. I am from atlanta georgia and white passing.",
  "example_2": "I am a past equestrian from san diego who is interested in impact and social good. I've had a confusing life so I studied cognitive psychology and philosophy for undergrad, did a divinity school masters, and am now a PhD student at the Chicago Booth school.",
  "example_3": "Non-binary Asian-American here, really into gaming and anime.",
  "example_4": "Irish-Italian straight guy from Boston who loves sports and history.",
  "example_5": "I am a bolivian from new york that enjoys cognitive science, machine learning, and community-oriented events. I want to help hispanic youth get into STEM fields.",
  "example_6": "Black queer woman from Detroit, passionate about urban farming and food justice. I want to bring fresh produce to food deserts.",
  "example_7": "I'm a deaf Filipino-American who works in UX design. Really into accessibility and inclusive design.",
  "example_8": "Trans man from rural Texas. I love country music and rodeo but also poetry and writing.",
  "example_9": "Jewish lesbian from Miami, work in environmental law. Obsessed with coral reef conservation.",
  "example_10": "I'm mixed Black and Korean, grew up in LA. Big into hip hop production and fashion design.",
  "example_11": "Native American (Navajo) woman interested in preserving indigenous languages through technology.",
  "example_12": "Pakistani Muslim immigrant, software engineer in Seattle. Passionate about open source and developer education.",
  "example_13": "Autistic nonbinary person from Portland. I work in library science and love archiving queer history.",
  "example_14": "Cuban-American gay man from Miami. I'm a chef focused on fusion cuisine and food history.",
  "example_15": "Indian woman from the Bay Area, first-gen college student. Studying bioengineering to work on affordable medical devices.",
  "example_16": "Bisexual Chinese-American woman, grew up in the midwest. Interested in theater and Asian-American representation in media.",
  "example_17": "I'm a Black man from Chicago, work as a public defender. Passionate about criminal justice reform.",
  "example_18": "Salvadoran trans woman from Houston. I work in immigration law and advocate for asylum seekers.",
  "example_19": "White disabled veteran from Ohio. Lost my leg in Iraq, now I do advocacy for disabled athletes.",
  "example_20": "Hmong refugee family background, grew up in Minnesota. I'm into documentary filmmaking about immigrant stories.",
}


def run_eval(
  num_examples: int = 3,
  num_combos: int = 5,
) -> Dict[str, Any]:
  """Run evaluation and collect metrics."""
  print(f"\n{'=' * 60}")
  print(f"RUNNING EVALUATION: {num_examples} examples x {num_combos} combos")
  print(f"{'=' * 60}\n")

  agent = StoryGeneratorAgent()

  results: Dict[str, Any] = {
    "timestamp": datetime.now().isoformat(),
    "config": {"num_examples": num_examples, "num_combos": num_combos},
    "aggregate": {},
    "per_example": [],
    "per_combination": [],
    "sample_rejections": {},
  }

  total_raw = 0
  total_valid = 0
  total_rejections: Dict[str, int] = {
    "too_long": 0,
    "sentence_pattern": 0,
    "wrong_word_count": 0,
    "non_name_pattern": 0,
    "bad_start": 0,
  }
  sample_rejections: Dict[str, List[str]] = {
    "too_long": [],
    "sentence_pattern": [],
    "wrong_word_count": [],
    "non_name_pattern": [],
    "bad_start": [],
  }

  all_unique_names: set = set()
  combos_with_at_least_one_name = 0
  total_combos = 0

  for key, description in list(TEST_CASES.items())[:num_examples]:
    print(f"\n{'=' * 40}")
    print(f"Processing: {key}")
    print(f"{'=' * 40}")

    # 1. Extract demographics
    demographics = agent.extract_demographics_from_text(description)

    # 2. Sample combinations
    samples = sample_demographic_combinations(
      demographics, num_attribution_combinations=num_combos
    )

    example_results: Dict[str, Any] = {
      "key": key,
      "description": description[:100] + "..."
      if len(description) > 100
      else description,
      "combinations": len(samples),
      "raw_names": 0,
      "valid_names": 0,
      "unique_names": [],
    }

    example_unique_names: set = set()

    # 3. Run search for each combination with metrics
    for demo_str, demo_dict in samples:
      total_combos += 1
      metrics = search_figures_for_demographic_gemini(
        demographic_dict=demo_dict,
        goals=demographics.goals(),
        limit=3,
        lm=agent.lm,
        return_metrics=True,
      )

      # Type guard - metrics is dict when return_metrics=True
      if not isinstance(metrics, dict):
        continue

      raw_count = len(metrics["raw_names"])
      valid_count = len(metrics["valid_names"])

      # Aggregate totals
      total_raw += raw_count
      total_valid += valid_count

      if valid_count > 0:
        combos_with_at_least_one_name += 1

      # Aggregate rejections
      for reason, rejected_list in metrics["rejections"].items():
        total_rejections[reason] += len(rejected_list)
        # Collect samples (max 5 per category)
        for text in rejected_list:
          if len(sample_rejections[reason]) < 5:
            sample_rejections[reason].append(text)

      # Store per-combo results
      results["per_combination"].append(
        {
          "example": key,
          "demographic": demo_dict,
          "raw_count": raw_count,
          "valid_count": valid_count,
          "rejections": {k: len(v) for k, v in metrics["rejections"].items()},
          "gemini_time_ms": metrics["gemini_time_ms"],
          "valid_names": metrics["valid_names"],
        }
      )

      example_results["raw_names"] += raw_count
      example_results["valid_names"] += valid_count
      example_unique_names.update(metrics["valid_names"])
      all_unique_names.update(metrics["valid_names"])

    example_results["unique_names"] = list(example_unique_names)
    results["per_example"].append(example_results)

  # Calculate aggregates
  waste_rate = (total_raw - total_valid) / total_raw if total_raw > 0 else 0
  api_efficiency = total_valid / total_combos if total_combos > 0 else 0
  combo_success_rate = (
    combos_with_at_least_one_name / total_combos if total_combos > 0 else 0
  )
  dedup_rate = (
    (total_valid - len(all_unique_names)) / total_valid if total_valid > 0 else 0
  )

  results["aggregate"] = {
    "total_api_calls": total_combos,
    "total_raw_names": total_raw,
    "total_valid_names": total_valid,
    "total_unique_names": len(all_unique_names),
    "waste_rate": waste_rate,
    "api_efficiency": api_efficiency,
    "combo_success_rate": combo_success_rate,
    "dedup_rate": dedup_rate,
    "rejection_breakdown": total_rejections,
  }

  results["sample_rejections"] = sample_rejections

  return results


def print_summary(results: Dict[str, Any]) -> None:
  """Print human-readable summary."""
  agg = results["aggregate"]
  total_raw = agg["total_raw_names"]

  print("\n" + "=" * 60)
  print("EVALUATION SUMMARY")
  print("=" * 60)

  print(f"\nConfiguration:")
  print(f"  Examples: {results['config']['num_examples']}")
  print(f"  Combos per example: {results['config']['num_combos']}")

  print(f"\nAPI Calls & Yield:")
  print(f"  Total API Calls: {agg['total_api_calls']}")
  print(f"  Raw Names Returned: {agg['total_raw_names']}")
  print(f"  Valid Names After Validation: {agg['total_valid_names']}")
  print(f"  Unique Names (deduplicated): {agg['total_unique_names']}")

  print(f"\nEfficiency Metrics:")
  print(f"  Waste Rate: {agg['waste_rate']:.1%}")
  print(f"  API Efficiency: {agg['api_efficiency']:.2f} valid names per call")
  print(f"  Combo Success Rate: {agg['combo_success_rate']:.1%} (combos with >=1 name)")
  print(f"  Dedup Rate: {agg['dedup_rate']:.1%} (duplicate names)")

  print(f"\nRejection Breakdown:")
  for reason, count in agg["rejection_breakdown"].items():
    pct = count / total_raw * 100 if total_raw > 0 else 0
    print(f"  {reason}: {count} ({pct:.1f}%)")

  print(f"\nSample Rejections (for false-negative review):")
  for reason, samples in results["sample_rejections"].items():
    if samples:
      print(f"  {reason}:")
      for sample in samples[:3]:
        display = sample[:60] + "..." if len(sample) > 60 else sample
        print(f'    - "{display}"')

  print(f"\nPer-Example Summary:")
  for ex in results["per_example"]:
    waste = (
      (ex["raw_names"] - ex["valid_names"]) / ex["raw_names"]
      if ex["raw_names"] > 0
      else 0
    )
    print(
      f"  {ex['key']}: {ex['combinations']} combos, {ex['raw_names']} raw, {ex['valid_names']} valid ({waste:.0%} waste)"
    )
    print(
      f"    Unique names: {', '.join(ex['unique_names'][:5])}{'...' if len(ex['unique_names']) > 5 else ''}"
    )

  print("\n" + "=" * 60)


def save_results(results: Dict[str, Any]) -> str:
  """Save results to JSON file."""
  output_dir = os.path.join(os.path.dirname(__file__), "eval_results")
  os.makedirs(output_dir, exist_ok=True)

  timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
  filename = f"generate_{timestamp}.json"
  filepath = os.path.join(output_dir, filename)

  with open(filepath, "w") as f:
    json.dump(results, f, indent=2)

  return filepath


def main():
  parser = argparse.ArgumentParser(description="Evaluate name generation efficiency")
  parser.add_argument(
    "--examples",
    type=int,
    default=3,
    help="Number of test examples to run (default: 3)",
  )
  parser.add_argument(
    "--combos",
    type=int,
    default=5,
    help="Number of demographic combinations per example (default: 5)",
  )
  parser.add_argument(
    "--save",
    action="store_true",
    help="Save results to JSON file",
  )
  args = parser.parse_args()

  results = run_eval(args.examples, args.combos)
  print_summary(results)

  if args.save:
    filepath = save_results(results)
    print(f"\nResults saved to: {filepath}")


if __name__ == "__main__":
  main()
