import exampleData from './exampleData.json';

export const dummyUserFacets = {
  social_model: {
    "Race/Ethnicity": ["Black", "African American"],
    "Gender": ["Female", "Non-binary"],
    "Profession": ["Scientist", "Artist"],
    "Era": ["19th Century", "Early 20th Century"]
  },
  facets: [
    "Black", 
    "African American", 
    "Female", 
    "Non-binary", 
    "Scientist", 
    "Artist", 
    "19th Century", 
    "Early 20th Century"
  ]
};

export const dummyFigures = [
  {
    name: "Ada Lovelace",
    image_url: "https://upload.wikimedia.org/wikipedia/commons/a/a4/Ada_Lovelace_portrait.jpg",
    marginalization_context: "Augusta Ada King, Countess of Lovelace was an English mathematician and writer, chiefly known for her work on Charles Babbage's proposed mechanical general-purpose computer, the Analytical Engine.",
    similarity_score: 0.92,
    facet_scores: {
      "Female": 0.95,
      "Scientist": 0.98,
      "19th Century": 0.99,
      "Artist": 0.4
    }
  },
  {
    name: "Katherine Johnson",
    image_url: "https://upload.wikimedia.org/wikipedia/commons/6/6d/Katherine_Johnson_1983.jpg",
    marginalization_context: "Katherine Johnson was an American mathematician whose calculations of orbital mechanics as a NASA employee were critical to the success of the first and subsequent U.S. crewed spaceflights.",
    similarity_score: 0.88,
    facet_scores: {
      "Black": 0.95,
      "African American": 0.95,
      "Female": 0.95,
      "Scientist": 0.99,
      "Early 20th Century": 0.2 // She was born in 1918, so technically early 20th
    }
  },
  {
    name: "Example Figure Without Image",
    image_url: null,
    marginalization_context: "This is an example of a figure that does not have an image associated with them, to test the fallback UI rendering.",
    similarity_score: 0.45,
    facet_scores: {
      "Female": 0.1,
      "Non-binary": 0.8,
      "Artist": 0.9,
      "19th Century": 0.5
    }
  }
];

export { exampleData };

