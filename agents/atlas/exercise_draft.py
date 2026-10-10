"""
EXERCISE DRAFT (ATLAS workout template, increment 2b-i) - asks Gemini (free cloud)
to DRAFT a how-to for an exercise that is not in the library yet.

- Only the exercise NAME is sent ("Exercise: <name>"). Never paid cloud, never anything personal.
- The answer is untrusted DATA: it goes through exercise_library.normalize_entry, and the
  result is only ever a PROPOSAL that Joey reads and approves. Always saved as AI-drafted.
- Python enforces what the prompt asks for (real models ignore prompts): the entry is saved
  under the name JOEY typed (a renamed answer keeps the model's spelling as another name),
  and a draft with fewer than MIN_STEPS steps or no primary muscle is refused.
- This module never writes the library or any file.
"""
import re

from agents.atlas import exercise_library as library
from shared.model_client import stream_by_tier
from shared.model_json import ExtractionError, parse_model_json

DRAFT_TIER = "free_cloud"
MIN_STEPS = 3
MAX_REQUEST_WORDS = 10


class DraftError(Exception):
    """The drafting model failed, said it does not know the exercise, or gave an unusable draft."""


SYSTEM_PROMPT = """You write exercise how-to entries for a personal fitness app. You are given ONE exercise name.
Return ONLY a single JSON object - no markdown, no commentary - with EXACTLY these keys:
{
  "name": "the exercise name",
  "aliases": ["other common names or spellings, with 'dumbbell' written out instead of 'DB'"],
  "steps": ["4 to 8 short imperative sentences covering setup, the movement, breathing and the finish"],
  "primary_muscles": ["1 to 3 muscles that do most of the work"],
  "secondary_muscles": ["up to 4 helper muscles"],
  "common_mistakes": ["2 to 3 short lines about common form mistakes"],
  "equipment": ["equipment needed, or an empty list for bodyweight"]
}
Rules: plain words; do not number the steps; no step may repeat another; no medical advice or diagnosis; no claims about results, calories or injuries.
Use the most common gym or warm-up meaning of the name. For example, "windmill arms" means big, slow arm circles with the arms moving in opposite directions, like a windmill: one arm swings forward and up while the other swings backward.
If the name is not a real, recognisable exercise, return exactly {"error": "not a recognised exercise"} instead."""


def clean_request_name(name) -> str:
    """The exercise name as it will be sent and saved, or DraftError for something that is not a name."""
    if not isinstance(name, str):
        raise DraftError("give me an exercise name")
    cleaned = "".join(ch for ch in " ".join(name.split()) if ch.isprintable())[:library.MAX_NAME].strip()
    if not library.normalize_name(cleaned):
        raise DraftError("that does not look like an exercise name")
    if len(cleaned.split()) > MAX_REQUEST_WORDS:
        raise DraftError("that is too long to be an exercise name")
    return cleaned


def _parse(text) -> dict:
    """JSON object from the model's text. Tolerates code fences and chatter around one object, nothing else."""
    try:
        return parse_model_json(text)
    except ExtractionError:
        if isinstance(text, str):
            start, end = text.find("{"), text.rfind("}")
            if 0 <= start < end:
                return parse_model_json(text[start:end + 1])
        raise


def _as_list(value) -> list:
    if isinstance(value, list):
        return list(value)
    if isinstance(value, str):
        return [p for p in re.split(r",|;|\n", value) if p.strip()]
    return []


def _enforce(requested: str, data: dict) -> dict:
    aliases = _as_list(data.get("aliases"))
    model_name = data.get("name")
    if isinstance(model_name, str) and model_name.strip():
        aliases.append(model_name)                   # the model's own spelling stays findable
    raw = dict(data)
    raw["name"] = requested                          # ALWAYS the name Joey typed
    raw["aliases"] = aliases
    try:
        clean = library.normalize_entry(raw)
    except ValueError as e:
        raise DraftError(f"the draft was not usable ({e})") from e
    if len(clean["steps"]) < MIN_STEPS:
        raise DraftError(f"the draft was too short (only {len(clean['steps'])} steps)")
    return clean


def draft_exercise(name) -> dict:
    """A clean, AI-drafted library entry for `name`, or DraftError. Never writes anything."""
    requested = clean_request_name(name)
    try:
        text = "".join(stream_by_tier("atlas", DRAFT_TIER, SYSTEM_PROMPT,
                                      [{"role": "user", "content": f"Exercise: {requested}"}]))
    except Exception as e:                           # shown to Joey, never swallowed
        raise DraftError(f"the drafting model call failed ({type(e).__name__}: {e})") from e
    try:
        data = _parse(text)
    except ExtractionError as e:
        raise DraftError("the drafting model did not return a usable answer") from e
    error = data.get("error")
    if isinstance(error, str) and error.strip():
        raise DraftError(f"the model does not recognise '{requested}' as an exercise")
    return _enforce(requested, data)