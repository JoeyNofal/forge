"""
ATLAS TOOLS — read-only fitness data engine (increment (a): core chat).

Rebuilt from reference/atlas_tools.py. Everything that WRITES workouts or
injuries (log_swim_workout, log_gym_workout, log_injury) is deliberately
NOT here yet — that is increment (b), built and tested on its own. The
photo scan is increment (d). The old duplicate web search is gone; ATLAS
uses shared/web_search.py like every other agent (Lesson #9).

Real fixes vs the old code:
- The data path is an env var (FITNESS_DATA_PATH), read at CALL time, and
  defaults to a FORGE-only file (data/fitness.json inside this repo) —
  never to the old NEXUS SYSTEM's real fitness.json. Pointing ATLAS at a
  real file is an explicit choice, not an accident.
- The file auto-creates if missing (Youssef's decision — fitness data
  legitimately starts empty), created atomically under a lock so 20
  simultaneous first-callers can never produce a half-written file or
  two competing creations (Lesson #4).
- Loading raises a clear RuntimeError on a real problem instead of
  crashing with a raw traceback. A mid-write read (the Training tracker
  writes the whole file non-atomically) gets one quick retry before it
  is called corruption (Lesson #12).
- Every reader tolerates BOTH data shapes now in the real file: the old
  ATLAS shapes and the Training tracker's (weaknesses as a string OR a
  list, exercises as dicts OR plain strings, null distances/durations,
  a missing date, a non-dict entry). One malformed entry can never take
  the whole agent down (Lesson #5) — the old code crashed on a missing
  date and printed weaknesses lists as raw Python.
"""
import json
import os
import time
import uuid
from datetime import datetime

from dotenv import load_dotenv
from filelock import FileLock

load_dotenv(override=True)  # Lesson #12: .env must win over a stale system env var

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_FITNESS_DATA_PATH = os.path.join(_REPO_ROOT, "data", "fitness.json")


def get_data_path() -> str:
    """Read at call time (not import time) so tests and .env changes work."""
    return os.path.abspath(os.getenv("FITNESS_DATA_PATH") or DEFAULT_FITNESS_DATA_PATH)


# ─────────────────────────────────────────────
# SECTION 1 — FILE SETUP AND LOADING
# ─────────────────────────────────────────────

def _starting_structure() -> dict:
    return {
        "profile": {
            "name": "Joey",
            "units": "imperial",
            "notes": "Former competitive swimmer. Specialized in breaststroke, IM, and long-distance freestyle. Also did open water. Currently training casually to get back in shape."
        },
        "workouts": [],
        "body_metrics": [],
        "injuries": [
            {
                "id": str(uuid.uuid4()),
                "date_logged": datetime.now().isoformat(),
                "description": "No injuries currently on file. Add as needed.",
                "status": "none"
            }
        ],
        "plans": []
    }


def initialize_fitness_data() -> bool:
    """
    Creates the data file with a clean starting structure if it doesn't
    exist. Safe to call any number of times, from any number of threads.
    Returns True only if THIS call created the file.
    """
    path = get_data_path()
    if os.path.exists(path):
        return False

    os.makedirs(os.path.dirname(path), exist_ok=True)
    with FileLock(path + ".lock", timeout=10):
        if os.path.exists(path):  # someone else created it while we waited
            return False
        tmp_path = path + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(_starting_structure(), f, indent=2, ensure_ascii=False)
        os.replace(tmp_path, path)  # atomic: a reader never sees half a file
        return True


def load_fitness_data() -> dict:
    """
    Returns the whole fitness file as a dict. Auto-creates it if missing.
    Raises RuntimeError with a specific message on a real problem.
    """
    initialize_fitness_data()
    path = get_data_path()

    data = None
    last_error = None
    for attempt in range(2):
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            break
        except json.JSONDecodeError as e:
            last_error = e
            if attempt == 0:
                time.sleep(0.3)  # the Training tracker may be mid-write; retry once
        except OSError as e:
            raise RuntimeError(f"Could not read the fitness data file at {path}: {e}")
    else:
        raise RuntimeError(
            f"The fitness data file at {path} is malformed (not valid JSON): {last_error}"
        )

    if not isinstance(data, dict):
        raise RuntimeError(
            f"The fitness data file at {path} has the wrong shape "
            f"(expected a JSON object, found {type(data).__name__})."
        )
    return data


# ─────────────────────────────────────────────
# SECTION 2 — SAFE HELPERS (Lesson #5: never trust the shape)
# ─────────────────────────────────────────────

def _safe_num(v) -> float:
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def _show(v):
    """Display value: None/empty becomes 'unknown' instead of printing 'None'."""
    return "unknown" if v is None or v == "" else v


def _as_text(v) -> str:
    """Turns a string OR a list (the tracker stores weaknesses as a list) into one readable string."""
    if v is None:
        return ""
    if isinstance(v, list):
        return ", ".join(str(x) for x in v if x not in (None, ""))
    return str(v)


def _workouts(data: dict) -> list:
    w = data.get("workouts")
    return [x for x in w if isinstance(x, dict)] if isinstance(w, list) else []


def _date(w: dict) -> str:
    return str(w.get("date") or "")


def _exercise_names(w: dict) -> list:
    ex = w.get("exercises")
    if not isinstance(ex, list):
        return []
    names = []
    for e in ex:
        if isinstance(e, dict):
            if e.get("name"):
                names.append(str(e["name"]))
        elif isinstance(e, str) and e.strip():
            names.append(e.strip())
    return names


# ─────────────────────────────────────────────
# SECTION 3 — READING AND ANALYSIS (read-only)
# ─────────────────────────────────────────────

def get_recent_workouts(limit: int = 10) -> str:
    """Most recent workouts (any type), newest first, as a readable summary."""
    workouts = _workouts(load_fitness_data())
    if not workouts:
        return "No workouts logged yet."

    recent = sorted(workouts, key=_date, reverse=True)[:limit]
    lines = [f"Last {len(recent)} workout(s):\n"]
    for w in recent:
        d = _date(w) or "no date"
        kind = w.get("type")
        if kind == "swim":
            lines.append(
                f"  [{d}] SWIM — {_show(w.get('total_distance_yards'))} yards, "
                f"{_show(w.get('duration_minutes'))} min, "
                f"difficulty {_show(w.get('difficulty_1_to_10'))}/10"
            )
        elif kind == "gym":
            names = ", ".join(_exercise_names(w)) or "no exercises listed"
            lines.append(
                f"  [{d}] GYM — {names}, {_show(w.get('duration_minutes'))} min, "
                f"difficulty {_show(w.get('difficulty_1_to_10'))}/10"
            )
        else:
            lines.append(f"  [{d}] {str(_show(kind)).upper()} workout")
    return "\n".join(lines)


def get_swim_history() -> str:
    """Full summary of every swim workout ever logged."""
    swims = [w for w in _workouts(load_fitness_data()) if w.get("type") == "swim"]
    if not swims:
        return "No swim workouts logged yet."

    total_yards = sum(_safe_num(w.get("total_distance_yards")) for w in swims)
    avg_yards = total_yards / len(swims)
    lines = [
        f"Swim history: {len(swims)} session(s), {total_yards:,.0f} total yards, "
        f"avg {avg_yards:,.0f} yards/session\n"
    ]
    for w in sorted(swims, key=_date):
        lines.append(
            f"  [{_date(w) or 'no date'}] {_show(w.get('total_distance_yards'))} yards — "
            f"Strokes: {_as_text(w.get('strokes')) or 'none listed'} — "
            f"Difficulty: {_show(w.get('difficulty_1_to_10'))}/10"
        )
        weak = _as_text(w.get("weaknesses"))
        if weak:
            lines.append(f"    Weaknesses: {weak}")
    return "\n".join(lines)


def get_gym_history() -> str:
    """Full summary of every gym workout ever logged."""
    gyms = [w for w in _workouts(load_fitness_data()) if w.get("type") == "gym"]
    if not gyms:
        return "No gym workouts logged yet."

    lines = [f"Gym history: {len(gyms)} session(s)\n"]
    for w in sorted(gyms, key=_date):
        names = ", ".join(_exercise_names(w)) or "no exercises listed"
        lines.append(
            f"  [{_date(w) or 'no date'}] {names} — {_show(w.get('duration_minutes'))} min — "
            f"Difficulty: {_show(w.get('difficulty_1_to_10'))}/10"
        )
        weak = _as_text(w.get("weaknesses"))
        if weak:
            lines.append(f"    Weaknesses: {weak}")
    return "\n".join(lines)


def get_injury_history() -> str:
    """All logged injuries and their status (the 'none' placeholder is hidden)."""
    injuries = load_fitness_data().get("injuries")
    injuries = [i for i in injuries if isinstance(i, dict)] if isinstance(injuries, list) else []
    real = [i for i in injuries if i.get("status") != "none"]
    if not real:
        return "No injuries on record."

    lines = ["Injury history:\n"]
    for i in real:
        d = str(i.get("date_logged") or "")[:10] or "no date"
        lines.append(
            f"  [{d}] {_show(i.get('description'))} — Status: {_show(i.get('status'))}"
        )
    return "\n".join(lines)


def get_data_summary_for_llm() -> str:
    """
    Plain-English summary of the fitness data, used as ATLAS's context
    before it responds. Counts here are the ONLY counts ATLAS may quote
    (its prompt forbids inventing any).
    """
    data = load_fitness_data()
    workouts = _workouts(data)
    swims = [w for w in workouts if w.get("type") == "swim"]
    gyms = [w for w in workouts if w.get("type") == "gym"]

    raw_profile = data.get("profile")
    profile = raw_profile if isinstance(raw_profile, dict) else {}
    name = profile.get("name") or "Joey"
    notes = profile.get("notes") or ""

    summary = f"""
=== ATLAS DATA SUMMARY ===
Profile: {name} — {notes}

Total workouts logged: {len(workouts)}
  Swim sessions: {len(swims)}
  Gym sessions: {len(gyms)}

{get_recent_workouts(5)}

{get_injury_history()}
=========================
"""
    return summary.strip()