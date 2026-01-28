from typing import Dict, List, Optional

from pydantic import BaseModel


class UserDescription(BaseModel):
  text: str
  facets: Optional[List[str]] = None
  social_model: Optional[Dict[str, List[str]]] = None


class SocialModel(BaseModel):
  race: Optional[List[str]] = None
  ethnicity: Optional[List[str]] = None
  cultural_background: Optional[List[str]] = None
  location: Optional[List[str]] = None
  gender: Optional[List[str]] = None
  sexuality: Optional[List[str]] = None
  interests: Optional[List[str]] = None
  aspirations: Optional[List[str]] = None

  def as_list(self, include_goals: bool = False) -> List[str]:
    """Return a flattened, deduplicated list of all demographic values.

    Deduplication is case-insensitive but preserves original case of first occurrence.
    """
    seen = set()
    result = []
    for field_value in [
      self.race,
      self.ethnicity,
      self.cultural_background,
      self.gender,
      self.sexuality,
      self.interests if include_goals else None,
      self.aspirations if include_goals else None,
    ]:
      if field_value:
        for val in field_value:
          if val.lower() not in seen:
            seen.add(val.lower())
            result.append(val)
    return result

  def as_str(self) -> str:
    """
    Return a line-by-line string representation of the social model.

    Format:
      field_name: value1, value2, ...

    Example:
      ethnicity: Hispanic
      cultural_background: Bolivian, New Yorker
      location: Brooklyn
      interests: cognitive science, machine learning
    """
    lines = []

    # Order matters for readability
    field_order = [
      ("race", self.race),
      ("ethnicity", self.ethnicity),
      ("cultural_background", self.cultural_background),
      ("gender", self.gender),
      ("sexuality", self.sexuality),
      ("interests", self.interests),
      ("aspirations", self.aspirations),
    ]

    for field_name, field_value in field_order:
      if field_value:
        # values_str = ", ".join(field_value)
        if isinstance(field_value, list):
          lines.append(f"{field_name} ({len(field_value)}): {str(field_value)}")
        else:
          lines.append(f"{field_name}: {str(field_value)}")

    return "\n".join(lines)

  def get_aspiration_summary(self) -> str:
    """Return a summary string of the user's aspirations."""
    if self.aspirations:
      return ", ".join(self.aspirations)
    return ""

  def goals(self) -> List[str]:
    """Return a flattened list of goals."""
    goals = []
    for field_value in [self.interests, self.aspirations]:
      if field_value:
        goals.extend(field_value)
    return list(set(goals))


class Attributes(SocialModel):
  """Backwards compatibility alias if needed, or just remove and fix usage."""

  pass


class HistoricalFigure(BaseModel):
  name: str
  marginalization_context: str
  challenges_faced: Optional[str] = None
  how_they_overcame: Optional[str] = None
  achievement: str
  image_url: Optional[str] = None
  tags: SocialModel
  search_queries_used: List[str] = []
  initial: bool = (
    False  # True for pre-populated figures, False for user-searched figures
  )


class Combination(BaseModel):
  attributes: SocialModel
  search_query: str
