import argparse

import backend.database  # Trigger credential setup
from backend.agent import (
  StoryGeneratorAgent,
  ensure_list,
  sample_demographic_combinations,
  search_figures_for_demographic_gemini,
)
from backend.models import SocialModel


# Mock/Debug helper
def debug_attributes():
  print("--- Testing Attribute Inference ---")
  agent = StoryGeneratorAgent()
  desc = "I am a Mexican neuroscientist who wants to use compassion to help others."
  # New method name involves calling the ChainOfThought module directly or wrapping it
  # process_user_request does extraction + combination + search.
  # To test just extraction:
  pred = agent.extract_demographics(user_input=desc)
  print(pred)

  # Check if we can form SocialModel
  demographics = SocialModel(
    race=ensure_list(pred.race),
    ethnicity=ensure_list(pred.ethnicity),
    cultural_background=ensure_list(pred.cultural_background),
    gender=ensure_list(pred.gender),
    sexuality=ensure_list(pred.sexuality),
    interests=ensure_list(pred.interests),
    aspirations=ensure_list(pred.aspirations),
  )
  print(demographics.as_str())
  return demographics


def debug_combinations(demographics=None):
  print("\n--- Testing Combination Generation ---")
  if not demographics:
    demographics = SocialModel(
      race=["Latino", "Hispanic"],
      ethnicity=["Mexican"],
      interests=["Neuroscience", "Compassion"],
      aspirations=["Help others"],
    )

  samples = sample_demographic_combinations(demographics)
  for s, d in samples:
    print(f"Combo: {s}")
  return samples


def debug_find_people(combo_data=None, demographics=None):
  print("\n--- Testing Find People ---")
  agent = StoryGeneratorAgent()

  if not demographics:
    demographics = SocialModel(ethnicity=["Mexican"], interests=["Neuroscience"])

  combo_str = "Mexican, Neuroscientist"
  if combo_data:
    combo_str, _ = combo_data

  print(f"Searching for: {combo_str}")

  figures = search_figures_for_demographic_gemini(
    demographics=demographics,
    demographic_str=combo_str,
    limit=3,
    debug=True,
    lm=agent.lm,
  )

  names = [f.name for f in figures]
  print("Found name(s):", names)
  return names


def debug_modeller_judge(name="Santiago Ramón y Cajal"):
  print(f"\n--- Testing Modeller/Judge Loop for {name} ---")
  agent = StoryGeneratorAgent()
  agent.process_person(name)


def debug_process_person():
  print("--- Testing Process Person (Modeller/Judge Loop) ---")
  agent = StoryGeneratorAgent()
  # Test with a specific figure
  target_name = "Bayard Rustin"

  # Clean up before test to ensure we run
  doc_id = target_name.replace("/", "_").replace(".", "_")
  if backend.database.db:
    backend.database.db.collection("historical_figures").document(doc_id).delete()
    print(f"Cleared existing entry for {target_name}")

  print(f"Processing: {target_name}")
  agent.process_person(target_name)
  print("Check Firestore for results (e.g. valid facets).")


if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument(
    "--step", choices=["attr", "combo", "find", "process_person"], default="attr"
  )
  args = parser.parse_args()

  if args.step == "attr":
    debug_attributes()
  elif args.step == "combo":
    debug_combinations()
  elif args.step == "find":
    debug_find_people()
  elif args.step == "process_person":
    debug_process_person()
  elif (
    args.step == "process"
  ):  # This step is no longer in choices, but kept for backward compatibility if needed
    debug_modeller_judge(args.name)
  elif (
    args.step == "all"
  ):  # This step is no longer in choices, but kept for backward compatibility if needed
    attrs = debug_attributes()
    combos = debug_combinations(attrs)
    if combos:
      names = debug_find_people(combos[0], attrs)
      if names:
        debug_modeller_judge(names[0])
