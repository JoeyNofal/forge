"""
ATLAS LOGGING — the ONLY place ATLAS writes workouts and injuries
(increment (b), Part 1). atlas_tools.py stays read-only.

Two jobs:
1. NORMALIZE: turn whatever a model extracted (untrusted, possibly
   malformed JSON) into a clean, exactly-shaped record, or raise a clear
   ValueError. (Lesson #5: never trust the shape.) Nothing is invented:
   a swim with no distance AND no duration is rejected, not guessed.
2. WRITE: add the clean record to the fitness file under one lock for the
   whole read-modify-write (Lesson #4), via shared/file_store.update_json.

Nothing in here talks to a model or to the approval queue — those are
separate, separately-tested parts. The saved shapes match what the old
ATLAS wrote, so the read-only readers and the Training tracker keep working.
"""
import re
import uuid
from datetime import datetime

from shared.file_store import update_json
from shared.keyword_gate import contains_keyword
from agents.atlas.atlas_tools import (
    get_data_path, initialize_fitness_data, _starting_structure,
)

MAX_TEXT = 1000
MAX_LIST = 30
VALID_SEVERITIES = ("mild", "moderate", "severe")
VALID_STATUSES = ("active", "recovering", "resolved")
OPEN_STATUSES = ("active", "recovering")   # an injury that can still be updated


# ─────────────────────────────────────────────
# SECTION 1 — NORMALIZERS (untrusted in, clean out, or ValueError)
# ─────────────────────────────────────────────

def _num(v, low, high, what):
    """Number in [low, high]; None/''/non-numeric -> 0; out of range -> ValueError."""
    if v is None or v == "" or isinstance(v, bool):
        return 0
    try:
        n = float(v)
    except (TypeError, ValueError):
        return 0
    if n != n or n < low or n > high:   # n != n catches NaN
        raise ValueError(f"{what} out of range: {v!r}")
    return int(n) if n == int(n) else n


def _text(v) -> str:
    if v is None:
        return ""
    if isinstance(v, list):
        v = ", ".join(str(x) for x in v if x not in (None, ""))
    return str(v).strip()[:MAX_TEXT]


def _str_list(v) -> list:
    """List of short strings from a list OR a comma-separated string."""
    if v is None or v == "":
        return []
    if isinstance(v, str):
        v = v.split(",")
    if not isinstance(v, list):
        return []
    out = []
    for x in v:
        if isinstance(x, dict):
            x = x.get("description") or x.get("name") or ""
        s = str(x).strip()
        if s:
            out.append(s[:200])
    return out[:MAX_LIST]


def _difficulty(v) -> int:
    n = _num(v, -10**6, 10**6, "difficulty") or 5
    return max(1, min(10, int(round(n))))


def _date(v) -> str:
    """A real, non-future YYYY-MM-DD, else today."""
    today = datetime.now().strftime("%Y-%m-%d")
    try:
        d = datetime.strptime(str(v).strip()[:10], "%Y-%m-%d").strftime("%Y-%m-%d")
    except (TypeError, ValueError):
        return today
    return d if d <= today else today


def _require_dict(raw, kind):
    if not isinstance(raw, dict):
        raise ValueError(f"{kind}: expected an object, got {type(raw).__name__}")


def normalize_swim(raw) -> dict:
    _require_dict(raw, "swim")
    yards = _num(raw.get("total_distance_yards"), 0, 100000, "distance")
    minutes = _num(raw.get("duration_minutes"), 0, 1440, "duration")
    if yards <= 0 and minutes <= 0:
        raise ValueError("swim: no distance and no duration given — nothing to log")
    return {
        "type": "swim",
        "date": _date(raw.get("date")),
        "total_distance_yards": yards,
        "duration_minutes": minutes,
        "strokes": [s.lower() for s in _str_list(raw.get("strokes"))],
        "sets": _str_list(raw.get("sets")),
        "difficulty_1_to_10": _difficulty(raw.get("difficulty")),
        "form_notes": _text(raw.get("form_notes")),
        "weaknesses": _text(raw.get("weaknesses")),
        "coach_notes": _text(raw.get("coach_notes")),
    }


def _normalize_exercise(e):
    if isinstance(e, str):          # the old bug: models return plain strings
        e = {"name": e}
    if not isinstance(e, dict):
        return None
    name = _text(e.get("name"))[:100]
    if not name:
        return None
    def opt(key, high):             # unknown stays None, never a made-up 0
        v = e.get(key)
        if v is None or v == "" or isinstance(v, bool):
            return None
        try:
            n = float(v)
        except (TypeError, ValueError):
            return None
        if n != n or n < 0 or n > high:
            return None
        return int(n) if n == int(n) else n
    return {
        "name": name,
        "sets": opt("sets", 1000),
        "reps": opt("reps", 10000),
        "weight_lbs": opt("weight_lbs", 5000),
        "notes": _text(e.get("notes"))[:200],
    }


def normalize_gym(raw) -> dict:
    _require_dict(raw, "gym")
    ex_in = raw.get("exercises")
    ex_in = ex_in if isinstance(ex_in, list) else []
    exercises = [x for x in (_normalize_exercise(e) for e in ex_in) if x][:MAX_LIST]
    if not exercises:
        raise ValueError("gym: no usable exercises given — nothing to log")
    return {
        "type": "gym",
        "date": _date(raw.get("date")),
        "exercises": exercises,
        "duration_minutes": _num(raw.get("duration_minutes"), 0, 1440, "duration"),
        "difficulty_1_to_10": _difficulty(raw.get("difficulty")),
        "form_notes": _text(raw.get("form_notes")),
        "weaknesses": _text(raw.get("weaknesses")),
        "coach_notes": _text(raw.get("coach_notes")),
    }


def normalize_injury(raw) -> dict:
    _require_dict(raw, "injury")
    body = _text(raw.get("body_part")).lower()[:60]
    desc = _text(raw.get("description"))
    if not body and not desc:
        raise ValueError("injury: no body part and no description — nothing to log")
    sev = _text(raw.get("severity")).lower()
    return {
        "body_part": body,
        "description": desc or body,
        "severity": sev if sev in VALID_SEVERITIES else "mild",
        "notes": _text(raw.get("notes")),
        "date": _date(raw.get("date")),
    }


def normalize_injury_update(raw) -> dict:
    _require_dict(raw, "injury update")
    body = _text(raw.get("body_part")).lower()[:60]
    status = _text(raw.get("new_status")).lower()
    if not body:
        raise ValueError("injury update: which body part? none given")
    if status not in VALID_STATUSES:
        raise ValueError(f"injury update: new_status must be one of {VALID_STATUSES}, got {status!r}")
    return {"body_part": body, "new_status": status, "notes": _text(raw.get("notes"))}


# ─────────────────────────────────────────────
# SECTION 2 — LOCKED WRITERS
# ─────────────────────────────────────────────

def _append(list_key: str, record: dict) -> None:
    """Locked read-modify-write that appends one record to data[list_key]."""
    initialize_fitness_data()

    def _modify(data):
        if not isinstance(data, dict):
            raise RuntimeError("fitness file has the wrong shape (expected an object)")
        if data.get(list_key) is None:
            data[list_key] = []
        elif not isinstance(data[list_key], list):   # fail loudly, never overwrite real data
            raise RuntimeError(f"fitness file: '{list_key}' is not a list — refusing to overwrite it")
        data[list_key].append(record)
        return data

    update_json(get_data_path(), _modify, default=_starting_structure())


def log_swim(raw) -> str:
    w = normalize_swim(raw)
    w.update(id=str(uuid.uuid4()), logged_at=datetime.now().isoformat())
    _append("workouts", w)
    return f"Swim logged: {w['total_distance_yards']} yards in {w['duration_minutes']} min on {w['date']}."


def log_gym(raw) -> str:
    w = normalize_gym(raw)
    w.update(id=str(uuid.uuid4()), logged_at=datetime.now().isoformat())
    _append("workouts", w)
    return f"Gym workout logged: {len(w['exercises'])} exercise(s) on {w['date']}."


def log_injury(raw) -> str:
    i = normalize_injury(raw)
    record = {
        "id": str(uuid.uuid4()),
        "date_logged": i["date"],
        "body_part": i["body_part"],
        "description": i["description"],
        "severity": i["severity"],
        "notes": i["notes"],
        "status": "active",
    }
    _append("injuries", record)
    return f"Injury logged: {i['description']} (severity {i['severity']}, active)."


def find_open_injuries(injuries: list, body_part: str) -> list:
    """Open (active/recovering) injuries whose body part or description contains the word."""
    hits = []
    for inj in injuries:
        if not isinstance(inj, dict) or inj.get("status") not in OPEN_STATUSES:
            continue
        haystack = f"{inj.get('body_part') or ''} {inj.get('description') or ''}"
        if contains_keyword(haystack, [body_part]):
            hits.append(inj)
    return hits


def update_injury_status(raw) -> tuple:
    """
    'my shoulder is better now' -> status change on the ONE matching open
    injury. Returns (ok, message). Zero matches or several matches change
    NOTHING and say so — it never guesses which injury you meant.
    """
    u = normalize_injury_update(raw)
    initialize_fitness_data()
    result = {"ok": False, "msg": ""}

    def _modify(data):
        if not isinstance(data, dict):
            raise RuntimeError("fitness file has the wrong shape (expected an object)")
        raw_injuries = data.get("injuries")
        injuries = raw_injuries if isinstance(raw_injuries, list) else []
        hits = find_open_injuries(injuries, u["body_part"])
        if not hits:
            result["msg"] = f"No open injury matching '{u['body_part']}' — nothing changed."
        elif len(hits) > 1:
            names = "; ".join(str(h.get("description")) for h in hits)
            result["msg"] = f"More than one open injury matches '{u['body_part']}' ({names}) — nothing changed, be more specific."
        elif hits[0].get("status") == u["new_status"]:
            result["msg"] = f"'{hits[0].get('description')}' is already {u['new_status']} — nothing changed."
        else:
            old = hits[0].get("status")
            hits[0]["status"] = u["new_status"]
            hits[0]["status_updated"] = datetime.now().strftime("%Y-%m-%d")
            if u["notes"]:
                prev = str(hits[0].get("notes") or "")
                hits[0]["notes"] = (prev + " | " if prev else "") + u["notes"]
            result["ok"] = True
            result["msg"] = f"Injury updated: {hits[0].get('description')} — {old} → {u['new_status']}."
        return data

    update_json(get_data_path(), _modify, default=_starting_structure())
    return result["ok"], result["msg"]