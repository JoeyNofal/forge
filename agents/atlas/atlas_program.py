"""
ATLAS PROGRAM COMMANDS (increment 3b): 'my program' and 'set next day <label>'.

- 'my program' shows your style, the days in order, what is next and the numbers per session.
  It only READS (the profile and your logged workouts).
- 'set next day Pull' is a manual override of the rotation. Like every change it is a PROPOSAL:
  nothing is saved until you approve it.
- A message counts as a command ONLY when the WHOLE message is the command (Lesson #6).
"""
import re
from typing import Optional

from agents.atlas import atlas_actions, programs
from agents.atlas import training_profile as profiles
from agents.atlas.atlas_tools import load_fitness_data

_I = re.IGNORECASE
_SHOW_RE = re.compile(r"^\s*(?:(?:show|view|see)\s+(?:my\s+)?program|my\s+program)\s*[?.!]?\s*$", _I)
_NEXT_DAY_RE = re.compile(r"^\s*set\s+next\s+day\s+(\S.{0,39}?)\s*[.!]?\s*$", _I)

_NO_PROFILE = "You don't have a training profile yet. Type 'atlas setup' and I'll ask you the questions a trainer would."


def match_command(message):
    """('show', None) / ('next_day', label) when the WHOLE message is that command, else None. Non-text fails loudly."""
    if _SHOW_RE.match(message):
        return "show", None
    m = _NEXT_DAY_RE.match(message)
    if m:
        return "next_day", m.group(1)
    return None


def _workouts() -> list:
    workouts = load_fitness_data().get("workouts")
    return workouts if isinstance(workouts, list) else []


def show_program() -> str:
    profile = profiles.load_profile()
    if profile is None:
        return _NO_PROFILE
    return programs.describe_program(profile, _workouts())


def propose_next_day(label: str) -> str:
    profile = profiles.load_profile()
    if profile is None:
        return _NO_PROFILE
    style, _reason = programs.resolve_style(profile)
    idx = programs.find_day(style, label)
    if idx is None:
        days = ", ".join(d["label"] for d in programs.PROGRAMS[style]["days"])
        return (f"I don't know a day called '{label}' in your {programs.PROGRAMS[style]['label']} program. "
                f"Your days are: {days}. Nothing was saved.")
    canonical = programs.PROGRAMS[style]["days"][idx]["label"]
    action_id, text = atlas_actions.propose_profile_update("next_day", canonical)
    short = action_id[:8]
    return text + f"\n\nReply 'approve {short}' to save it, or 'deny {short}' to throw it away."


def handle_message(message) -> Optional[str]:
    """The text to show for a program command, or None when the message is none of its business."""
    command = match_command(message)
    if command is None:
        return None
    kind, value = command
    try:
        return show_program() if kind == "show" else propose_next_day(value or "")
    except RuntimeError as e:
        return f"I can't read or write your profile or workout files right now: {e}"
    except ValueError as e:
        return f"I couldn't use that: {e}. Nothing was saved."