"""
ATLAS NOTE READER (increment: struggle notes) - the LOCAL model reads the note Joey wrote under an exercise
and says whether he was telling ATLAS "that was a struggle" (too hard, could not continue, had to stop...).

WHY A MODEL: a person reads "too hard" or "I couldn't continue" at a glance; a word list would always miss
something. The model only does the READING. Python guards everything around it (this is the project rule:
where a real model can go wrong, enforce in Python):
- the model sees ONLY the note text: no weights, reps or RPE, so it cannot decide from numbers;
- it can only answer struggled / fine / unclear; anything else, a missing answer, or a conflicting duplicate
  becomes "unclear" and is NEVER counted as a struggle;
- a note that is empty is never sent and never flagged;
- every reading is SHOWN in the proposal ("Struggle noted: Bench press (your note: ...)"), so nothing is
  flagged without Joey seeing it, and nothing is saved until he approves;
- if the model cannot be reached, a visible line says so and NO flags are set (nothing is silently guessed).
The local model is used (never the cloud): notes can mention pain or health.
"""
from typing import Any

from shared.model_client import complete_ollama_json
from shared.model_json import ExtractionError, model_call_failed, parse_model_json

READINGS = ("struggled", "fine", "unclear")
MAX_NOTE_CHARS = 300
MAX_NOTES = 30
SHOW_NOTE_CHARS = 80

PROMPT = """You read short notes a person wrote about ONE exercise at the gym. For each numbered note decide
whether the person is saying the exercise was a STRUGGLE for them.

- "struggled": the note says it was too hard or too heavy, they could not continue or finish, had to stop
  early, failed reps, or their form fell apart.
- "fine": the note says it was fine, easy, good or as planned, OR it says they did NOT struggle
  (for example "no struggle", "wasn't hard"), OR it is about something else (a machine being taken,
  a weight change, how they felt afterwards) without saying it was too hard.
- "unclear": you cannot tell.

Use ONLY the words of the note. Do not guess from anything else.

Answer with ONLY this JSON, one entry per note number:
{"readings": [{"n": 1, "reading": "struggled"}, {"n": 2, "reading": "fine"}]}
"""


def _one_line(text: Any, limit: int) -> str:
    if not isinstance(text, str):
        return ""
    visible = "".join(ch if ch.isprintable() or ch.isspace() else " " for ch in text)      # control characters never reach the model
    return " ".join(visible.split())[:limit]


def read_notes(notes) -> list:
    """
    One reading per note, same order and length: "struggled", "fine", "unclear", or "none" for an empty note.
    Raises ExtractionError when the model call fails or its answer is unusable.
    """
    items = notes if isinstance(notes, list) else []
    cleaned = [_one_line(n, MAX_NOTE_CHARS) for n in items[:MAX_NOTES]]
    asked = [i for i, n in enumerate(cleaned) if n]
    result = ["none" if not n else "unclear" for n in cleaned]
    if not asked:
        return result
    user_text = "\n".join(f"{k}. {cleaned[i]}" for k, i in enumerate(asked, 1))
    try:
        raw = complete_ollama_json(PROMPT, user_text)
    except Exception as e:
        raise model_call_failed(e) from e
    data = parse_model_json(raw)
    answers = data.get("readings")
    if not isinstance(answers, list):
        raise ExtractionError("the local model's answer had no 'readings' list")
    seen: dict = {}
    for item in answers:
        if not isinstance(item, dict):
            continue
        n, reading = item.get("n"), item.get("reading")
        if isinstance(n, bool) or not isinstance(n, int) or not 1 <= n <= len(asked):
            continue
        r = reading.strip().lower() if isinstance(reading, str) else ""
        r = r if r in READINGS else "unclear"
        seen[n] = r if seen.get(n, r) == r else "unclear"      # two different answers for one note: unclear
    for k, i in enumerate(asked, 1):
        result[i] = seen.get(k, "unclear")
    return result


def apply_note_readings(clean) -> list:
    """
    Reads the notes under the MAIN exercises of a normalized workout-block record. Sets ex["struggled"] = True
    on the exercises read as struggled, and puts a proposal-only "note_readings" list on the record (never
    saved). Returns the lines to show in the proposal. NEVER raises for a model problem.
    """
    exercises = clean.get("exercises") if isinstance(clean, dict) else None
    if not isinstance(exercises, list):
        return []
    idx = [i for i, e in enumerate(exercises) if isinstance(e, dict) and _one_line(e.get("notes"), MAX_NOTE_CHARS)]
    if not idx:
        return []
    try:
        readings = read_notes([exercises[i].get("notes") for i in idx])
    except ExtractionError as e:
        return [f"I couldn't read your exercise notes just now ({_one_line(str(e), 120)}), so no struggle flags were set. "
                "Your notes are still saved as you wrote them."]
    lines, shown = [], []
    for i, reading in zip(idx, readings):
        ex = exercises[i]
        note = _one_line(ex.get("notes"), SHOW_NOTE_CHARS)
        name = _one_line(ex.get("name"), 60) or "exercise"
        shown.append({"exercise": name, "note": note, "reading": reading})
        if reading == "struggled":
            ex["struggled"] = True
            lines.append(f"Struggle noted: {name} (your note: \"{note}\").")
        elif reading == "unclear":
            lines.append(f"I couldn't tell whether this was a struggle: {name} (your note: \"{note}\"). Not counted.")
    clean["note_readings"] = shown
    return lines