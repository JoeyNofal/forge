"""
ATLAS ACTIONS — approval gate in front of every fitness-data write
(increment (b), Part 2).

The rule (Youssef's decision): ATLAS never saves a workout or injury on
its own. It PROPOSES; nothing touches the fitness file until you approve.

    propose_*()           -> cleans the data, puts it in the shared pending
                             queue, returns (action_id, plain-English summary).
                             ZERO effect on the fitness file.
    approve_and_execute() -> the ONLY way anything gets written. The atomic
                             claim (two near-simultaneous approvals can never
                             both save) lives in the ONE shared gate,
                             shared/action_gate.py, not in a private copy here.
    deny_action()         -> throws the proposal away.

Consolidation (Lesson #9): the find-by-id / claim / run-once / record-outcome
logic used to be copy-pasted here and in DRIVE. It now lives once in
shared/action_gate.py (its own full L1-L5 tests). This file only supplies
what is truly ATLAS's: the summaries and the table of which writer each
action type runs. All the real writing lives in atlas_logging.py.
You may approve or deny with the full id or any unique start of it (6+
characters) — the ids are long and you'll be typing them.
"""
from agents.atlas import atlas_logging as log
from agents.atlas import exercise_library as library
from agents.atlas.atlas_tools import load_fitness_data
from agents.atlas.workout_block import parse_workout_block
from shared.action_gate import ActionGate

AGENT_NAME = "atlas"

TYPE_LOG_SWIM = "log_swim"
TYPE_LOG_GYM = "log_gym"
TYPE_LOG_INJURY = "log_injury"
TYPE_UPDATE_INJURY = "update_injury"
TYPE_LOG_WORKOUT_BLOCK = "log_workout_block"
TYPE_ADD_EXERCISE = "add_exercise"
TYPE_MARK_EXERCISE_REVIEWED = "mark_exercise_reviewed"


# ─────────────────────────────────────────────
# SECTION 1 — PLAIN-ENGLISH SUMMARIES
# ─────────────────────────────────────────────

def _stated(value, template: str, missing: str) -> str:
    """'45 min' when Joey gave it, 'duration not stated' when he didn't — never a made-up 0 or 5."""
    return template.format(value) if value else missing


def _weights_note(d: dict) -> str:
    """'; weights: bench press 135 lbs, curl 30 lbs (unit assumed)' — or '' when no weights."""
    assumed = d.get("units_assumed")
    assumed = assumed if isinstance(assumed, list) else []
    parts = []
    for e in d["exercises"]:
        if not isinstance(e, dict) or e.get("weight_lbs") is None:
            continue
        text = f"{e['name']} {e['weight_lbs']} lbs"
        if e["name"] in assumed:
            text += " (unit assumed)"
        parts.append(text)
    return f"; weights: {', '.join(parts)}" if parts else ""


def _describe_block(d: dict) -> str:
    names = ", ".join(e["name"] for e in d["exercises"]) or "none"
    text = (f"log workout \"{d['title']}\" on {d['date']}: "
            f"{len(d['exercises'])} exercise(s) ({names}), "
            f"{len(d['warmup'])} warmup, {len(d['cooldown'])} cooldown"
            f"{_weights_note(d)}")
    skipped = d.get("skipped")
    if isinstance(skipped, list) and skipped:
        text += f"; skipped: {', '.join(str(s) for s in skipped)}"
    return text


def describe(action_type: str, d: dict) -> str:
    """One readable line for a proposal. Never crashes on odd details."""
    try:
        if action_type == TYPE_LOG_SWIM:
            distance = _stated(d['total_distance_yards'], '{} yards', 'distance not stated')
            if d['total_distance_yards'] and 'distance' in (d.get('units_assumed') or []):
                distance += " (unit assumed)"
            return (f"log swim: {distance}, "
                    f"{_stated(d['duration_minutes'], '{} min', 'duration not stated')}, "
                    f"{_stated(d['difficulty_1_to_10'], 'difficulty {}/10', 'difficulty not stated')}, on {d['date']}")
        if action_type == TYPE_LOG_GYM:
            names = ", ".join(e["name"] for e in d["exercises"])
            return (f"log gym workout: {len(d['exercises'])} exercise(s) ({names}), "
                    f"{_stated(d['duration_minutes'], '{} min', 'duration not stated')}, "
                    f"{_stated(d['difficulty_1_to_10'], 'difficulty {}/10', 'difficulty not stated')}, on {d['date']}"
                    f"{_weights_note(d)}")
        if action_type == TYPE_LOG_INJURY:
            return f"log injury: {d['description']} ({d['severity']}), on {d['date']}"
        if action_type == TYPE_UPDATE_INJURY:
            return f"update injury: {d['body_part']} -> {d['new_status']}"
        if action_type == TYPE_LOG_WORKOUT_BLOCK:
            return _describe_block(d)
        if action_type == TYPE_ADD_EXERCISE:
            return f"add exercise to the library: {d['name']} (AI-drafted, you review it later)"
        if action_type == TYPE_MARK_EXERCISE_REVIEWED:
            return f"mark exercise as reviewed: {d['name']}"
    except (KeyError, TypeError):
        pass
    return f"{action_type}: {d}"


def _proposal_message(action_id: str, action_type: str, details: dict) -> str:
    return (f"Proposed: {describe(action_type, details)}\n"
            f"Nothing is saved until you approve. id: {action_id}")


# ─────────────────────────────────────────────
# SECTION 2 — WHAT EACH APPROVED ACTION ACTUALLY RUNS
# Only the shared gate ever calls these, and only after it has
# atomically claimed the action. Each returns (ok, message).
# ─────────────────────────────────────────────

def _run_swim(d: dict) -> tuple:
    return True, log.log_swim(d)


def _run_gym(d: dict) -> tuple:
    return True, log.log_gym(d)


def _run_injury(d: dict) -> tuple:
    return True, log.log_injury(d)


def _run_injury_update(d: dict) -> tuple:
    ok, result = log.update_injury_status(d)
    return bool(ok), result


def _run_workout_block(d: dict) -> tuple:
    ok, result = log.log_workout_block(d)
    return bool(ok), result


def _run_add_exercise(d: dict) -> tuple:
    ok, result = library.add_entry(d)
    return bool(ok), result


def _run_mark_exercise_reviewed(d: dict) -> tuple:
    ok, result = library.mark_reviewed(d.get("id"))
    return bool(ok), result


_gate = ActionGate(
    AGENT_NAME,
    "ATLAS",
    describe,
    {
        TYPE_LOG_SWIM: _run_swim,
        TYPE_LOG_GYM: _run_gym,
        TYPE_LOG_INJURY: _run_injury,
        TYPE_UPDATE_INJURY: _run_injury_update,
        TYPE_LOG_WORKOUT_BLOCK: _run_workout_block,
        TYPE_ADD_EXERCISE: _run_add_exercise,
        TYPE_MARK_EXERCISE_REVIEWED: _run_mark_exercise_reviewed,
    },
)


# ─────────────────────────────────────────────
# SECTION 3 — PROPOSING (no effect on the fitness file)
# ─────────────────────────────────────────────

def _propose(action_type: str, clean: dict) -> tuple:
    action_id = _gate.propose(action_type, clean)
    return action_id, _proposal_message(action_id, action_type, clean)


def propose_swim(raw) -> tuple:
    """Bad data raises ValueError HERE, so garbage never enters the queue."""
    return _propose(TYPE_LOG_SWIM, log.normalize_swim(raw))


def propose_gym(raw) -> tuple:
    return _propose(TYPE_LOG_GYM, log.normalize_gym(raw))


def propose_injury(raw) -> tuple:
    return _propose(TYPE_LOG_INJURY, log.normalize_injury(raw))


def propose_workout_block(text) -> tuple:
    """
    A pasted FORGE WORKOUT LOG block -> a proposal. Read-only: zero effect on the
    fitness file. Bad text raises BlockError / ValueError / TypeError. Returns
    (None, explanation) when this exact workout is already logged.
    """
    parsed = parse_workout_block(text)
    clean = log.normalize_workout_block(parsed)
    if log.is_duplicate_workout_block(clean["block_hash"]):
        return None, "This workout is already logged - nothing to propose."
    action_id, message = _propose(TYPE_LOG_WORKOUT_BLOCK, clean)
    notes = clean.get("warnings") or []
    if notes:
        message += "\nHeads up (lines I could not read):\n" + "\n".join(f"- {n}" for n in notes[:5])
    return action_id, message


def propose_add_exercise(raw) -> tuple:
    """
    A drafted exercise -> a proposal that SHOWS the whole how-to. Read-only: nothing is
    written to the library. Bad drafts raise ValueError. Returns (None, why) when the
    exercise (or one of its other names) is already in the library.
    """
    clean = library.normalize_entry(raw)
    conflict = library.find_conflict(clean)
    if conflict is not None:
        return None, f"'{conflict.get('name')}' is already in the library - nothing to add."
    action_id, message = _propose(TYPE_ADD_EXERCISE, clean)
    return action_id, message + "\n\n" + library.format_entry(clean)


def propose_mark_reviewed(name) -> tuple:
    """'I have checked this entry' -> a proposal. Read-only. Returns (None, why) when there is nothing to do."""
    entry = library.find_exercise(name)
    if entry is None:
        return None, f"'{str(name)[:60]}' is not in the exercise library."
    if entry.get("status") == library.STATUS_REVIEWED:
        return None, f"'{entry.get('name')}' is already marked as reviewed."
    if not isinstance(entry.get("id"), str):
        return None, f"'{entry.get('name')}' has no id in the library file, so it cannot be marked."
    return _propose(TYPE_MARK_EXERCISE_REVIEWED, {"id": entry["id"], "name": entry.get("name")})


def propose_injury_update(raw) -> tuple:
    """
    Checks NOW (read-only) that exactly one open injury matches, so you are
    never asked to approve something that can't work. Returns
    (None, explanation) when it can't be proposed; otherwise (id, summary).
    """
    clean = log.normalize_injury_update(raw)
    data = load_fitness_data()
    injuries = data.get("injuries")
    hits = log.find_open_injuries(injuries if isinstance(injuries, list) else [], clean["body_part"])
    if not hits:
        return None, f"No open injury matching '{clean['body_part']}' — nothing to update."
    if len(hits) > 1:
        names = "; ".join(str(h.get("description")) for h in hits)
        return None, f"More than one open injury matches '{clean['body_part']}' ({names}) — be more specific."
    return _propose(TYPE_UPDATE_INJURY, clean)


# ─────────────────────────────────────────────
# SECTION 4 — APPROVING / DENYING (thin wrappers over the shared gate)
# ─────────────────────────────────────────────

def approve_and_execute(action_id: str) -> str:
    """Claims the action atomically, saves, reports the real outcome. See shared/action_gate.py."""
    return _gate.approve_and_execute(action_id)


def deny_action(action_id: str) -> str:
    return _gate.deny_action(action_id)


def get_pending_workout(action_id):
    """The cleaned record of a WAITING workout-block proposal, or None. Read-only."""
    action, _error = _gate.find_action(action_id)
    if not action or action.get("type") != TYPE_LOG_WORKOUT_BLOCK:
        return None
    details = action.get("details")
    return details if isinstance(details, dict) else None


def list_pending() -> str:
    """Everything of ATLAS's still waiting for approval, one per line."""
    return _gate.list_pending()