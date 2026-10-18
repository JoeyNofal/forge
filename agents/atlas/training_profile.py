"""
TRAINING PROFILE (ATLAS setup, increment 3a-i) - the store.

One locked JSON file holding what a trainer would want to know about Joey: goal,
experience, days and minutes available, equipment, limitations, preferences, the
program style he wants. ATLAS reads it when it builds programs and plans (3b-3d).

RULES
- NO model and NO network code here. The profile holds JOEY'S OWN WORDS (cleaned to one
  line and length-limited); nothing a model says is ever written into it.
- The only thing Python works out is what can be worked out safely: a goal TYPE from his
  goal words (strength / power / muscle / fat_loss / endurance / general, shown to him and changeable),
  and numbers (days 1-7, minutes 15-180).
- Every write is one locked read-modify-write (Lesson #4). A damaged or wrong-shaped file
  fails loudly and is never overwritten (Lesson #5). The file lives in the data folder
  (kept out of git): it contains health details.
"""
import json
import os
import re
import time
from datetime import datetime
from typing import Any

from shared.file_store import load_json, update_json
from shared.normalizers import require_dict

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_PROFILE_PATH = os.path.join(_REPO_ROOT, "data", "training_profile.json")

PROFILE_VERSION = 1
GOAL_TYPES = ("strength", "power", "muscle", "fat_loss", "endurance", "general")
PROGRAM_STYLES = ("ppl", "upper_lower", "full_body", "bro_split", "auto")
STYLE_LABELS = {
    "ppl": "push / pull / legs",
    "upper_lower": "upper / lower",
    "full_body": "full body",
    "bro_split": "bro split (chest, back, shoulders, arms, legs)",
    "auto": "you decide",
}
GOAL_TYPE_LABELS = {"strength": "strength", "power": "power", "muscle": "build muscle", "fat_loss": "fat loss",
                    "endurance": "endurance", "general": "general fitness"}

# Free-text fields and their length limits.
TEXT_FIELDS = {"goal": 500, "experience": 500, "consistency": 500, "equipment": 500,
               "activity": 500, "preferences": 500, "body": 200, "notes": 500}
FIELD_LABELS = {
    "goal": "goal", "experience": "experience", "consistency": "recent consistency", "equipment": "equipment",
    "activity": "other activity", "preferences": "likes and dislikes", "body": "body numbers", "notes": "notes",
    "goal_type": "goal type", "days_per_week": "days per week", "session_minutes": "minutes per session",
    "program_style": "program style", "add_limitation": "limitations", "clear_limitations": "limitations",
    "next_day": "next program day", "goal_order": "goal order",
}
MAX_DAY_LABEL = 40
UPDATABLE_FIELDS = tuple(FIELD_LABELS)
MAX_LIMITATIONS = 20
MAX_LIMITATION = 300
MAX_GOAL_HISTORY = 50


def get_profile_path() -> str:
    """Read at call time (not import time) so tests and .env changes work."""
    return os.path.abspath(os.getenv("TRAINING_PROFILE_PATH") or DEFAULT_PROFILE_PATH)


# --------------------------------------------------------------
# CLEANING
# --------------------------------------------------------------

def _squash(v: str) -> str:
    """One clean line: every kind of whitespace becomes one space, other control characters are dropped."""
    return " ".join("".join(ch if ch.isprintable() else (" " if ch.isspace() else "") for ch in v).split())


def _text(v, limit: int) -> str:
    """One clean line, length-limited. Non-text gives ''. Nothing is invented."""
    if not isinstance(v, str):
        return ""
    return _squash(v)[:limit].strip()


def _whole(v, low: int, high: int):
    """A whole number in [low, high], else None. Booleans, junk and out-of-range values give None."""
    if isinstance(v, bool):
        return None
    if isinstance(v, str):
        v = v.strip()
        if not re.fullmatch(r"\d{1,6}", v):
            return None
        v = int(v)
    if isinstance(v, float):
        if v != v or v in (float("inf"), float("-inf")) or v != int(v):
            return None
        v = int(v)
    if not isinstance(v, int) or not low <= v <= high:
        return None
    return v


def _clean_limitations(v) -> list:
    if isinstance(v, str):
        v = re.split(r"\n|;", v)
    if not isinstance(v, list):
        return []
    out, seen = [], set()
    for x in v[:MAX_LIMITATIONS * 4]:
        s = _text(x, MAX_LIMITATION)
        if s and s.lower() not in seen:
            seen.add(s.lower())
            out.append(s)
        if len(out) >= MAX_LIMITATIONS:
            break
    return out


_GOAL_PATTERNS = {
    "strength": r"\b(?:strength|stronger|strong|powerlifting|1rm)\b",
    "power": r"\b(?:power|explosive|explosiveness|plyometric|plyometrics)\b",
    "muscle": r"\b(?:muscle|muscles|hypertrophy|bulk|bulking|mass|size|bigger)\b",
    "fat_loss": r"\b(?:fat|lose weight|weight loss|cut|cutting|lean|leaner|slim|shred)\b",
    "endurance": r"\b(?:endurance|cardio|swim|swimming|marathon|stamina|conditioning|running|triathlon)\b",
}


def derive_goal_type(text) -> str:
    """The goal type from the EARLIEST goal word in his text (whole words only), else 'general'."""
    if not isinstance(text, str):
        return "general"
    best = None
    for name, pattern in _GOAL_PATTERNS.items():
        m = re.search(pattern, text[:1000], re.IGNORECASE)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else "general"


def parse_goal_type(text):
    """'fat loss' / 'Fat-Loss' / 'muscle' -> a goal type, else None."""
    if not isinstance(text, str):
        return None
    key = re.sub(r"[\s\-]+", "_", text.strip().lower())
    return key if key in GOAL_TYPES else None


_STYLE_PATTERNS = [
    ("ppl", r"\b(?:ppl|push[\s/,_-]*pull[\s/,_-]*legs?)\b"),
    ("upper_lower", r"\bupper[\s/,_-]*(?:and\s+)?lower\b"),
    ("full_body", r"\bfull[\s_-]*body\b"),
    ("bro_split", r"\b(?:bro[\s_-]*split|body[\s_-]*part[\s_-]*split|bro)\b"),
    ("auto", r"\b(?:auto|decide|you choose|any|whatever|no preference|not sure|dont know|don't know)\b"),
]


def parse_program_style(text):
    """A program style from his words (earliest match wins), else None (so the caller can ask again)."""
    if not isinstance(text, str):
        return None
    best = None
    for name, pattern in _STYLE_PATTERNS:
        m = re.search(pattern, text[:300], re.IGNORECASE)
        if m and (best is None or m.start() < best[0]):
            best = (m.start(), name)
    return best[1] if best else None


def parse_goal_order(text) -> list:
    """
    'power, strength, muscle' / 'power then strength > endurance' -> ['power', 'strength', ...], or ValueError.
    Items are split on commas, 'then', 'and', '>', '->' and ';'. Every item must be a goal I know, listed once.
    """
    if not isinstance(text, str) or not text.strip():
        raise ValueError("profile: a goal order needs goals, for example: power, strength, muscle, endurance, fat loss")
    pieces = [p.strip() for p in re.split(r",|;|->|>|\u2192|\bthen\b|\band\b", text[:300], flags=re.IGNORECASE) if p.strip()]
    order: list = []
    for piece in pieces:
        goal = parse_goal_type(piece)
        if goal is None:
            raise ValueError(f"profile: '{piece[:30]}' is not a goal I know (strength, power, muscle, fat loss, endurance, general)")
        if goal in order:
            raise ValueError(f"profile: {GOAL_TYPE_LABELS[goal]} is listed twice in the goal order")
        order.append(goal)
    if not order:
        raise ValueError("profile: a goal order needs goals, for example: power, strength, muscle, endurance, fat loss")
    return order


def _clean_goal_order(v) -> list:
    """A saved goal order made safe: only known goals, each once, in order. Anything else gives []."""
    if not isinstance(v, list):
        return []
    out: list = []
    for item in v:
        goal = parse_goal_type(item) if isinstance(item, str) else None
        if goal and goal not in out:
            out.append(goal)
    return out


def _clean_goal_history(v) -> list:
    """[{'goal_type', 'started', 'ended'}], newest last, at most MAX_GOAL_HISTORY, junk dropped."""
    if not isinstance(v, list):
        return []
    out = []
    for item in v:
        if not isinstance(item, dict):
            continue
        goal = parse_goal_type(item.get("goal_type")) if isinstance(item.get("goal_type"), str) else None
        started = _text(item.get("started"), 10)
        if goal and started:
            out.append({"goal_type": goal, "started": started, "ended": _text(item.get("ended"), 10) or None})
    return out[-MAX_GOAL_HISTORY:]


def track_goal(profile: dict, today: str) -> None:
    """Keeps the record of when each goal started: closes the open entry and opens a new one when the goal changed."""
    history = _clean_goal_history(profile.get("goal_history"))
    last = history[-1] if history else None
    if last is None or last["ended"] is not None or last["goal_type"] != profile.get("goal_type"):
        if last is not None and last["ended"] is None:
            last["ended"] = today
        history.append({"goal_type": profile.get("goal_type"), "started": today, "ended": None})
    profile["goal_history"] = history[-MAX_GOAL_HISTORY:]


def goal_priority(profile) -> list:
    """The goals in his order, first = the one training follows now. Never empty for a real profile."""
    p = normalize_profile(profile) if isinstance(profile, dict) else normalize_profile({})
    return p["goal_order"] or [p["goal_type"]]


def _clean_next_day(v):
    """{'day', 'set_at'} when Joey set the next program day by hand, else None."""
    if not isinstance(v, dict):
        return None
    day = _text(v.get("day"), MAX_DAY_LABEL)
    return {"day": day, "set_at": _text(v.get("set_at"), 40)} if day else None


# --------------------------------------------------------------
# THE PROFILE SHAPE
# --------------------------------------------------------------

def normalize_profile(raw) -> dict:
    """Any dict -> a clean profile. Unknown keys are dropped; missing things are '' / None / []."""
    require_dict(raw, "profile")
    out: dict[str, Any] = {"version": PROFILE_VERSION}
    for key, limit in TEXT_FIELDS.items():
        out[key] = _text(raw.get(key), limit)
    goal_type = parse_goal_type(raw.get("goal_type"))
    out["goal_type"] = goal_type or derive_goal_type(out["goal"])
    out["goal_order"] = _clean_goal_order(raw.get("goal_order"))
    if out["goal_order"]:
        out["goal_type"] = out["goal_order"][0]               # with an order, the first goal IS the goal type
    out["goal_history"] = _clean_goal_history(raw.get("goal_history"))
    out["days_per_week"] = _whole(raw.get("days_per_week"), 1, 7)
    out["session_minutes"] = _whole(raw.get("session_minutes"), 15, 180)
    out["limitations"] = _clean_limitations(raw.get("limitations"))
    style = raw.get("program_style")
    out["program_style"] = style if style in PROGRAM_STYLES else (parse_program_style(style) or "auto")
    out["next_day"] = _clean_next_day(raw.get("next_day"))
    out["setup_complete"] = raw.get("setup_complete") is True
    for stamp in ("created_at", "updated_at"):
        out[stamp] = _text(raw.get(stamp), 40) or None
    return out


def clean_update(field, value) -> dict:
    """
    One change -> {"field", "value"} with the value cleaned, or ValueError. Used when a change is
    PROPOSED and again when it is approved. A stated value that is not usable is refused, never guessed.
    """
    if field not in UPDATABLE_FIELDS:
        raise ValueError(f"profile: '{str(field)[:30]}' is not something I can change")
    if field == "clear_limitations":
        return {"field": field, "value": None}
    if field in TEXT_FIELDS:
        text = _text(value, TEXT_FIELDS[field])
        if not text:
            raise ValueError(f"profile: {FIELD_LABELS[field]} needs some text")
        return {"field": field, "value": text}
    if field == "add_limitation":
        text = _text(value, MAX_LIMITATION)
        if not text:
            raise ValueError("profile: a limitation needs some text")
        return {"field": field, "value": text}
    if field == "next_day":
        text = _text(value, MAX_DAY_LABEL)
        if not text:
            raise ValueError("profile: the next program day needs a name")
        return {"field": field, "value": text}
    if field == "goal_order":
        return {"field": field, "value": parse_goal_order(value) if not isinstance(value, list) else parse_goal_order(", ".join(str(v) for v in value))}
    if field == "goal_type":
        goal_type = parse_goal_type(value)
        if goal_type is None:
            raise ValueError("profile: goal type must be strength, power, muscle, fat loss, endurance or general")
        return {"field": field, "value": goal_type}
    if field == "days_per_week":
        days = _whole(value, 1, 7)
        if days is None:
            raise ValueError("profile: days per week must be a whole number from 1 to 7")
        return {"field": field, "value": days}
    if field == "session_minutes":
        minutes = _whole(value, 15, 180)
        if minutes is None:
            raise ValueError("profile: minutes per session must be a whole number from 15 to 180")
        return {"field": field, "value": minutes}
    style = value if value in PROGRAM_STYLES else parse_program_style(value)     # field == "program_style"
    if style is None:
        raise ValueError("profile: program style must be push/pull/legs, upper/lower, full body, bro split or 'you decide'")
    return {"field": field, "value": style}


def format_profile(profile) -> str:
    """The profile as plain text (what Joey reads before approving, and for 'show profile')."""
    if not isinstance(profile, dict):
        raise ValueError("profile must be a dict")
    p = normalize_profile(profile)

    def given(v):
        return v if v not in ("", None) else "(not given)"

    lines = ["Training profile (" + ("setup complete" if p["setup_complete"] else "setup not finished") + "):",
             f"Goal: {given(p['goal'])} (type: {GOAL_TYPE_LABELS[p['goal_type']]})"]
    if p["goal_order"]:
        lines.append("Goal order: " + " > ".join(GOAL_TYPE_LABELS[g] for g in p["goal_order"]))
    current = p["goal_history"][-1] if p["goal_history"] and p["goal_history"][-1]["ended"] is None else None
    if current:
        lines.append(f"Current goal ({GOAL_TYPE_LABELS[current['goal_type']]}) since {current['started']}")
    lines += [
             f"Experience: {given(p['experience'])}",
             f"Recent consistency: {given(p['consistency'])}",
             f"Days per week: {given(p['days_per_week'])}   Minutes per session: {given(p['session_minutes'])}",
             f"Equipment: {given(p['equipment'])}"]
    if p["limitations"]:
        lines.append("Limitations:")
        lines += [f"  {i}. {s}" for i, s in enumerate(p["limitations"], 1)]
    else:
        lines.append("Limitations: none noted")
    lines += [f"Other activity: {given(p['activity'])}",
              f"Likes and dislikes: {given(p['preferences'])}",
              f"Program style: {STYLE_LABELS[p['program_style']]}"
              + (f" (next day set by hand: {p['next_day']['day']})" if p["next_day"] else ""),
              f"Body numbers: {given(p['body'])}",
              f"Notes: {given(p['notes'])}"]
    return "\n".join(lines)


# --------------------------------------------------------------
# READING (never writes, never creates the file)
# --------------------------------------------------------------

def _load_data() -> dict:
    path = get_profile_path()
    data = None
    for attempt in (1, 2):                            # a reader can catch a write in progress: one quick retry
        try:
            data = load_json(path, {})
            break
        except json.JSONDecodeError as e:
            if attempt == 2:
                raise RuntimeError(f"training profile file is damaged ({e.msg}): {path}") from e
            time.sleep(0.05)
    if not isinstance(data, dict):
        raise RuntimeError("training profile file has the wrong shape (expected an object)")
    return data


def load_profile():
    """The clean profile, or None when there is none yet. Damaged or wrong shape = RuntimeError."""
    profile = _load_data().get("profile")
    if profile is None:
        return None
    if not isinstance(profile, dict):
        raise RuntimeError("training profile file: 'profile' is not an object")
    return normalize_profile(profile)


# --------------------------------------------------------------
# WRITING (each one a single locked read-modify-write)
# --------------------------------------------------------------

def _check_shape(data) -> None:
    if not isinstance(data, dict):
        raise RuntimeError("training profile file has the wrong shape (expected an object)")
    if data.get("profile") is not None and not isinstance(data["profile"], dict):
        raise RuntimeError("training profile file: 'profile' is not an object - refusing to overwrite it")


def save_profile(clean) -> tuple:
    """Saves a whole profile (the end of setup), replacing any earlier one. Returns (ok, message)."""
    profile = normalize_profile(clean)
    now = datetime.now().isoformat()
    result = {"msg": ""}

    def _modify(data):
        _check_shape(data)
        old = data.get("profile") if isinstance(data.get("profile"), dict) else {}
        profile["created_at"] = _text(old.get("created_at"), 40) or now
        profile["updated_at"] = now
        kept = _clean_goal_order(old.get("goal_order"))
        if kept and not profile["goal_order"]:                  # redoing setup never throws away an order he chose
            profile["goal_order"] = kept
            profile["goal_type"] = kept[0]
        if not profile["goal_history"]:
            profile["goal_history"] = _clean_goal_history(old.get("goal_history"))
        track_goal(profile, now[:10])
        data["profile"] = profile
        result["msg"] = "Training profile saved." + (f" (Your goal order was kept: {' > '.join(GOAL_TYPE_LABELS[g] for g in kept)}.)" if kept else "")
        return data

    update_json(get_profile_path(), _modify, {})
    return True, result["msg"]


def update_field(field, value) -> tuple:
    """Changes ONE thing in the profile (creating a not-finished profile if there is none). Returns (ok, message)."""
    change = clean_update(field, value)
    field, value = change["field"], change["value"]
    now = datetime.now().isoformat()
    result = {"ok": False, "msg": ""}

    def _modify(data):
        _check_shape(data)
        profile = normalize_profile(data["profile"]) if isinstance(data.get("profile"), dict) else normalize_profile({})
        profile["created_at"] = profile["created_at"] or now
        if field == "clear_limitations":
            profile["limitations"] = []
            shown = "cleared"
        elif field == "add_limitation":
            if value.lower() in [s.lower() for s in profile["limitations"]]:
                result["msg"] = "That limitation is already in your profile - nothing changed."
                return data
            if len(profile["limitations"]) >= MAX_LIMITATIONS:
                result["msg"] = f"Your profile already has {MAX_LIMITATIONS} limitations - nothing changed."
                return data
            profile["limitations"].append(value)
            shown = f"added '{value}'"
        elif field == "next_day":
            profile["next_day"] = {"day": value, "set_at": now}
            shown = value
        elif field == "goal_order":
            profile["goal_order"] = list(value)
            profile["goal_type"] = value[0]
            track_goal(profile, now[:10])
            shown = " > ".join(GOAL_TYPE_LABELS[g] for g in value)
        else:
            profile[field] = value
            shown = STYLE_LABELS[value] if field == "program_style" else GOAL_TYPE_LABELS[value] if field == "goal_type" else str(value)
            if field == "goal_type":
                if profile["goal_order"]:                      # with an order, the chosen goal moves to the front
                    profile["goal_order"] = [value] + [g for g in profile["goal_order"] if g != value]
                    shown += " (goal order now: " + " > ".join(GOAL_TYPE_LABELS[g] for g in profile["goal_order"]) + ")"
                track_goal(profile, now[:10])
            if field == "goal" and not profile["goal_order"]:       # with an order, the goal words are just words
                profile["goal_type"] = derive_goal_type(value)
                track_goal(profile, now[:10])
                shown += f" (goal type: {GOAL_TYPE_LABELS[profile['goal_type']]})"
        profile["updated_at"] = now
        data["profile"] = profile
        result["ok"] = True
        result["msg"] = f"Profile updated: {FIELD_LABELS[field]} -> {shown}."
        return data

    update_json(get_profile_path(), _modify, {})
    return result["ok"], result["msg"]