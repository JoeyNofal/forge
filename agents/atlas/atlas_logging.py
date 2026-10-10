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
import hashlib
import json
import re
import uuid
from datetime import datetime

from shared.file_store import update_json
from shared.keyword_gate import contains_keyword
from shared.normalizers import (
    MAX_TEXT, MAX_LIST,
    num as _num, text as _text, str_list as _str_list,
    date_or_today as _date, require_dict as _require_dict,
)
from agents.atlas.atlas_tools import (
    get_data_path, initialize_fitness_data, load_fitness_data, _starting_structure,
)

VALID_SEVERITIES = ("mild", "moderate", "severe")
VALID_STATUSES = ("active", "recovering", "resolved")
OPEN_STATUSES = ("active", "recovering")   # an injury that can still be updated

# Units. ALL unit arithmetic lives here in Python, never in the model prompt
# (a local model once turned "at 50" into 110.23 lbs by assuming kg and doing
# the multiplication itself).
LB_UNITS = ("lb", "lbs", "pound", "pounds")
KG_UNITS = ("kg", "kgs", "kilo", "kilos", "kilogram", "kilograms")
YARD_UNITS = ("yd", "yds", "yard", "yards")
METER_UNITS = ("m", "meter", "meters", "metre", "metres")
KG_TO_LBS = 2.20462
METERS_TO_YARDS = 1.09361
MAX_WEIGHT_LBS = 5000
MAX_SWIM_YARDS = 100000


# ─────────────────────────────────────────────
# SECTION 1 — NORMALIZERS (untrusted in, clean out, or ValueError)
# ─────────────────────────────────────────────

# _num, _text and _str_list live in shared/normalizers.py (imported above).


def _difficulty(v):
    """1-10 if Joey gave one; None if he didn't (never an invented default)."""
    n = _num(v, -10**6, 10**6, "difficulty")
    if not n:
        return None
    return max(1, min(10, int(round(n))))


def _or_none(n):
    """A stated amount stays; 0 (= not stated) becomes None, which the readers show as 'unknown'."""
    return n if n else None


# _date and _require_dict live in shared/normalizers.py (imported above).


def _swim_distance_yards(raw: dict) -> tuple:
    """
    (yards, unit_was_assumed). yards is 0 when no distance was stated.
    The model reports "total_distance" exactly as Joey said it plus
    "distance_unit" only if he wrote one; Python converts. No unit -> yards,
    flagged. The older "total_distance_yards" key is still accepted, unflagged.
    """
    legacy = raw.get("total_distance_yards")
    if legacy is not None and legacy != "":
        return _num(legacy, 0, MAX_SWIM_YARDS, "distance"), False
    stated = _num(raw.get("total_distance"), 0, 10**7, "distance")
    if not stated:
        return 0, False
    unit = _text(raw.get("distance_unit")).lower()
    yards = round(stated * METERS_TO_YARDS, 2) if unit in METER_UNITS else stated
    if yards > MAX_SWIM_YARDS:
        raise ValueError(f"distance out of range: {yards!r}")
    yards = int(yards) if yards == int(yards) else yards
    return yards, unit not in YARD_UNITS and unit not in METER_UNITS


def normalize_swim(raw) -> dict:
    _require_dict(raw, "swim")
    yards, assumed = _swim_distance_yards(raw)
    minutes = _num(raw.get("duration_minutes"), 0, 1440, "duration")
    if yards <= 0 and minutes <= 0:
        raise ValueError("swim: no distance and no duration given — nothing to log")
    result = {
        "type": "swim",
        "date": _date(raw.get("date")),
        "total_distance_yards": _or_none(yards),
        "duration_minutes": _or_none(minutes),
        "strokes": [s.lower() for s in _str_list(raw.get("strokes"))],
        "sets": _str_list(raw.get("sets")),
        "difficulty_1_to_10": _difficulty(raw.get("difficulty")),
        "form_notes": _text(raw.get("form_notes")),
        "weaknesses": _text(raw.get("weaknesses")),
        "coach_notes": _text(raw.get("coach_notes")),
    }
    if assumed:
        result["units_assumed"] = ["distance"]    # shown on the proposal only, never saved
    return result


def unit_family(unit_text) -> str:
    """'lbs' / 'kg' / 'yards' / 'meters' for a unit word the model reported, else ''."""
    u = _text(unit_text).lower()
    if u in LB_UNITS:
        return "lbs"
    if u in KG_UNITS:
        return "kg"
    if u in YARD_UNITS:
        return "yards"
    if u in METER_UNITS:
        return "meters"
    return ""


def _opt_number(v, high):
    """A stated number in [0, high], else None (unknown stays None, never a made-up 0)."""
    if v is None or v == "" or isinstance(v, bool):
        return None
    try:
        n = float(v)
    except (TypeError, ValueError):
        return None
    if n != n or n < 0 or n > high:
        return None
    return int(n) if n == int(n) else n


def _exercise_weight_lbs(e: dict) -> tuple:
    """
    (weight in pounds or None, unit_was_assumed).

    The model reports the number EXACTLY as Joey said it ("weight") plus the
    unit only if he wrote one ("weight_unit"). Python does any conversion.
    No unit stated -> taken as pounds and flagged so the proposal says so.
    The older "weight_lbs" key (already pounds) is still accepted, unflagged.
    """
    stated = e.get("weight")
    if stated is None or stated == "" or isinstance(stated, bool):
        return _opt_number(e.get("weight_lbs"), MAX_WEIGHT_LBS), False
    number = _opt_number(stated, 10**6)
    if number is None:
        return None, False
    unit = _text(e.get("weight_unit")).lower()
    lbs = round(number * KG_TO_LBS, 2) if unit in KG_UNITS else number
    if lbs > MAX_WEIGHT_LBS:
        return None, False
    lbs = int(lbs) if lbs == int(lbs) else lbs
    assumed = unit not in LB_UNITS and unit not in KG_UNITS and lbs != 0
    return lbs, assumed


def _normalize_exercise(e):
    if isinstance(e, str):          # the old bug: models return plain strings
        e = {"name": e}
    if not isinstance(e, dict):
        return None, False
    name = _text(e.get("name"))[:100]
    if not name:
        return None, False
    weight_lbs, assumed = _exercise_weight_lbs(e)
    return {
        "name": name,
        "sets": _opt_number(e.get("sets"), 1000),
        "reps": _opt_number(e.get("reps"), 10000),
        "weight_lbs": weight_lbs,
        "notes": _text(e.get("notes"))[:200],
    }, assumed


def normalize_gym(raw) -> dict:
    _require_dict(raw, "gym")
    ex_in = raw.get("exercises")
    ex_in = ex_in if isinstance(ex_in, list) else []
    kept = []
    for e in ex_in:
        exercise, was_assumed = _normalize_exercise(e)
        if exercise is not None:
            kept.append((exercise, was_assumed))
    kept = kept[:MAX_LIST]
    if not kept:
        raise ValueError("gym: no usable exercises given — nothing to log")
    exercises = [exercise for exercise, _ in kept]
    assumed = [exercise["name"] for exercise, was_assumed in kept if was_assumed]
    result = {
        "type": "gym",
        "date": _date(raw.get("date")),
        "exercises": exercises,
        "duration_minutes": _or_none(_num(raw.get("duration_minutes"), 0, 1440, "duration")),
        "difficulty_1_to_10": _difficulty(raw.get("difficulty")),
        "form_notes": _text(raw.get("form_notes")),
        "weaknesses": _text(raw.get("weaknesses")),
        "coach_notes": _text(raw.get("coach_notes")),
    }
    if assumed:
        result["units_assumed"] = assumed      # shown on the proposal only, never saved
    return result


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
    w.pop("units_assumed", None)   # a proposal-only note, never part of the saved record
    w.update(id=str(uuid.uuid4()), logged_at=datetime.now().isoformat())
    _append("workouts", w)
    dist = f"{w['total_distance_yards']} yards" if w["total_distance_yards"] else "distance not stated"
    mins = f"{w['duration_minutes']} min" if w["duration_minutes"] else "duration not stated"
    return f"Swim logged: {dist}, {mins}, on {w['date']}."


def log_gym(raw) -> str:
    w = normalize_gym(raw)
    w.pop("units_assumed", None)   # a proposal-only note, never part of the saved record
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



# ─────────────────────────────────────────────
# SECTION 3 — WORKOUT BLOCK (the filled-in phone template)
# Input is the dict from workout_block.parse_workout_block(). Weights arrive in
# the unit Joey wrote; ALL conversion to pounds happens here, in Python.
# Old fields (sets / reps / weight_lbs) keep the Training tracker working:
#   sets = completed sets, weight_lbs = HEAVIEST set, reps = reps of that set
#   (no weighted set: the set with the most reps; timed sets: reps stay None).
# ─────────────────────────────────────────────

MAX_BLOCK_EXERCISES = 100


def _set_weight_lbs(weight, unit, warnings: list, name: str):
    """A weight in pounds (rounded), or None. kg is converted HERE."""
    if weight is None or isinstance(weight, bool):
        return None
    number = _opt_number(weight, 10**6)
    if number is None or number == 0:
        return None
    lbs = round(number * KG_TO_LBS, 2) if unit == "kg" else number
    if lbs > MAX_WEIGHT_LBS:
        warnings.append(f"{name}: a weight of {number} {unit or 'lbs'} is too large - left blank")
        return None
    return int(lbs) if lbs == int(lbs) else lbs


def _block_prescribed(p, default_unit: str, warnings: list, name: str):
    if not isinstance(p, dict):
        return None
    unit = p.get("weight_unit") if p.get("weight_unit") in ("lbs", "kg") else default_unit
    return {
        "text": _text(p.get("text"))[:200],
        "sets": _opt_number(p.get("sets"), 1000),
        "reps": _opt_number(p.get("reps"), 10000),
        "seconds": _opt_number(p.get("seconds"), 36000),
        "weight_lbs": _set_weight_lbs(p.get("weight"), unit, warnings, name),
        "bodyweight": bool(p.get("bodyweight")),
        "rest_seconds": _opt_number(p.get("rest_seconds"), 36000),
        "target_rpe": _opt_number(p.get("target_rpe"), 10),
    }


def _block_exercise(ex: dict, section_name: str, default_unit: str, warnings: list):
    """One exercise record, or None when no set was completed (that exercise is 'skipped')."""
    name = _text(ex.get("name"))[:100]
    details = []
    raw_sets = ex.get("sets")
    for s in raw_sets if isinstance(raw_sets, list) else []:
        if not isinstance(s, dict):
            continue
        reps = _opt_number(s.get("reps"), 10000)
        seconds = _opt_number(s.get("seconds"), 36000)
        if reps is None and seconds is None:
            continue
        unit = s.get("weight_unit") if s.get("weight_unit") in ("lbs", "kg") else default_unit
        details.append({
            "set": _opt_number(s.get("set"), 10000),
            "reps": reps,
            "seconds": seconds,
            "weight_lbs": _set_weight_lbs(s.get("weight"), unit, warnings, name),
            "bodyweight": bool(s.get("bodyweight")),
        })
    if not details:
        return None

    weighted = [d for d in details if d["weight_lbs"]]
    if weighted:
        top = max(weighted, key=lambda d: (d["weight_lbs"], d["reps"] or 0))
    else:
        repped = [d for d in details if d["reps"]]
        top = max(repped, key=lambda d: d["reps"]) if repped else None
    return {
        "name": name,
        "section": section_name,
        "sets": len(details),
        "reps": top["reps"] if top else None,
        "weight_lbs": top["weight_lbs"] if top else None,
        "notes": _text(ex.get("notes"))[:500],
        "rpe": _opt_number(ex.get("rpe"), 10),
        "set_details": details,
        "prescribed": _block_prescribed(ex.get("prescribed"), default_unit, warnings, name),
    }


def normalize_workout_block(parsed) -> dict:
    """
    parse_workout_block() output -> one clean gym-workout record, or ValueError.
    Exercises with no completed set are listed in "skipped", never saved as done.
    "units_assumed" and "warnings" are proposal-only notes; they are never saved.
    """
    _require_dict(parsed, "workout block")
    sections = parsed.get("sections")
    if not isinstance(sections, list):
        raise ValueError("workout block: no sections found")
    default_unit = "kg" if parsed.get("unit") == "kg" else "lbs"
    raw_warnings = parsed.get("warnings")
    warnings = [w[:200] for w in raw_warnings if isinstance(w, str)] if isinstance(raw_warnings, list) else []

    main, warmup, cooldown, skipped = [], [], [], []
    for sec in sections:
        if not isinstance(sec, dict):
            continue
        section_name = _text(sec.get("name"))[:100]
        kind = sec.get("kind")
        target = warmup if kind == "warmup" else cooldown if kind == "cooldown" else main
        exercises = sec.get("exercises")
        for ex in exercises if isinstance(exercises, list) else []:
            if not isinstance(ex, dict) or not _text(ex.get("name")):
                continue
            record = _block_exercise(ex, section_name, default_unit, warnings)
            if record is None:
                skipped.append(_text(ex.get("name"))[:100])
            elif len(target) < MAX_BLOCK_EXERCISES:
                target.append(record)
    if not (main or warmup or cooldown):
        raise ValueError("workout block: no exercise has a completed set - nothing to log")

    result = {
        "type": "gym",
        "source": "workout_block",
        "title": _text(parsed.get("title"))[:100] or "Workout",
        "date": _date(parsed.get("date")),
        "exercises": main,
        "warmup": warmup,
        "cooldown": cooldown,
        "skipped": skipped[:MAX_BLOCK_EXERCISES],
        "duration_minutes": None,
        "difficulty_1_to_10": None,
        "form_notes": "",
        "weaknesses": "",
        "coach_notes": "",
    }
    result["block_hash"] = hashlib.sha256(
        json.dumps(result, sort_keys=True).encode("utf-8")).hexdigest()[:16]
    assumed = parsed.get("units_assumed")
    if isinstance(assumed, list) and assumed:
        result["units_assumed"] = [str(a)[:100] for a in assumed]
    if warnings:
        result["warnings"] = warnings[:50]
    return result


def is_duplicate_workout_block(block_hash) -> bool:
    """Read-only: has a workout with this block_hash already been saved?"""
    workouts = load_fitness_data().get("workouts")
    if not isinstance(workouts, list):
        return False
    return any(isinstance(w, dict) and w.get("block_hash") == block_hash for w in workouts)


def log_workout_block(clean) -> tuple:
    """
    Saves a normalized workout-block record. Returns (ok, message).
    One locked read-modify-write. The same completed workout is never saved twice.
    """
    _require_dict(clean, "workout")
    if clean.get("source") != "workout_block" or not isinstance(clean.get("block_hash"), str):
        raise ValueError("workout: not a normalized workout-block record")
    for key in ("exercises", "warmup", "cooldown", "skipped"):
        if not isinstance(clean.get(key), list):
            raise ValueError(f"workout: '{key}' must be a list")
    record = {k: v for k, v in clean.items() if k not in ("units_assumed", "warnings")}
    record.update(id=str(uuid.uuid4()), logged_at=datetime.now().isoformat())

    initialize_fitness_data()
    result = {"ok": False, "msg": ""}

    def _modify(data):
        if not isinstance(data, dict):
            raise RuntimeError("fitness file has the wrong shape (expected an object)")
        if data.get("workouts") is None:
            data["workouts"] = []
        elif not isinstance(data["workouts"], list):     # fail loudly, never overwrite real data
            raise RuntimeError("fitness file: 'workouts' is not a list - refusing to overwrite it")
        if any(isinstance(w, dict) and w.get("block_hash") == record["block_hash"] for w in data["workouts"]):
            result["msg"] = "This workout was already logged - nothing changed."
            return data
        data["workouts"].append(record)
        result["ok"] = True
        result["msg"] = (f"Workout logged: {record['title']}, {len(record['exercises'])} exercise(s), "
                         f"{len(record['warmup'])} warmup, {len(record['cooldown'])} cooldown, "
                         f"on {record['date']}.")
        return data

    update_json(get_data_path(), _modify, default=_starting_structure())
    return result["ok"], result["msg"]