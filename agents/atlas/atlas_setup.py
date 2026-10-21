"""
ATLAS SETUP (increment 3a-ii) - the first-time interview, and the commands that change the
training profile later.

HOW IT WORKS
- Python runs the interview: a FIXED list of questions, asked one per message, in order. No model
  is involved, so no question is skipped or reworded and your answers are saved in YOUR words.
- Progress lives in a small state file (data/atlas_setup_state.json), so the interview survives
  restarts. An interview untouched for STALE_HOURS stops capturing your messages (type
  'continue setup' to pick it up again), so an abandoned setup can never swallow normal chat.
- At the end ATLAS shows the whole profile as a PROPOSAL. Nothing is saved until you approve it.
- Changing something later ('set goal ...', 'set days 4', 'add limitation ...') is also a proposal.
- A message counts as a command ONLY when the WHOLE message is the command (Lesson #6).
"""
import json
import os
import re
from datetime import datetime, timedelta
from typing import Any, Optional

from filelock import FileLock

from agents.atlas import atlas_actions
from agents.atlas import training_profile as profiles
from shared.file_store import update_json

_REPO_ROOT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
DEFAULT_STATE_PATH = os.path.join(_REPO_ROOT, "data", "atlas_setup_state.json")
STALE_HOURS = 12

# (key, kind, question). Every question can be skipped.
QUESTIONS = [
    ("goal", "text", "What's your main goal? For example build muscle, get stronger, lose fat, swim faster or general "
                     "fitness. Add any target or timeframe."),
    ("experience", "text", "How long have you been training, and which lifts are you comfortable with?"),
    ("consistency", "text", "How consistent have you been over the last 3 months?"),
    ("days_per_week", "days", "How many days a week can you train?"),
    ("session_minutes", "minutes", "How many minutes can you give each session?"),
    ("equipment", "text", "What equipment do you have access to? (Full gym, home setup, anything missing?)"),
    ("limitations", "limitations", "Any injuries, pain or limitations a trainer should know about, including anything a "
                                   "doctor restricted? (Type 'none' if there is nothing.)"),
    ("activity", "text", "What other activity do you do (swimming, sports) and how much?"),
    ("preferences", "text", "Which exercises do you love, and which do you want to avoid?"),
    ("program_style", "style", "Which program style do you prefer? Push/pull/legs, upper/lower, full body, bro split, "
                               "or 'you decide'."),
    ("body", "text", "Optional: your age, height and weight."),
    ("notes", "text", "Anything else a trainer should know?"),
]
TOTAL = len(QUESTIONS)

_NONE_WORDS = {"none", "no", "nope", "nothing", "n/a", "na", "no limitations", "none at all", "nothing really"}
_NUMBER_WORDS = {"once": 1, "one": 1, "twice": 2, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7}
_CONTROL_HINT = "(type 'skip' to pass, 'back' to go back, or 'cancel setup' to stop)"


def _now() -> datetime:
    return datetime.now()


def get_state_path() -> str:
    """Read at call time (not import time) so tests and .env changes work."""
    return os.path.abspath(os.getenv("ATLAS_SETUP_STATE_PATH") or DEFAULT_STATE_PATH)


# --------------------------------------------------------------
# WORDS TO NUMBERS
# --------------------------------------------------------------

def parse_days(text) -> Optional[int]:
    """'4', '4 days', '3-4' (first number), 'twice a week' -> 1..7, else None."""
    if not isinstance(text, str):
        return None
    m = re.search(r"\d+", text[:200])
    if m:
        n = int(m.group())
        return n if 1 <= n <= 7 else None
    m = re.search(r"\b(once|one|twice|two|three|four|five|six|seven)\b", text[:200], re.IGNORECASE)
    return _NUMBER_WORDS[m.group(1).lower()] if m else None


def parse_minutes(text) -> Optional[int]:
    """'45', '90 minutes', '1.5 hours', 'an hour', 'half an hour' -> 15..180, else None."""
    if not isinstance(text, str):
        return None
    t = text[:200].lower()
    if re.search(r"\bhalf\s+(?:an?\s+)?hour\b", t):
        return 30
    m = re.search(r"\d+(?:\.\d+)?", t)
    if m:
        n = float(m.group())
        if re.search(r"\b(?:hours?|hrs?)\b", t):
            n *= 60
    elif re.search(r"\b(?:an?|one)\s+hour\b", t):
        n = 60.0
    else:
        return None
    n = int(round(n))
    return n if 15 <= n <= 180 else None


# --------------------------------------------------------------
# COMMANDS (whole message only)
# --------------------------------------------------------------

_I = re.IGNORECASE
_COMMANDS = [
    ("start", re.compile(r"^\s*(?:atlas\s+setup|redo\s+setup|start\s+setup)\s*[.!]?\s*$", _I)),
    ("cancel", re.compile(r"^\s*cancel\s+setup\s*[.!]?\s*$", _I)),
    ("continue", re.compile(r"^\s*(?:continue|resume)\s+setup\s*[.!]?\s*$", _I)),
    ("show", re.compile(r"^\s*(?:(?:show|view|see)\s+(?:my\s+)?(?:training\s+)?profile|my\s+profile)\s*[?.!]?\s*$", _I)),
    ("clear_limitations", re.compile(r"^\s*clear\s+limitations\s*[.!]?\s*$", _I)),
    ("add_limitation", re.compile(r"^\s*add\s+limitation\s+(\S.{0,299}?)\s*[.!]?\s*$", _I)),
    ("goal_type", re.compile(r"^\s*set\s+goal\s+type\s+(\S.{0,40}?)\s*[.!]?\s*$", _I)),
    ("goal_order", re.compile(r"^\s*set\s+goal\s+order\s+(\S.{0,150}?)\s*[.!]?\s*$", _I)),          # before the generic 'set goal ...'
    ("days_per_week", re.compile(r"^\s*set\s+days(?:\s+per\s+week)?\s+(\d)\s*[.!]?\s*$", _I)),
    ("session_minutes", re.compile(r"^\s*set\s+minutes(?:\s+per\s+session)?\s+(\d{2,3})\s*[.!]?\s*$", _I)),
    ("program_style", re.compile(r"^\s*set\s+program(?:\s+style)?\s+(\S.{0,60}?)\s*[.!]?\s*$", _I)),
    ("text", re.compile(r"^\s*set\s+(goal|experience|consistency|equipment|activity|preferences|notes|body)\s+"
                        r"(\S.{0,499}?)\s*[.!]?\s*$", _I)),
]
# A command that no pattern above accepted because it is too long (or has line breaks) must be ANSWERED, not
# silently sent to the chat model (found for real: a 348-character 'add limitation' was just chatted about).
_TOO_LONG_RE = re.compile(r"^\s*(add\s+limitation|set\s+(?:goal|experience|consistency|equipment|activity|preferences|notes|body))\s+(\S[\s\S]*)$", _I)
_SKIP_RE = re.compile(r"^\s*skip\s*[.!]?\s*$", _I)
_BACK_RE = re.compile(r"^\s*back\s*[.!]?\s*$", _I)


def match_command(message):
    """(kind, value-or-None) when the WHOLE message is a setup/profile command, else None. Non-text fails loudly."""
    for kind, pattern in _COMMANDS:
        m = pattern.match(message)
        if m:
            if kind == "text":
                return "text", (m.group(1).lower(), m.group(2))
            return kind, (m.group(1) if m.lastindex else None)
    m = _TOO_LONG_RE.match(message)
    if m:
        which = " ".join(m.group(1).lower().split())
        return "too_long", (which, len(" ".join(m.group(2).split())), 300 if which == "add limitation" else 500)
    return None


# --------------------------------------------------------------
# THE STATE FILE
# --------------------------------------------------------------

def _valid_state(data) -> Optional[dict]:
    """The state when it is a usable in-progress interview, else None (hand-edited junk never crashes anything)."""
    if not isinstance(data, dict) or data.get("status") != "in_progress":
        return None
    index = data.get("index")
    if isinstance(index, bool) or not isinstance(index, int) or not 0 <= index < TOTAL:
        return None
    return {
        "status": "in_progress",
        "index": index,
        "answers": data["answers"] if isinstance(data.get("answers"), dict) else {},
        "skipped": [k for k in data["skipped"] if isinstance(k, str)] if isinstance(data.get("skipped"), list) else [],
        "started_at": data.get("started_at") if isinstance(data.get("started_at"), str) else "",
        "updated_at": data.get("updated_at") if isinstance(data.get("updated_at"), str) else "",
    }


def _is_stale(state: dict) -> bool:
    try:
        return _now() - datetime.fromisoformat(state["updated_at"]) > timedelta(hours=STALE_HOURS)
    except (ValueError, TypeError):
        return True


def _peek_state() -> Optional[dict]:
    """The in-progress interview, or None. A missing OR damaged file means 'no interview': normal chat must never break."""
    path = get_state_path()
    if not os.path.exists(path):
        return None
    try:
        with FileLock(path + ".lock", timeout=10):          # the writers' lock: never read a half-written file
            with open(path, encoding="utf-8") as f:
                return _valid_state(json.load(f))
    except (OSError, ValueError):
        return None


def _locked_update(modify):
    """One locked read-modify-write of the state file. A damaged file is a RuntimeError, never overwritten."""
    try:
        update_json(get_state_path(), modify, {"status": "idle"})
    except json.JSONDecodeError as e:
        raise RuntimeError(f"the setup state file is damaged ({e.msg}): {get_state_path()}") from e


def _prompt(index: int) -> str:
    return f"Setup question {index + 1} of {TOTAL}: {QUESTIONS[index][2]}\n{_CONTROL_HINT}"


def _approve_hint(action_id: str) -> str:
    short = action_id[:8]
    return f"\n\nReply 'approve {short}' to save it, or 'deny {short}' to throw it away."


# --------------------------------------------------------------
# THE INTERVIEW
# --------------------------------------------------------------

def _start() -> str:
    existing = profiles.load_profile()
    now = _now().isoformat()
    state = {"status": "in_progress", "index": 0, "answers": {}, "skipped": [], "started_at": now, "updated_at": now}

    def _modify(data):
        if not isinstance(data, dict):
            raise RuntimeError("the setup state file has the wrong shape (expected an object)")
        return state

    _locked_update(_modify)
    intro = (f"Let's set up your training profile. I'll ask {TOTAL} questions, one at a time, and keep your answers "
             "in your own words. Nothing is saved until you approve the summary at the end.")
    if existing is not None:
        intro += " You already have a profile; it stays as it is until you approve the new one."
    return intro + "\n\n" + _prompt(0)


def _cancel() -> str:
    result = {"was_active": False}

    def _modify(data):
        if not isinstance(data, dict):
            raise RuntimeError("the setup state file has the wrong shape (expected an object)")
        result["was_active"] = _valid_state(data) is not None
        return {"status": "idle"} if result["was_active"] else data

    if not os.path.exists(get_state_path()):
        return "There is no setup in progress."
    _locked_update(_modify)
    return "Setup cancelled. Nothing was saved." if result["was_active"] else "There is no setup in progress."


def _continue() -> str:
    result: dict[str, Any] = {"index": None}

    def _modify(data):
        if not isinstance(data, dict):
            raise RuntimeError("the setup state file has the wrong shape (expected an object)")
        state = _valid_state(data)
        if state is None:
            return data
        state["updated_at"] = _now().isoformat()
        result["index"] = state["index"]
        return state

    if not os.path.exists(get_state_path()):
        return "There is no setup in progress. Type 'atlas setup' to start one."
    _locked_update(_modify)
    if result["index"] is None:
        return "There is no setup in progress. Type 'atlas setup' to start one."
    return "Picking up where we left off.\n\n" + _prompt(result["index"])


def _parse_answer(kind: str, key: str, message: str):
    """(value, acknowledgement) for a good answer, or (None, reprompt text)."""
    if kind == "days":
        n = parse_days(message)
        return (n, f"Got it: {n} days a week.") if n else (None, "I need a number of days from 1 to 7 (for example 4), or type 'skip'.")
    if kind == "minutes":
        n = parse_minutes(message)
        return (n, f"Got it: {n} minutes a session.") if n else (None, "I need a session length between 15 and 180 minutes (for example 60 or 'an hour'), or type 'skip'.")
    if kind == "style":
        style = profiles.parse_program_style(message)
        if style is None:
            return None, "I didn't recognise that. Say push/pull/legs, upper/lower, full body, bro split, or 'you decide' (or type 'skip')."
        return style, f"Got it: {profiles.STYLE_LABELS[style]}."
    if kind == "limitations":
        cleaned = " ".join(message.split()).lower().strip(" .!")
        if cleaned in _NONE_WORDS:
            return [], "Got it: no limitations."
        items = profiles.normalize_profile({"limitations": message})["limitations"]
        return (items, "Got it.") if items else (None, "I need some text, or type 'none' or 'skip'.")
    try:
        return profiles.clean_update(key, message)["value"], "Got it."
    except ValueError:
        return None, "I need some text, or type 'skip'."


def _build_profile(answers: dict) -> dict:
    profile: dict[str, Any] = {k: answers.get(k) for k, _kind, _q in QUESTIONS}
    profile["setup_complete"] = True
    return profile


def _answer(message: str):
    """Treats the message as the answer to the current question. Returns text, or None when no interview is active."""
    result: dict[str, Any] = {"text": None, "finished": None}

    def _modify(data):
        if not isinstance(data, dict):
            raise RuntimeError("the setup state file has the wrong shape (expected an object)")
        state = _valid_state(data)
        if state is None or _is_stale(state):
            return data
        index = state["index"]
        key, kind, _q = QUESTIONS[index]
        if _BACK_RE.match(message):
            if index == 0:
                result["text"] = "You're already at the first question.\n\n" + _prompt(0)
                return data
            state["index"] = index - 1
            prev = QUESTIONS[index - 1][0]
            state["answers"].pop(prev, None)
            state["skipped"] = [k for k in state["skipped"] if k != prev]
            ack = "Going back."
        elif _SKIP_RE.match(message):
            state["answers"].pop(key, None)
            if key not in state["skipped"]:
                state["skipped"].append(key)
            state["index"] = index + 1
            ack = "Skipped."
        else:
            value, ack = _parse_answer(kind, key, message)
            if value is None:
                result["text"] = ack + "\n\n" + _prompt(index)
                return data
            state["answers"][key] = value
            state["skipped"] = [k for k in state["skipped"] if k != key]
            state["index"] = index + 1
        state["updated_at"] = _now().isoformat()
        if state["index"] >= TOTAL:
            result["finished"] = _build_profile(state["answers"])
            result["text"] = ack
            return {"status": "idle"}
        result["text"] = ack + "\n\n" + _prompt(state["index"])
        return state

    _locked_update(_modify)
    if result["finished"] is not None:
        action_id, text = atlas_actions.propose_save_profile(result["finished"])
        return (f"{result['text']}\n\nThat's everything. Here is your profile for your approval:\n\n{text}"
                + _approve_hint(action_id)
                + "\n(If anything is wrong, 'deny' it and type 'atlas setup' to go again, or approve it and change single "
                  "things later, for example 'set days 4'.)")
    return result["text"]


# --------------------------------------------------------------
# PROFILE COMMANDS
# --------------------------------------------------------------

def _propose_change(field: str, value) -> str:
    action_id, text = atlas_actions.propose_profile_update(field, value)
    return text + _approve_hint(action_id)


def _run_command(kind: str, value):
    if kind == "start":
        return _start()
    if kind == "cancel":
        return _cancel()
    if kind == "continue":
        return _continue()
    if kind == "show":
        profile = profiles.load_profile()
        if profile is None:
            return "You don't have a training profile yet. Type 'atlas setup' and I'll ask you the questions a trainer would."
        return profiles.format_profile(profile)
    if kind == "too_long":
        which, length, limit = value
        return (f"I didn't understand '{which} ...': it is {length} characters or has line breaks, and the limit is {limit} "
                f"characters on one line. Nothing was saved. Split it into shorter parts, one '{which} ...' for each.")
    if kind == "clear_limitations":
        return _propose_change("clear_limitations", None)
    if kind == "add_limitation":
        return _propose_change("add_limitation", value)
    if kind == "text":
        field, text = value
        return _propose_change(field, text)
    return _propose_change(kind, value)            # goal_type, goal_order, days_per_week, session_minutes, program_style


def handle_message(message) -> Optional[str]:
    """
    The text to show for a setup or profile message, or None when the message is none of ATLAS setup's
    business (normal chat goes on). A non-text message fails loudly.
    """
    command = match_command(message)
    try:
        if command:
            return _run_command(*command)
        state = _peek_state()
        if state is None or _is_stale(state):
            return None
        return _answer(message)
    except RuntimeError as e:
        return f"I can't read or write the setup or profile files right now: {e}"
    except ValueError as e:
        return f"I couldn't use that: {e}. Nothing was saved."