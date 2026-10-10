"""
EXERCISE LIBRARY (ATLAS workout template, increment 2a) - the store.

One locked JSON file of exercise how-tos: steps, muscles targeted, common
mistakes. This module has NO model and NO network code. Drafting a missing entry
with Gemini is increment 2b.

RULES
- A new entry is ALWAYS saved as "ai_drafted". Nothing a draft says can make it
  "reviewed"; only mark_reviewed() does that (through an approval).
- Names match EXACTLY after tidying (case, spacing, punctuation, DB/BB/KB spelled
  out) or through an entry's other names. No fuzzy guessing (a wrong match would
  show Joey the wrong how-to). A name that would point at two entries is refused.
- Every write is one locked read-modify-write (Lesson #4). A damaged or wrong-shaped
  file fails loudly and is never overwritten (Lesson #5). Junk already in the file
  is preserved.
"""
import json
import os
import re
import time
import uuid
from datetime import datetime

from shared.file_store import load_json, update_json
from shared.normalizers import require_dict

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_LIBRARY_PATH = os.path.join(_REPO_ROOT, "data", "exercise_library.json")

STATUS_DRAFTED = "ai_drafted"
STATUS_REVIEWED = "reviewed"

MAX_NAME = 100
MAX_STEPS = 15
MAX_STEP = 300
MAX_MUSCLES = 8
MAX_MUSCLE = 60
MAX_MISTAKES = 5
MAX_MISTAKE = 300
MAX_ALIASES = 8
MAX_EQUIPMENT = 5
MAX_ENTRIES = 2000

_ABBREVIATIONS = {
    "db": "dumbbell", "dbs": "dumbbell", "dumbbells": "dumbbell",
    "bb": "barbell", "barbells": "barbell",
    "kb": "kettlebell", "kbs": "kettlebell", "kettlebells": "kettlebell",
    "bw": "bodyweight",
}
# "1. Do this" / "Step 2: Do that" / "- bullet". NOT "2-3 deep breaths" or "2.5 second pause".
_LEADING_MARK_RE = re.compile(r"^(?:step\s*)?\d{1,2}\s*[.):]\s+|^[-*\u2022]\s+", re.IGNORECASE)


def get_library_path() -> str:
    """Read at call time (not import time) so tests and .env changes work."""
    return os.path.abspath(os.getenv("EXERCISE_LIBRARY_PATH") or DEFAULT_LIBRARY_PATH)


# --------------------------------------------------------------
# CLEANING
# --------------------------------------------------------------

def normalize_name(name) -> str:
    """'Incline DB press' -> 'incline dumbbell press'. Non-text gives ''."""
    if not isinstance(name, str):
        return ""
    words = "".join(c if c.isalnum() else " " for c in name[:200].lower()).split()
    return " ".join(_ABBREVIATIONS.get(w, w) for w in words)


def _printable(s: str) -> str:
    return "".join(ch for ch in s if ch.isprintable())


def _one_line(v, limit: int) -> str:
    if not isinstance(v, str):
        return ""
    return _printable(" ".join(v.split()))[:limit].strip()


def _clean_items(v, max_items: int, max_chars: int, split_on: str) -> list:
    """List of short clean strings from a list OR a delimited string. Junk items are skipped."""
    if v is None:
        return []
    if isinstance(v, str):
        v = re.split(split_on, v)
    if not isinstance(v, list):
        return []
    out, seen = [], set()
    for x in v[:max_items * 4]:                       # bounded work on huge lists
        if isinstance(x, dict):
            text = ""
            for key in ("text", "description", "instruction", "name", "step"):
                candidate = x.get(key)
                if isinstance(candidate, str) and candidate.strip():
                    text = candidate
                    break
            x = text
        if not isinstance(x, str):
            continue
        s = _printable(" ".join(x.split()))
        s = _LEADING_MARK_RE.sub("", s).strip()[:max_chars].strip()
        if not s or s.lower() in seen:
            continue
        seen.add(s.lower())
        out.append(s)
        if len(out) >= max_items:
            break
    return out


def normalize_entry(raw) -> dict:
    """
    A draft (from a model or anyone) -> a clean entry, or ValueError.
    Needs a name, at least one step and at least one primary muscle.
    The status is ALWAYS ai_drafted, whatever the draft claims.
    """
    require_dict(raw, "exercise")
    name = _one_line(raw.get("name"), MAX_NAME)
    name_key = normalize_name(name)
    if not name_key:
        raise ValueError("exercise: needs a name")
    steps = _clean_items(raw.get("steps"), MAX_STEPS, MAX_STEP, r"\n+")
    if not steps:
        raise ValueError("exercise: needs at least one step")
    primary = _clean_items(raw.get("primary_muscles"), MAX_MUSCLES, MAX_MUSCLE, r",|;|\n")
    if not primary:
        raise ValueError("exercise: needs at least one primary muscle")
    aliases, seen = [], {name_key}
    for a in _clean_items(raw.get("aliases"), MAX_ALIASES * 2, MAX_NAME, r",|;|\n"):
        key = normalize_name(a)
        if key and key not in seen:
            seen.add(key)
            aliases.append(a)
        if len(aliases) >= MAX_ALIASES:
            break
    return {
        "name": name,
        "aliases": aliases,
        "steps": steps,
        "primary_muscles": primary,
        "secondary_muscles": _clean_items(raw.get("secondary_muscles"), MAX_MUSCLES, MAX_MUSCLE, r",|;|\n"),
        "common_mistakes": _clean_items(raw.get("common_mistakes"), MAX_MISTAKES, MAX_MISTAKE, r"\n+"),
        "equipment": _clean_items(raw.get("equipment"), MAX_EQUIPMENT, MAX_MUSCLE, r",|;|\n"),
        "status": STATUS_DRAFTED,
    }


# --------------------------------------------------------------
# READING (never writes, never creates the file)
# --------------------------------------------------------------

def _entry_names(entry: dict) -> set:
    names = {normalize_name(entry.get("name"))}
    aliases = entry.get("aliases")
    if isinstance(aliases, list):
        names |= {normalize_name(a) for a in aliases}
    names.discard("")
    return names


def _entries(data: dict) -> list:
    return [e for e in data.get("exercises", []) if isinstance(e, dict)]


def load_library() -> dict:
    """The library data. Missing file = empty library. Damaged or wrong shape = RuntimeError."""
    path = get_library_path()
    data = None
    for attempt in (1, 2):                            # a reader can catch a write in progress: one quick retry
        try:
            data = load_json(path, {"exercises": []})
            break
        except json.JSONDecodeError as e:
            if attempt == 2:
                raise RuntimeError(f"exercise library file is damaged ({e.msg}): {path}") from e
            time.sleep(0.05)
    if not isinstance(data, dict):
        raise RuntimeError("exercise library file has the wrong shape (expected an object)")
    if data.get("exercises") is None:
        data["exercises"] = []
    elif not isinstance(data["exercises"], list):
        raise RuntimeError("exercise library file: 'exercises' is not a list")
    return data


def list_entries() -> list:
    return _entries(load_library())


def find_exercise(name):
    """The ONE entry whose name or other name matches, else None. Two matches = ValueError."""
    target = normalize_name(name)
    if not target:
        return None
    matches = [e for e in _entries(load_library()) if target in _entry_names(e)]
    if len(matches) > 1:
        raise ValueError(f"'{str(name)[:60]}' matches more than one library entry - fix the library file")
    return matches[0] if matches else None


def find_conflict(clean):
    """An existing entry that a new entry's name or other names would collide with, else None."""
    entry = normalize_entry(clean)
    names = _entry_names(entry)
    for existing in _entries(load_library()):
        if names & _entry_names(existing):
            return existing
    return None


def _read_items(v) -> list:
    return [s for s in v if isinstance(s, str) and s.strip()] if isinstance(v, list) else []


def format_entry(entry) -> str:
    """The how-to as plain text (what Joey reads before approving, and later on the template)."""
    if not isinstance(entry, dict):
        raise ValueError("exercise entry must be a dict")
    name = _one_line(entry.get("name"), MAX_NAME) or "Unnamed exercise"
    status = "reviewed by you" if entry.get("status") == STATUS_REVIEWED else "AI-drafted, NOT yet reviewed"
    lines = [f"{name} ({status})"]
    primary = _read_items(entry.get("primary_muscles"))[:MAX_MUSCLES]
    secondary = _read_items(entry.get("secondary_muscles"))[:MAX_MUSCLES]
    if primary:
        targets = ", ".join(primary)
        if secondary:
            targets += f" (also: {', '.join(secondary)})"
        lines.append(f"Targets: {targets}")
    equipment = _read_items(entry.get("equipment"))[:MAX_EQUIPMENT]
    if equipment:
        lines.append("Equipment: " + ", ".join(equipment))
    steps = _read_items(entry.get("steps"))[:MAX_STEPS]
    if steps:
        lines.append("Steps:")
        lines += [f"{i}. {s}" for i, s in enumerate(steps, 1)]
    mistakes = _read_items(entry.get("common_mistakes"))[:MAX_MISTAKES]
    if mistakes:
        lines.append("Common mistakes:")
        lines += [f"- {m}" for m in mistakes]
    return "\n".join(lines)


# --------------------------------------------------------------
# WRITING (each one a single locked read-modify-write)
# --------------------------------------------------------------

def _check_shape(data) -> None:
    if not isinstance(data, dict):
        raise RuntimeError("exercise library file has the wrong shape (expected an object)")
    if data.get("exercises") is None:
        data["exercises"] = []
    elif not isinstance(data["exercises"], list):     # fail loudly, never overwrite real data
        raise RuntimeError("exercise library file: 'exercises' is not a list - refusing to overwrite it")


def add_entry(clean) -> tuple:
    """Adds a new AI-drafted entry. Returns (ok, message). Re-cleans the entry (it is re-checked at approval)."""
    entry = normalize_entry(clean)
    names = _entry_names(entry)
    result = {"ok": False, "msg": ""}

    def _modify(data):
        _check_shape(data)
        if len(data["exercises"]) >= MAX_ENTRIES:
            result["msg"] = f"The exercise library is full ({MAX_ENTRIES} entries) - nothing was added."
            return data
        for existing in data["exercises"]:
            if isinstance(existing, dict) and names & _entry_names(existing):
                result["msg"] = (f"'{existing.get('name')}' is already in the library "
                                 f"(it matches '{entry['name']}') - nothing changed.")
                return data
        record = dict(entry)
        record.update(id=str(uuid.uuid4()), created_at=datetime.now().isoformat(), reviewed_at=None)
        data["exercises"].append(record)
        result["ok"] = True
        result["msg"] = f"Exercise added: {entry['name']} (AI-drafted, not yet reviewed)."
        return data

    update_json(get_library_path(), _modify, {"exercises": []})
    return result["ok"], result["msg"]


def mark_reviewed(entry_id) -> tuple:
    """Marks one entry (by id) as reviewed. Returns (ok, message)."""
    if not isinstance(entry_id, str) or not entry_id.strip():
        return False, "That exercise could not be identified - nothing changed."
    result = {"ok": False, "msg": ""}

    def _modify(data):
        _check_shape(data)
        for existing in data["exercises"]:
            if isinstance(existing, dict) and existing.get("id") == entry_id:
                if existing.get("status") == STATUS_REVIEWED:
                    result["msg"] = f"'{existing.get('name')}' is already marked as reviewed - nothing changed."
                    return data
                existing["status"] = STATUS_REVIEWED
                existing["reviewed_at"] = datetime.now().isoformat()
                result["ok"] = True
                result["msg"] = f"Marked as reviewed: {existing.get('name')}."
                return data
        result["msg"] = "That exercise is no longer in the library - nothing changed."
        return data

    update_json(get_library_path(), _modify, {"exercises": []})
    return result["ok"], result["msg"]