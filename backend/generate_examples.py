""" """

import json
import os
import sys

# Add project root to path so we can import from backend
sys.path.append(os.getcwd())


from backend.agent import StoryGeneratorAgent, ensure_list
from backend.database import query_by_facets_semantic
from backend.models import SocialModel

EXAMPLES = {
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

OUTPUT_FILE = "frontend/src/exampleData.json"


def main():
  print("Initializing Agent...")
  agent = StoryGeneratorAgent()

  output_data = {}

  for key, description in EXAMPLES.items():
    print(f"\nProcessing {key}...")

    # 1. Extract Facets
    print("  Extracting facets...")
    pred = agent.extract_demographics(user_input=description)

    social_model = SocialModel(
      race=ensure_list(pred.race),
      ethnicity=ensure_list(pred.ethnicity),
      cultural_background=ensure_list(pred.cultural_background),
      gender=ensure_list(pred.gender),
      sexuality=ensure_list(pred.sexuality),
      interests=ensure_list(pred.interests),
      aspirations=ensure_list(pred.aspirations),
    )

    user_facets = {
      "facets": social_model.as_list(include_goals=True),
      "social_model": {
        "race": social_model.race or [],
        "ethnicity": social_model.ethnicity or [],
        "cultural_background": social_model.cultural_background or [],
        "gender": social_model.gender or [],
        "sexuality": social_model.sexuality or [],
        "interests": social_model.interests or [],
        "aspirations": social_model.aspirations or [],
      },
    }

    # 2. Find Figures (Populate DB)
    print("  Finding figures...")
    # using num_attribution_combinations=1 for speed in this test script,
    # but maybe 2 to get decent results? The user said "script runs an example", implies doing the work.
    # I'll stick to 1 or 2.
    for name, search_query in agent.process_user_request(
      description, num_attribution_combinations=1
    ):
      agent.process_person(name, search_query=search_query)

    # 3. Query Results (Simulate Results View)
    print("  Querying results...")
    facets_list = user_facets["facets"]

    # Helper to format results exactly like the API
    results_with_scores = query_by_facets_semantic(
      facets_list, limit=20, min_similarity=0.3
    )

    figures = []
    for figure_data, score, facet_scores in results_with_scores:
      figure_with_score = {
        **figure_data,
        "similarity_score": round(score, 3),
        "facet_scores": {k: round(v, 3) for k, v in facet_scores.items()},
      }
      figures.append(figure_with_score)

    output_data[key] = {
      "description": description,
      "userFacets": user_facets,
      "figures": figures,
    }

  print(f"\nWriting to {OUTPUT_FILE}...")
  with open(OUTPUT_FILE, "w") as f:
    json.dump(output_data, f, indent=2)

  print("Done!")


if __name__ == "__main__":
  main()
