"""
PROGRAMS (ATLAS, increment 3b) - pure Python: the program templates, the numbers for each goal,
how big a session is for the minutes Joey has, and where he is in the rotation.

NO model, NO files, NO network here. Everything is a table or a small function, so it can be tested
exactly. The plan builder (3d) will ask THESE functions what to build; a model only picks exercises.

RULES
- The rotation advances one day per TAGGED workout (a workout whose block carried 'Program:' and
  'Day:' lines), no matter how many calendar days pass. Workouts without a tag never move it.
- Workouts tagged with a DIFFERENT program style are ignored, so changing style restarts at day 1.
- 'set next day <label>' is a manual override that lasts only until the next tagged workout.
- Every day carries a core (abs) finisher, as asked; it is dropped only for short sessions.
"""
from typing import Any, Optional

from agents.atlas import training_profile as profiles

CORE_FINISHER = ["abs", "core"]

PROGRAMS: dict[str, dict[str, Any]] = {
    "ppl": {"label": "push / pull / legs", "days": [
        {"label": "Push", "focus": ["chest", "shoulders", "triceps"]},
        {"label": "Pull", "focus": ["back", "biceps", "rear delts", "forearms"]},
        {"label": "Legs", "focus": ["quads", "hamstrings", "glutes", "calves"]},
    ]},
    "upper_lower": {"label": "upper / lower", "days": [
        {"label": "Upper", "focus": ["chest", "back", "shoulders", "biceps", "triceps", "forearms"]},
        {"label": "Lower", "focus": ["quads", "hamstrings", "glutes", "calves"]},
    ]},
    "full_body": {"label": "full body A/B", "days": [
        {"label": "Full body A", "focus": ["quads", "chest", "back", "shoulders"]},
        {"label": "Full body B", "focus": ["hamstrings", "glutes", "back", "chest", "biceps", "triceps", "forearms"]},
    ]},
    "bro_split": {"label": "bro split", "days": [
        {"label": "Chest", "focus": ["chest"]},
        {"label": "Back", "focus": ["back", "rear delts", "forearms"]},
        {"label": "Shoulders", "focus": ["shoulders"]},
        {"label": "Arms", "focus": ["biceps", "triceps", "forearms"]},
        {"label": "Legs", "focus": ["quads", "hamstrings", "glutes", "calves"]},
    ]},
}

# sets / reps / rest are (low, high) ranges; RPE is a single number.
GOAL_PARAMS: dict[str, dict[str, Any]] = {
    "strength": {"sets": (4, 4), "reps": (3, 6), "rest_seconds": (180, 180), "rpe_main": 8, "rpe_accessory": 7},
    "muscle": {"sets": (3, 4), "reps": (8, 12), "rest_seconds": (90, 90), "rpe_main": 8, "rpe_accessory": 7},
    "fat_loss": {"sets": (2, 3), "reps": (12, 20), "rest_seconds": (45, 60), "rpe_main": 7, "rpe_accessory": 6},
    "endurance": {"sets": (2, 3), "reps": (12, 20), "rest_seconds": (45, 60), "rpe_main": 7, "rpe_accessory": 6},
    "general": {"sets": (3, 3), "reps": (8, 12), "rest_seconds": (75, 75), "rpe_main": 7, "rpe_accessory": 7},
}
WARMUP_RPE = 5
DEFAULT_MINUTES = 60


def _has(table, key) -> bool:
    """True when `key` is a text key of `table` (a list or dict from a damaged file must never crash a lookup)."""
    return isinstance(key, str) and key in table


def goal_params(goal_type) -> dict:
    """The numbers for a goal type; anything unknown gets the 'general' numbers."""
    return GOAL_PARAMS[goal_type] if _has(GOAL_PARAMS, goal_type) else GOAL_PARAMS["general"]


def session_shape(minutes) -> dict:
    """How big a session is: warmup moves, main exercises, cooldown moves, and whether a core finisher fits."""
    m = minutes if isinstance(minutes, int) and not isinstance(minutes, bool) and 15 <= minutes <= 180 else DEFAULT_MINUTES
    main = 2 if m < 25 else 3 if m < 38 else 4 if m < 53 else 5 if m < 76 else 6
    return {"minutes": m, "warmup": 3 if m <= 45 else 4, "main": main,
            "cooldown": 2 if m <= 45 else 3, "core_finisher": m >= 40}


def resolve_style(profile) -> tuple:
    """(style key, plain-English reason). 'you decide' is settled from the days per week."""
    style = profile.get("program_style") if isinstance(profile, dict) else None
    if _has(PROGRAMS, style):
        return style, "your choice"
    days = profile.get("days_per_week") if isinstance(profile, dict) else None
    if isinstance(days, bool) or not isinstance(days, int):
        return "full_body", "you said 'you decide' and no days per week is set, so full body (it works on any schedule)"
    if days <= 3:
        return "full_body", f"you said 'you decide', so I chose it from your {days} days a week"
    if days == 4:
        return "upper_lower", "you said 'you decide', so I chose it from your 4 days a week"
    return "ppl", f"you said 'you decide', so I chose it from your {days} days a week"


def _norm(label) -> str:
    return " ".join(label.lower().split()) if isinstance(label, str) else ""


def find_day(style, label) -> Optional[int]:
    """The index of the day with this label (case and spacing do not matter), else None."""
    if not _has(PROGRAMS, style):
        return None
    wanted = _norm(label)
    if not wanted:
        return None
    for i, day in enumerate(PROGRAMS[style]["days"]):
        if _norm(day["label"]) == wanted:
            return i
    return None


def day_info(style, index) -> dict:
    """{'label', 'focus', 'core_finisher'} for one day of a program."""
    day = PROGRAMS[style]["days"][index]
    return {"label": day["label"], "focus": list(day["focus"]), "core_finisher": True}


def _latest_tagged(style, workouts):
    """(sort key, day index, workout) of the most recent workout tagged with this style, or None."""
    best = None
    for w in workouts if isinstance(workouts, list) else []:
        if not isinstance(w, dict):
            continue
        tag = w.get("program")
        tag_style = tag if _has(PROGRAMS, tag) else profiles.parse_program_style(tag)
        if tag_style != style:
            continue
        idx = find_day(style, w.get("program_day"))
        if idx is None:
            continue
        key = (str(w.get("date") or ""), str(w.get("logged_at") or ""))
        if best is None or key > best[0]:
            best = (key, idx, w)
    return best


def rotation_state(style, workouts, override=None) -> dict:
    """Where Joey is: the next day, the last tagged workout, and why."""
    if not _has(PROGRAMS, style):
        raise ValueError(f"unknown program style: {str(style)[:30]}")
    n = len(PROGRAMS[style]["days"])
    last = _latest_tagged(style, workouts)
    last_info = None
    if last is not None:
        last_info = {"label": PROGRAMS[style]["days"][last[1]]["label"], "date": str(last[2].get("date") or "")}
    if isinstance(override, dict):
        idx = find_day(style, override.get("day"))
        set_at = str(override.get("set_at") or "")
        if idx is not None and set_at and (last is None or set_at > last[0][1]):
            return {"style": style, "next_index": idx, "next": day_info(style, idx), "last": last_info,
                    "reason": "you set it by hand"}
    if last is None:
        return {"style": style, "next_index": 0, "next": day_info(style, 0), "last": None,
                "reason": "no tagged workout yet in this program, so it starts at day 1"}
    nxt = (last[1] + 1) % n
    return {"style": style, "next_index": nxt, "next": day_info(style, nxt), "last": last_info,
            "reason": "the day after your last tagged workout"}


def next_day_after(style, label) -> Optional[dict]:
    """The day that follows `label` in a program (wrapping round), or None when style or label are unknown."""
    idx = find_day(style, label)
    if idx is None:
        return None
    return day_info(style, (idx + 1) % len(PROGRAMS[style]["days"]))


def next_day_hint(program, day_label) -> str:
    """A line for the end of 'Workout logged...' when the workout was tagged, else ''. Reads no files."""
    style = program if _has(PROGRAMS, program) else profiles.parse_program_style(program)
    if not isinstance(style, str) or style not in PROGRAMS:
        return ""
    nxt = next_day_after(style, day_label)
    if nxt is None:
        return ""
    return f"\nNext in your {PROGRAMS[style]['label']} program: {nxt['label']}."


def _range(low, high, unit="") -> str:
    return f"{low}{unit}" if low == high else f"{low}-{high}{unit}"


def describe_program(profile, workouts) -> str:
    """Plain text for 'my program': the style, the days in order, what is next, and the numbers per session."""
    if not isinstance(profile, dict):
        raise ValueError("describe_program needs a profile (a dict)")
    style, reason = resolve_style(profile)
    state = rotation_state(style, workouts, profile.get("next_day"))
    p = profiles.normalize_profile(profile)
    shape = session_shape(p["session_minutes"])
    gp = goal_params(p["goal_type"])
    lines = [f"Your program: {PROGRAMS[style]['label']} ({reason})", "Days in order:"]
    for i, day in enumerate(PROGRAMS[style]["days"], 1):
        lines.append(f"  {i}. {day['label']}: {', '.join(day['focus'])}, plus a core (abs) finisher")
    last_date = state["last"]["date"] if state["last"] else ""
    if state["last"] is None:
        lines.append(f"Next: {state['next']['label']} ({state['reason']}).")
    elif state["reason"] == "you set it by hand":
        lines.append(f"Next: {state['next']['label']} (you set it by hand; your last tagged workout was "
                     f"{state['last']['label']} on {last_date or 'an unknown date'}).")
    else:
        lines.append(f"Next: {state['next']['label']} ({state['reason']}: {state['last']['label']} on {state['last']['date'] or 'an unknown date'}).")
    core = "with a core finisher" if shape["core_finisher"] else "without the core finisher (too short)"
    lines.append(f"A {shape['minutes']}-minute session: {shape['warmup']} warmup moves, {shape['main']} main exercises {core}, "
                 f"{shape['cooldown']} cooldown moves.")
    lines.append(f"For your goal ({profiles.GOAL_TYPE_LABELS[p['goal_type']]}): {_range(*gp['sets'])} sets of {_range(*gp['reps'])} reps, "
                 f"rest {_range(*gp['rest_seconds'], unit=' sec')}, target RPE {gp['rpe_main']} on main lifts and {gp['rpe_accessory']} on accessories "
                 f"(warmups {WARMUP_RPE}).")
    return "\n".join(lines)