"""
PROGRESSION (ATLAS, increment 3c) - pure Python: what weight to try next for an exercise, worked out
from Joey's own logged workouts. NO model, NO files, NO network. The plan builder (3d) will ask THIS
module for every weight; a model never invents or does arithmetic on a weight.

THE RULES (agreed with Joey)
- Look at the LAST 2 sessions of that exact exercise (matched by name, ignoring DB/dumbbell spelling
  and case; extra names can be passed in).
- A session is a SUCCESS when every prescribed set hit the prescribed reps (or seconds) and the RPE
  was at or below the target (a missing RPE is allowed, and said so). It is a STRUGGLE when reps were
  missed (or sets skipped) OR the RPE was 2 or more above the target. Anything else is NEUTRAL.
- Last session SUCCESS  -> add weight: +5 lbs on big lifts, +2.5 lbs on small lifts, then round to
  what the equipment allows (dumbbells of 20 lbs or more go up in 5s, everything else in 2.5s).
  Even a very easy session gets the same normal step: big jumps are how people get hurt.
- Last session NEUTRAL, or ONE struggle -> repeat the same weight.
- TWO struggles in a row -> drop about 10 percent (rounded down to the equipment step).
- No history -> NO weight is invented: the advice is to pick a weight that feels like RPE 6.
- Bodyweight exercises have no weight to progress (the plan builder progresses reps instead).
"""
import math
import re
from typing import Any, Optional

from agents.atlas import exercise_library as library

BIG_STEP = 5.0
SMALL_STEP = 2.5
DELOAD_FACTOR = 0.9
SESSIONS_LOOKED_AT = 2
MAX_WORKOUTS_SCANNED = 20000
MAX_PLAUSIBLE_LBS = 5000.0       # a logged weight above this is treated as a typo, never worked from

_SMALL_NAME_RE = re.compile(
    r"\b(?:curls?|raises?|extensions?|pushdowns?|kickbacks?|calf|calves|crunch(?:es)?|face pulls?|wrist|fly|flye|flyes|flies"
    r"|shrugs?|planks?)\b", re.IGNORECASE)
_COMPOUND_NAME_RE = re.compile(r"\b(?:press|overhead|military)\b", re.IGNORECASE)
_SMALL_MUSCLE_RE = re.compile(r"bicep|tricep|shoulder|delt|calf|calves|forearm|\babs?\b|abdominal|\bcore\b|\btrap", re.IGNORECASE)


# --------------------------------------------------------------
# SMALL HELPERS (all tolerate junk: it is Joey's data)
# --------------------------------------------------------------

def _num(x):
    if isinstance(x, bool) or not isinstance(x, (int, float)):
        return None
    if x != x or x in (float("inf"), float("-inf")):
        return None
    return x


def _tidy(n):
    n = float(n)
    return int(n) if n == int(n) else n


def _fmt(n) -> str:
    n = _num(n)
    return "?" if n is None else str(_tidy(round(n, 2)))


def round_to_unit(x: float, unit: float) -> float:
    """The nearest multiple of `unit` (halves round up)."""
    return math.floor(x / unit + 0.5) * unit


def next_up(last: float, step: float, unit: float) -> float:
    """The next weight after a success: last + step, rounded to the equipment, and always above `last`."""
    candidate = round_to_unit(last + step, unit)
    return candidate if candidate > last else last + unit


def deload_weight(last: float, unit: float) -> Optional[float]:
    """About 10 percent lighter, rounded DOWN to the equipment step, and always lighter than `last`. None if too light to drop."""
    if last <= unit:
        return None
    candidate = math.floor(last * DELOAD_FACTOR / unit) * unit
    if candidate >= last:
        candidate = last - unit
    return candidate if candidate >= unit else None


def is_dumbbell(name, equipment=None) -> bool:
    words = library.normalize_name(name).split()
    if "dumbbell" in words:
        return True
    if isinstance(equipment, list):
        return any(isinstance(e, str) and "dumbbell" in library.normalize_name(e).split() for e in equipment)
    return False


def is_small_lift(name, primary_muscles=None) -> bool:
    """Small lift (+2.5 lbs steps) or big lift (+5). Words in the name first, then the library's muscles."""
    text = library.normalize_name(name)
    if _COMPOUND_NAME_RE.search(text):
        return False
    if _SMALL_NAME_RE.search(text):
        return True
    muscles = [m for m in primary_muscles if isinstance(m, str) and m.strip()] if isinstance(primary_muscles, list) else []
    return bool(muscles) and all(_SMALL_MUSCLE_RE.search(m) for m in muscles)


def weight_unit(name, weight, equipment=None) -> float:
    """What the equipment allows: dumbbells of 20 lbs or more go up in 5s, everything else in 2.5s."""
    return 5.0 if is_dumbbell(name, equipment) and weight >= 20 else 2.5


# --------------------------------------------------------------
# HISTORY
# --------------------------------------------------------------

def _names_of(name, aliases) -> set:
    names = {library.normalize_name(name)}
    if isinstance(aliases, list):
        names |= {library.normalize_name(a) for a in aliases}
    names.discard("")
    return names


def find_sessions(name, workouts, aliases=None, limit: int = SESSIONS_LOOKED_AT) -> list:
    """[(date, exercise record), ...] for this exercise, newest first (by date, then by when it was logged)."""
    wanted = _names_of(name, aliases)
    found = []
    if not wanted or not isinstance(workouts, list):
        return []
    for w in workouts[-MAX_WORKOUTS_SCANNED:]:
        if not isinstance(w, dict):
            continue
        exercises = w.get("exercises")
        for ex in exercises if isinstance(exercises, list) else []:
            if isinstance(ex, dict) and library.normalize_name(ex.get("name")) in wanted:
                key = (str(w.get("date") or ""), str(w.get("logged_at") or ""))
                found.append((key, ex))
                break
    found.sort(key=lambda item: item[0], reverse=True)
    return [(key[0], ex) for key, ex in found[:limit]]


def evaluate_session(ex) -> dict:
    """What one logged session of an exercise says: success / neutral / struggle / unknown, and the numbers behind it."""
    ex = ex if isinstance(ex, dict) else {}
    raw_sets = ex.get("set_details")
    sets = [d for d in raw_sets if isinstance(d, dict)] if isinstance(raw_sets, list) else []
    raw_weight = _num(ex.get("weight_lbs"))
    top = raw_weight if raw_weight and 0 < raw_weight <= MAX_PLAUSIBLE_LBS else None
    implausible = bool(raw_weight and raw_weight > MAX_PLAUSIBLE_LBS)
    raw_prescribed = ex.get("prescribed")
    p: dict = raw_prescribed if isinstance(raw_prescribed, dict) else {}
    planned_sets, planned_reps, planned_secs = _num(p.get("sets")), _num(p.get("reps")), _num(p.get("seconds"))
    target_rpe = _num(p.get("target_rpe"))
    rpe = _num(ex.get("rpe"))
    base = {"top_weight": top, "implausible": implausible, "rpe": rpe, "target_rpe": target_rpe, "sets_done": len(sets), "planned_sets": planned_sets,
            "planned_reps": planned_reps, "planned_seconds": planned_secs}
    if planned_sets is None or (planned_reps is None and planned_secs is None):
        return {**base, "status": "unknown", "reps_hit": None}
    if planned_reps is not None:
        hits = sum(1 for d in sets if (_num(d.get("reps")) or 0) >= planned_reps)
    else:
        hits = sum(1 for d in sets if (_num(d.get("seconds")) or 0) >= (planned_secs or 0))
    reps_hit = hits >= planned_sets
    too_hard = rpe is not None and target_rpe is not None and rpe >= target_rpe + 2
    if not reps_hit or too_hard:
        status = "struggle"
    elif rpe is None or target_rpe is None or rpe <= target_rpe:
        status = "success"
    else:
        status = "neutral"
    return {**base, "status": status, "reps_hit": reps_hit, "sets_hit": hits}


def _session_text(date: str, ev: dict) -> str:
    done = f"{ev['sets_done']} of {_fmt(ev['planned_sets'])} sets"
    if ev["reps_hit"]:
        reps = "every rep hit"
    elif ev.get("sets_hit") is not None and ev.get("planned_sets") is not None:
        goal = f"{_fmt(ev['planned_reps'])} reps" if ev.get("planned_reps") is not None else f"{_fmt(ev.get('planned_seconds'))} sec"
        reps = f"{ev['sets_hit']} of {_fmt(ev['planned_sets'])} sets hit the prescribed {goal}"
    else:
        reps = "no prescription to compare"
    rpe = (f"RPE {_fmt(ev['rpe'])} against a target of {_fmt(ev['target_rpe'])}" if ev["rpe"] is not None and ev["target_rpe"] is not None
           else "no RPE to compare")
    return f"on {date or 'an unknown date'} you did {done} at {_fmt(ev['top_weight'])} lbs ({reps}, {rpe})"


# --------------------------------------------------------------
# THE ANSWER
# --------------------------------------------------------------

def suggest_weight(name, workouts, aliases=None, primary_muscles=None, equipment=None) -> dict:
    """
    What to try next for one exercise. Returns:
      {"exercise", "action" (increase / hold / deload / new / bodyweight / unknown), "weight_lbs" (or None),
       "last_weight_lbs", "step", "unit", "small_lift", "sessions_used", "reason" (plain English), "notes" [..]}
    A weight is only ever worked out from logged data; with no usable data it is None, never a guess.
    """
    label = str(name)[:100] if isinstance(name, str) else "?"
    small = is_small_lift(name, primary_muscles)
    result: dict[str, Any] = {"exercise": label, "action": "new", "weight_lbs": None, "last_weight_lbs": None,
                              "step": SMALL_STEP if small else BIG_STEP, "unit": None, "small_lift": small,
                              "sessions_used": 0, "reason": "", "notes": []}
    sessions = find_sessions(name, workouts, aliases)
    result["sessions_used"] = len(sessions)
    if not sessions:
        result["reason"] = "no history for this exercise yet, so no weight is invented: pick a weight that feels like RPE 6"
        return result
    last_date, last_ex = sessions[0]
    last = evaluate_session(last_ex)
    if last["implausible"]:
        result.update(action="unknown", reason=f"the weight logged on {last_date or 'an unknown date'} is not believable "
                                               "(over 5,000 lbs), so I cannot work from it: check that log entry")
        return result
    if last["top_weight"] is None:
        result["action"] = "bodyweight"
        result["reason"] = "no weight was used last time, so there is no weight to progress (progress the reps instead)"
        return result
    weight = last["top_weight"]
    unit = weight_unit(name, weight, equipment)
    result["last_weight_lbs"] = _tidy(weight)
    result["unit"] = unit
    seen = _session_text(last_date, last)
    if last["status"] == "unknown":
        result.update(action="unknown", weight_lbs=_tidy(weight),
                      reason=f"{seen}, but no prescription was recorded, so I cannot tell if it was too easy or too hard: repeat {_fmt(weight)} lbs")
        return result
    if last["status"] == "success":
        new = next_up(weight, result["step"], unit)
        if last["rpe"] is None or last["target_rpe"] is None:
            result["notes"].append("no RPE was logged, so I went by the reps alone")
        result.update(action="increase", weight_lbs=_tidy(new),
                      reason=f"{seen}: a success, so +{_fmt(new - weight)} lbs to {_fmt(new)} lbs")
        return result
    if last["status"] == "neutral":
        result.update(action="hold", weight_lbs=_tidy(weight),
                      reason=f"{seen}: reps hit but harder than planned, so repeat {_fmt(weight)} lbs")
        return result
    previous = evaluate_session(sessions[1][1]) if len(sessions) > 1 else None
    if previous is not None and previous["status"] == "struggle":
        lighter = deload_weight(weight, unit)
        if lighter is not None:
            result.update(action="deload", weight_lbs=_tidy(lighter),
                          reason=f"{seen}: a struggle, and the session before it (on {sessions[1][0] or 'an unknown date'}) was one too, "
                                 f"so drop to {_fmt(lighter)} lbs (about 10% lighter)")
            return result
        result["notes"].append("it is already too light to drop further")
    result.update(action="hold", weight_lbs=_tidy(weight),
                  reason=f"{seen}: a struggle, so repeat {_fmt(weight)} lbs")
    return result


def _entry_names(entry: dict) -> set:
    names = {library.normalize_name(entry.get("name"))}
    aliases = entry.get("aliases")
    if isinstance(aliases, list):
        names |= {library.normalize_name(a) for a in aliases}
    names.discard("")
    return names


def suggest_for(names, workouts, library_entries=None) -> dict:
    """{exercise name: suggestion} for several exercises. `library_entries` (dicts from the exercise library) supply other names, muscles and equipment."""
    entries = [e for e in library_entries if isinstance(e, dict)] if isinstance(library_entries, list) else []
    out = {}
    for name in names if isinstance(names, list) else []:
        if not isinstance(name, str):
            continue
        key = library.normalize_name(name)
        entry = None
        for candidate in entries:
            if key and key in _entry_names(candidate):
                entry = candidate
                break
        if entry is None:
            out[name] = suggest_weight(name, workouts)
            continue
        raw_aliases = entry.get("aliases")
        aliases: list = [entry.get("name")]
        if isinstance(raw_aliases, list):
            aliases += raw_aliases
        out[name] = suggest_weight(name, workouts, aliases=aliases, primary_muscles=entry.get("primary_muscles"),
                                   equipment=entry.get("equipment"))
    return out


def describe_suggestion(s: dict) -> str:
    """The suggestion as plain text (for the 'next weight' command)."""
    if not isinstance(s, dict):
        raise ValueError("describe_suggestion needs a suggestion (a dict)")
    action = s.get("action")
    head = {"increase": "Try", "hold": "Repeat", "deload": "Drop to", "unknown": "Repeat"}.get(action) if isinstance(action, str) else None
    if head and s.get("weight_lbs") is not None:
        line = f"{s.get('exercise')}: {head} {_fmt(s['weight_lbs'])} lbs."
    elif action == "bodyweight":
        line = f"{s.get('exercise')}: bodyweight, no weight to set."
    else:
        line = f"{s.get('exercise')}: no weight yet."
    lines = [line, f"Why: {s.get('reason')}."]
    kind = "small" if s.get("small_lift") else "big"
    if s.get("unit"):
        lines.append(f"({kind} lift: steps of {_fmt(s['step'])} lbs, rounded to {_fmt(s['unit'])} lbs.)")
    for note in s.get("notes") or []:
        lines.append(f"Note: {note}.")
    return "\n".join(lines)