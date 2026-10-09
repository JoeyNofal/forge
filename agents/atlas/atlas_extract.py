"""
ATLAS EXTRACT — turns what Joey SAYS into log PROPOSALS (increment (b), Part 3).

Flow, for one message Joey sent:
  1. detect_report_kinds(): cheap whole-word pre-filter — does this even look
     like a workout report / injury report / "it's better now"? (Lesson #6)
  2. For each kind, ONE call to the LOCAL model (shared/model_client's
     complete_ollama_json) with a prompt that spells out the exact JSON shape
     (Lesson #5). The model sees ONLY Joey's own message — never ATLAS's
     replies, history or memory — so a wrong ATLAS statement can never be
     "extracted" back into data (Lesson #3).
  3. The answer is parsed and handed to atlas_actions.propose_*, which
     re-validates it and queues a proposal. NOTHING is saved here: Joey
     approves or denies each proposal separately, through atlas_actions.

Every failure (Ollama down, timeout, junk JSON, data the validators reject) is
turned into ONE plain sentence for Joey. Nothing is guessed, nothing is
silently dropped (Lesson #12).
"""
import re
from datetime import datetime
from typing import Optional

from shared.keyword_gate import contains_keyword
from shared.agent_topics import (
    ATLAS_WORKOUT_REPORT_PHRASES, ATLAS_ADVICE_SIGNALS, ATLAS_BODY_PARTS,
    ATLAS_INJURY_REPORT_WORDS, ATLAS_INJURY_RECOVERY_PHRASES,
)
from shared.model_client import complete_ollama_json
from agents.atlas import atlas_actions
from agents.atlas import atlas_logging as log
from shared.model_json import ExtractionError, model_call_failed, parse_model_json

MAX_INPUT_CHARS = 4000       # only the first part of a huge message goes to the model
MAX_PROPOSALS = 3            # per message

KIND_WORKOUT = "workout"
KIND_INJURY = "injury"
KIND_INJURY_UPDATE = "injury_update"
_LABELS = {KIND_WORKOUT: "workout", KIND_INJURY: "injury", KIND_INJURY_UPDATE: "injury update"}


# ExtractionError, model_call_failed and parse_model_json live in shared/model_json.py (imported above).


# ─────────────────────────────────────────────
# SECTION 1 — DETECTION (does it even look like a report?)
# ─────────────────────────────────────────────

def detect_report_kinds(message: str) -> list:
    """
    Which extractions to TRY for this message. Empty list = nothing to log.
    Raises TypeError for a non-string (fails loudly rather than guessing).
    """
    if not isinstance(message, str):
        raise TypeError(f"message must be a string, got {type(message).__name__}")
    text = message.replace("\u2019", "'").strip()      # phone keyboards type curly apostrophes
    if not text:
        return []
    kinds = []
    if contains_keyword(text, ATLAS_WORKOUT_REPORT_PHRASES) and not contains_keyword(text, ATLAS_ADVICE_SIGNALS):
        kinds.append(KIND_WORKOUT)
    if contains_keyword(text, ATLAS_BODY_PARTS):
        if contains_keyword(text, ATLAS_INJURY_RECOVERY_PHRASES):
            kinds.append(KIND_INJURY_UPDATE)          # "better" wins over "hurts": it's an update
        elif contains_keyword(text, ATLAS_INJURY_REPORT_WORDS):
            kinds.append(KIND_INJURY)
    return kinds


# ─────────────────────────────────────────────
# SECTION 2 — PROMPTS (exact output shapes, Lesson #5)
# ─────────────────────────────────────────────

_COMMON_RULES = """You extract data from ONE message Joey wrote. Reply with ONLY a JSON object — no other text.
Today's date is {{TODAY}}.
Rules:
- Use ONLY what the message explicitly says. Never invent a number, exercise, body part or date.
- If a number is not stated, use null. If a date is not stated, use an empty string. If Joey says "yesterday" or "Monday", work out the date from today's date.
- If the message is a question, a plan, a request for advice, a hypothetical, or something that did not really happen to Joey, reply exactly {"kind": "none"}.
"""

WORKOUT_PROMPT = _COMMON_RULES + """
Task: Joey may be reporting a workout he ALREADY did.

Gym workout — reply in exactly this shape:
{"kind": "gym", "date": "", "duration_minutes": null, "difficulty": null,
 "exercises": [{"name": "bench press", "sets": 3, "reps": 8, "weight": 135, "weight_unit": "lbs", "notes": ""}],
 "form_notes": "", "weaknesses": "", "coach_notes": ""}
- "exercises" MUST be a list of OBJECTS exactly like the example. Never a list of plain strings.
- weight is the number EXACTLY as Joey said it. NEVER convert it and NEVER do any arithmetic. weight_unit is "lbs" or "kg" ONLY if Joey wrote the unit (lb, lbs, pounds, kg, kilos). If he gave no unit, weight_unit is an empty string "". If no weight is stated, weight is null and weight_unit is "".
- difficulty is 1 to 10, only if Joey said how hard it was.
- form_notes, weaknesses and coach_notes stay EMPTY unless Joey explicitly wrote form feedback, a weakness, or a note. Soreness or pain is NOT a weakness; ignore it here (it is logged separately).

Swim workout — reply in exactly this shape:
{"kind": "swim", "date": "", "total_distance": 2000, "distance_unit": "yards", "duration_minutes": 45, "strokes": ["freestyle"],
 "sets": ["4x100 kick"], "difficulty": null, "form_notes": "", "weaknesses": "", "coach_notes": ""}
- total_distance is the number EXACTLY as Joey said it. NEVER convert it. distance_unit is "yards" or "meters" ONLY if Joey wrote the unit (yards, yds, meters, m). If he gave no unit, distance_unit is an empty string "". If no distance is stated, total_distance is null.

Not a workout report: {"kind": "none"}
"""

INJURY_PROMPT = _COMMON_RULES + """
Task: Joey may be reporting an injury or pain he HAS RIGHT NOW.

Reply in exactly this shape:
{"kind": "injury", "body_part": "left shoulder", "description": "sharp pain when reaching overhead",
 "severity": "", "notes": "", "date": ""}
- severity is "mild", "moderate" or "severe" ONLY if his words say so; otherwise an empty string.
- description uses Joey's own words, kept short.
- If he is NOT currently hurt (it's better, it's a question, it's about the past, it's hypothetical): {"kind": "none"}
"""

UPDATE_PROMPT = _COMMON_RULES + """
Task: Joey may be saying that an injury he already reported is getting better or is gone.

Reply in exactly this shape:
{"kind": "injury_update", "body_part": "shoulder", "new_status": "recovering", "notes": ""}
- body_part: the body part in Joey's own words, as short as he said it (add left/right only if he did).
- new_status: "recovering" if it is improving or better but not gone; "resolved" if it is gone, healed, or fully recovered.
- If he is not saying an injury got better: {"kind": "none"}
"""

_PROMPTS = {KIND_WORKOUT: WORKOUT_PROMPT, KIND_INJURY: INJURY_PROMPT, KIND_INJURY_UPDATE: UPDATE_PROMPT}


# ─────────────────────────────────────────────
# SECTION 3 — CALLING THE LOCAL MODEL
# ─────────────────────────────────────────────

# (parsing the model's JSON answer: shared/model_json.py)


# A unit the model reports is only trusted if Joey's own words contain a word of that
# unit family. Letter look-arounds (not \b) so "50kg" and "135lbs" still count; the
# single letter "m" only counts right after a digit, so "I'm" and "30 minutes" never do.
_UNIT_WORDS = {
    "lbs": re.compile(r"(?<![a-z])(?:lbs?|pounds?)(?![a-z])", re.I),
    "kg": re.compile(r"(?<![a-z])(?:kgs?|kilos?|kilograms?)(?![a-z])", re.I),
    "yards": re.compile(r"(?<![a-z])(?:yds?|yards?)(?![a-z])", re.I),
    "meters": re.compile(r"(?:(?<=\d)\s?m|(?<![a-z])(?:meters?|metres?))(?![a-z])", re.I),
}


def _enforce_stated_units(data: dict, message: str) -> None:
    """
    The real local model copied "lbs" from the example shape (and could just as well
    guess "kg"). Python enforces the rule instead: a reported unit survives only if
    Joey actually wrote a word of that family; otherwise it is blanked, so the number
    is treated as unitless and flagged "(unit assumed)". Mutates data; never raises
    on junk shapes.
    """
    kind = data.get("kind")
    if kind == "gym":
        items, key = data.get("exercises"), "weight_unit"
    elif kind == "swim":
        items, key = [data], "distance_unit"
    else:
        return
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        family = log.unit_family(item.get(key))
        if family and not _UNIT_WORDS[family].search(message):
            item[key] = ""


def _extract(kind: str, message: str, today: str) -> dict:
    prompt = _PROMPTS[kind].replace("{{TODAY}}", today)
    try:
        raw_text = complete_ollama_json(prompt, message[:MAX_INPUT_CHARS])
    except Exception as e:       # Ollama down, timeout, bad response — surfaced, never swallowed
        raise model_call_failed(e) from e
    return parse_model_json(raw_text)


# ─────────────────────────────────────────────
# SECTION 4 — EXTRACT -> PROPOSE
# ─────────────────────────────────────────────

def _handle(kind: str, message: str, today: str) -> Optional[str]:
    """One extraction. Returns a note for Joey, or None when there's nothing to log."""
    data = _extract(kind, message, today)
    found = data.get("kind")
    if found == "none":
        return None
    _enforce_stated_units(data, message)
    if kind == KIND_WORKOUT:
        if found == "gym":
            return atlas_actions.propose_gym(data)[1]
        if found == "swim":
            return atlas_actions.propose_swim(data)[1]
    elif kind == KIND_INJURY and found == "injury":
        return atlas_actions.propose_injury(data)[1]
    elif kind == KIND_INJURY_UPDATE and found == "injury_update":
        return atlas_actions.propose_injury_update(data)[1]   # (None, reason) -> the reason is the note
    raise ExtractionError(f"unexpected answer type {found!r}")


def extract_and_propose(message: str, today: Optional[str] = None) -> list:
    """
    The one function chat.py calls. Returns a list of plain-English notes for
    Joey (proposals, or honest "couldn't" sentences) — [] when the message
    isn't a report. Never saves anything.
    """
    kinds = detect_report_kinds(message)
    if not kinds:
        return []
    today = today or datetime.now().strftime("%Y-%m-%d")
    notes = []
    for kind in kinds[:MAX_PROPOSALS]:
        try:
            note = _handle(kind, message, today)
        except (ExtractionError, ValueError, RuntimeError, OSError) as e:
            note = f"I couldn't turn that into a {_LABELS[kind]} entry: {e}. Nothing was proposed."
        if note:
            notes.append(note)
    return notes