"""
PLAN FACTS (ATLAS, increment 3d-1) - pure Python: gathers every FACT the plan builder needs for
"next workout", and nothing else. NO model, NO network, NO writes.

What it answers (all from Joey's own saved data, using the already-tested modules):
- which program day is next, how many exercises fit his minutes, the sets/reps/rest/RPE for his goal;
- his limitations and open injuries (his words), and what they rule out;
- the approved warmup, cooldown and core-finisher choices;
- what he did last time on this same day, which exercises stay (main lifts steady, about 60% of
  accessories stay) and how many slots are open for the model to fill;
- the suggested weight for each exercise he keeps (progression.py; never invented);
- which exercises his library already knows for today's muscles.

Later increments use this: the model only picks exercise NAMES; Python sets every number and uses
exclusion_reason() / pt_note_for() to throw out or flag what must not appear.

Run from the repo root to look at your own real facts (reads only):
    python -m agents.atlas.plan_facts            (uses your saved minutes)
    python -m agents.atlas.plan_facts 90         (one workout of 90 minutes)
"""
import re
from datetime import date
from typing import Any, Optional

from agents.atlas import exercise_library as library
from agents.atlas import programs
from agents.atlas import progression
from agents.atlas import training_profile as profiles
from agents.atlas.atlas_tools import load_fitness_data
from shared.keyword_gate import contains_keyword

OPEN_STATUSES = ("active", "recovering")      # an injury that is still open (same words atlas_logging uses)
VALID_SEVERITIES = ("mild", "moderate", "severe")
DEFAULT_UNIT = "lbs"
KEEP_ACCESSORY_SHARE = 0.6                    # about 60% of accessories stay the same from last time
MAX_INJURIES = 20
MAX_CANDIDATES = 60
MAX_LIBRARY_NAMES = 200
MAX_TEXT = 300

# Approved by Joey (Session 16). Nothing here loads the shoulder.
WARMUP_CHOICES = ["easy bike or walk (3-5 minutes)", "bodyweight squats", "glute bridges",
                  "hip circles", "leg swings", "cat-cow"]
COOLDOWN_CHOICES = ["hamstring stretch", "quad stretch", "hip flexor stretch", "calf stretch", "child's pose"]
CORE_CHOICES = ["plank", "side plank", "dead bug", "bird dog", "glute-bridge march", "crunches"]

# Names the plan never contains while a limitation mentions the biceps (see programs.limit_flags).
BICEPS_NAME_WORDS = ["curl", "curls"]
# Explosive moves: excluded unless Joey asks AND his physical therapist agrees (allow_explosive=True).
EXPLOSIVE_WORDS = ["jump", "jumps", "jumping", "clean", "cleans", "snatch", "snatches", "throw", "throws",
                   "slam", "slams", "burpee", "burpees", "plyo", "plyometric", "plyometrics",
                   "kettlebell swing", "kettlebell swings"]
# Allowed, but while a shoulder/biceps limitation is on file they carry the "check with your PT" line.
PT_CHECK_WORDS = ["row", "rows", "pulldown", "pulldowns", "pull down", "pull downs", "pull up", "pull ups",
                  "pullup", "pullups", "overhead", "military", "shoulder press", "face pull", "face pulls"]
_CHIN_RE = re.compile(r"\bchin\s?ups?\b")

# Words a library entry might use for each program muscle (a HINT for candidates only).
MUSCLE_WORDS = {
    "chest": ["chest", "pec", "pecs", "pectoral", "pectorals", "pectoralis"],
    "shoulders": ["shoulder", "shoulders", "deltoid", "deltoids", "delt", "delts"],
    "triceps": ["tricep", "triceps"],
    "back": ["back", "lat", "lats", "latissimus", "rhomboid", "rhomboids", "trap", "traps", "trapezius"],
    "biceps": ["bicep", "biceps"],
    "rear delts": ["rear delt", "rear delts", "rear deltoid", "rear deltoids", "posterior deltoid"],
    "forearms": ["forearm", "forearms"],
    "quads": ["quad", "quads", "quadriceps"],
    "hamstrings": ["hamstring", "hamstrings"],
    "glutes": ["glute", "glutes", "gluteus"],
    "calves": ["calf", "calves", "gastrocnemius", "soleus"],
}


# --------------------------------------------------------------
# SMALL SAFE HELPERS (Lesson #5: never trust the shape of a data file)
# --------------------------------------------------------------

def _clip(v, limit: int = MAX_TEXT) -> str:
    """Any value -> one clean line of at most `limit` characters ('' when it is not text)."""
    if not isinstance(v, str):
        return ""
    return " ".join("".join(c if (c.isprintable() or c.isspace()) else " " for c in v).split())[:limit]


def _plain(name) -> str:
    """Lower-case words separated by single spaces ('Chin-Ups' -> 'chin ups'), for matching."""
    return " ".join(re.sub(r"[^a-z0-9]+", " ", name.lower()).split()) if isinstance(name, str) else ""


def _list_of_dicts(v) -> list:
    return [x for x in v if isinstance(x, dict)] if isinstance(v, list) else []


def _valid_minutes(v) -> bool:
    return isinstance(v, int) and not isinstance(v, bool) and 15 <= v <= 180


# --------------------------------------------------------------
# WHAT MAY NOT APPEAR, AND WHAT GETS A NOTE (used by the validator in the next increment)
# --------------------------------------------------------------

def exclusion_reason(name, flags: Any = None, primary_muscles=None, allow_explosive: bool = False) -> str:
    """'' when the exercise may appear in a plan, else a plain-English reason it may not."""
    text = _plain(name)
    if not text:
        return "no name"
    raw_drop = flags.get("drop_muscles") if isinstance(flags, dict) else None
    drop: list = raw_drop if isinstance(raw_drop, list) else []
    if "biceps" in drop:
        if contains_keyword(text, BICEPS_NAME_WORDS) or _CHIN_RE.search(text):
            return "your limitations rule out direct biceps work (curls and chin-ups)"
        muscles = [m for m in primary_muscles if isinstance(m, str)] if isinstance(primary_muscles, list) else []
        if any(contains_keyword(m, MUSCLE_WORDS["biceps"]) for m in muscles):
            return "your limitations rule out direct biceps work"
    if not allow_explosive and contains_keyword(text, EXPLOSIVE_WORDS):
        return "explosive moves are off by default (only if you ask and your physical therapist agrees)"
    return ""


def pt_note_for(name, flags: Any = None) -> str:
    """The 'check with your physical therapist' line for this exercise, or '' when none applies."""
    note = flags.get("pt_note") if isinstance(flags, dict) else ""
    if not isinstance(note, str) or not note:
        return ""
    return note if contains_keyword(_plain(name), PT_CHECK_WORDS) else ""


def main_lift_count(slots: int) -> int:
    """How many of the day's exercises count as MAIN lifts (the rest are accessories): 1 up to 3 exercises, else 2."""
    return 1 if slots <= 3 else 2


# --------------------------------------------------------------
# PIECES OF THE FACTS
# --------------------------------------------------------------

def _open_injuries(injuries) -> list:
    out = []
    for inj in _list_of_dicts(injuries):
        if inj.get("status") not in OPEN_STATUSES:
            continue
        sev = inj.get("severity")
        out.append({"body_part": _clip(inj.get("body_part"), 60), "description": _clip(inj.get("description"), 150),
                    "severity": sev if sev in VALID_SEVERITIES else "unstated", "status": inj.get("status"),
                    "date_logged": _clip(inj.get("date_logged"), 40)})
        if len(out) >= MAX_INJURIES:
            break
    return out


def _is_core(name, section) -> bool:
    if _plain(name) in {_plain(c) for c in CORE_CHOICES}:
        return True
    return isinstance(section, str) and contains_keyword(section, programs.CORE_FINISHER)


def last_session_for(style: str, day_index: int, workouts) -> Optional[dict]:
    """The latest saved workout tagged with this program style and day -> {'date', 'exercises': [names in order]}."""
    best = None
    for w in _list_of_dicts(workouts):
        tag = w.get("program")
        tag_style = tag if isinstance(tag, str) and tag in programs.PROGRAMS else profiles.parse_program_style(tag)
        if tag_style != style or programs.find_day(style, w.get("program_day")) != day_index:
            continue
        key = (str(w.get("date") or ""), str(w.get("logged_at") or ""))
        if best is None or key > best[0]:
            best = (key, w)
    if best is None:
        return None
    names = []
    for e in best[1].get("exercises") if isinstance(best[1].get("exercises"), list) else []:
        name = e.get("name") if isinstance(e, dict) else e
        section = e.get("section") if isinstance(e, dict) else None
        clean = _clip(name, 100)
        if clean and not _is_core(clean, section) and _plain(clean) not in {_plain(n) for n in names}:
            names.append(clean)
    return {"date": str(best[1].get("date") or ""), "exercises": names}


def _library_entry_for(name, entries: list) -> Optional[dict]:
    key = library.normalize_name(name)
    if not key:
        return None
    for e in entries:
        names = {library.normalize_name(e.get("name"))}
        if isinstance(e.get("aliases"), list):
            names |= {library.normalize_name(a) for a in e["aliases"]}
        if key in names:
            return e
    return None


def _candidates(entries: list, focus: list, flags: dict) -> list:
    out = []
    for e in entries:
        muscles = [m for m in e.get("primary_muscles", []) if isinstance(m, str)] if isinstance(e.get("primary_muscles"), list) else []
        hit = any(contains_keyword(m, MUSCLE_WORDS[f]) for m in muscles for f in focus if f in MUSCLE_WORDS)
        name = _clip(e.get("name"), 100)
        if not (hit and name) or exclusion_reason(name, flags, muscles):
            continue
        out.append({"name": name, "status": _clip(e.get("status"), 20), "primary_muscles": [_clip(m, 40) for m in muscles][:6],
                    "equipment": [_clip(q, 40) for q in e["equipment"] if isinstance(q, str)][:6] if isinstance(e.get("equipment"), list) else []})
        if len(out) >= MAX_CANDIDATES:
            break
    return out


def _variety(slots: int, previous: Optional[dict], entries: list, flags: dict) -> dict:
    """Which of last time's exercises stay (main lifts steady, about 60% of accessories) and how many slots stay open."""
    main_slots = min(main_lift_count(slots), slots)
    acc_slots = slots - main_slots
    result: dict[str, Any] = {"slots": slots, "main_slots": main_slots, "accessory_slots": acc_slots,
                              "previous_date": None, "keep_main": [], "keep_accessories": [], "dropped": [], "open_slots": slots}
    if previous is None:
        return result
    result["previous_date"] = previous["date"]
    allowed = []
    for name in previous["exercises"]:
        entry = _library_entry_for(name, entries)
        why = exclusion_reason(name, flags, entry.get("primary_muscles") if entry else None)
        if why:
            result["dropped"].append({"name": name, "reason": why})
        else:
            allowed.append(name)
    prev_main, prev_acc = allowed[:main_slots], allowed[main_slots:main_slots + acc_slots]
    keep = min(len(prev_acc), int(KEEP_ACCESSORY_SHARE * acc_slots + 0.5))
    result["keep_main"] = prev_main
    result["keep_accessories"] = prev_acc[:keep]
    result["open_slots"] = slots - len(prev_main) - keep
    return result


# --------------------------------------------------------------
# THE FACTS
# --------------------------------------------------------------

def build_facts(profile, workouts, injuries, library_entries, minutes_override=None, today: Optional[str] = None) -> dict:
    """Everything the plan builder needs, from data handed in (no files read). {'ok': False, 'problem'} with no usable profile."""
    if minutes_override is not None and not _valid_minutes(minutes_override):
        raise ValueError("minutes must be a whole number from 15 to 180")
    if not isinstance(profile, dict):
        return {"ok": False, "problem": "no training profile yet: type 'atlas setup' first"}
    prof = profiles.normalize_profile(profile)
    entries = _list_of_dicts(library_entries)
    notes = [] if prof["setup_complete"] else ["your setup interview was not finished, so some answers may be missing"]

    if minutes_override is not None:
        minutes, source = minutes_override, "this request"
    elif prof["session_minutes"] is not None:
        minutes, source = prof["session_minutes"], "your profile"
    else:
        minutes, source = programs.DEFAULT_MINUTES, "the default (no minutes saved in your profile)"
    shape = programs.session_shape(minutes)

    style, style_reason = programs.resolve_style(prof)
    rotation = programs.rotation_state(style, workouts, prof["next_day"])
    flags = programs.limit_flags(prof)
    focus = programs.focus_for(rotation["next"]["focus"], prof)
    goal_type = profiles.goal_priority(prof)[0]
    previous = last_session_for(style, rotation["next_index"], workouts)
    variety = _variety(shape["main"], previous, entries, flags)
    keep = variety["keep_main"] + variety["keep_accessories"]

    return {
        "ok": True, "notes": notes, "today": today if isinstance(today, str) and today else date.today().isoformat(),
        "unit": DEFAULT_UNIT, "minutes": minutes, "minutes_source": source, "shape": shape,
        "goal_type": goal_type, "goal_order": profiles.goal_priority(prof), "goal_params": programs.goal_params(goal_type),
        "style": style, "style_label": programs.PROGRAMS[style]["label"], "style_reason": style_reason,
        "day": {"label": rotation["next"]["label"], "index": rotation["next_index"], "focus": focus,
                "reason": rotation["reason"], "last_tagged": rotation["last"]},
        "limits": flags, "limitations": list(prof["limitations"]), "open_injuries": _open_injuries(injuries),
        "profile_text": {k: prof[k] for k in ("goal", "experience", "equipment", "activity", "preferences") if prof[k]},
        "warmups": [w for w in WARMUP_CHOICES if _plain(w) not in {_plain(a) for a in flags["avoid_warmups"]}],
        "cooldowns": list(COOLDOWN_CHOICES), "core_choices": list(CORE_CHOICES),
        "core_finisher": shape["core_finisher"],
        "previous": previous, "variety": variety,
        "weights": progression.suggest_for(keep, workouts, entries) if keep else {},
        "library_candidates": _candidates(entries, focus, flags),
        "library_names": [_clip(e.get("name"), 100) for e in entries if _clip(e.get("name"), 100)][:MAX_LIBRARY_NAMES],
    }


def gather_facts(minutes_override=None, today: Optional[str] = None) -> dict:
    """build_facts() on Joey's real saved data. READS only. A damaged data file raises RuntimeError (never ignored)."""
    data = load_fitness_data()
    return build_facts(profiles.load_profile(), data.get("workouts"), data.get("injuries"),
                       library.list_entries(), minutes_override, today)


def describe_facts(facts) -> str:
    """The facts as plain readable lines (for checking them by eye)."""
    if not isinstance(facts, dict) or not facts.get("ok"):
        return str(facts.get("problem")) if isinstance(facts, dict) and facts.get("problem") else "no facts"
    v, d, shape = facts["variety"], facts["day"], facts["shape"]
    gp = facts["goal_params"]
    lines = [
        f"Next: {d['label']} ({facts['style_label']}; {d['reason']})",
        f"Muscles today: {', '.join(d['focus']) or 'none'}",
        f"Goal: {facts['goal_type']}: {gp['sets'][0]}-{gp['sets'][1]} sets, {gp['reps'][0]}-{gp['reps'][1]} reps, "
        f"rest {gp['rest_seconds'][0]}-{gp['rest_seconds'][1]} s, RPE {gp['rpe_main']} main / {gp['rpe_accessory']} accessory",
        f"Time: {facts['minutes']} min ({facts['minutes_source']}): {shape['main']} exercises, {shape['warmup']} warmup, "
        f"{shape['cooldown']} cooldown, core finisher {'yes' if facts['core_finisher'] else 'no'}",
        f"Limitations: {'; '.join(facts['limitations']) or 'none'}",
        "Open injuries: " + ("; ".join(f"{i['description'] or i['body_part']} ({i['severity']}, {i['status']})" for i in facts["open_injuries"]) or "none"),
        f"Dropped by your limitations: {', '.join(facts['limits']['drop_muscles']) or 'nothing'}",
        f"Warmups allowed: {', '.join(facts['warmups'])}",
        f"Last time on this day: {v['previous_date'] or 'never done'}",
        f"Keeping (main): {', '.join(v['keep_main']) or 'none'}",
        f"Keeping (accessories): {', '.join(v['keep_accessories']) or 'none'}",
        f"Open slots for new picks: {v['open_slots']}",
    ]
    lines += [f"Left out: {x['name']} - {x['reason']}" for x in v["dropped"]]
    lines += [f"Weight {n}: {s['reason']}" for n, s in facts["weights"].items()]
    lines.append(f"Library exercises that fit today: {len(facts['library_candidates'])}")
    lines += [f"Note: {n}" for n in facts["notes"]]
    return "\n".join(lines)


if __name__ == "__main__":
    import sys
    minutes = None
    if len(sys.argv) > 1:
        try:
            minutes = int(sys.argv[1])
        except ValueError:
            raise SystemExit("minutes must be a whole number, for example: python -m agents.atlas.plan_facts 90")
    print(describe_facts(gather_facts(minutes)))