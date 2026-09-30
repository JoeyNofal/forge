"""
ATLAS ACTIONS — approval gate in front of every fitness-data write
(increment (b), Part 2).

The rule (Youssef's decision): ATLAS never saves a workout or injury on
its own. It PROPOSES; nothing touches the fitness file until you approve.

    propose_*()          -> cleans the data, puts it in the shared pending
                            queue, returns (action_id, plain-English summary).
                            ZERO effect on the fitness file.
    approve_and_execute() -> the ONLY function here that writes. Claims the
                            action atomically first, so two near-simultaneous
                            approvals of the same action can never both save.
    deny_action()        -> throws the proposal away.

Same pattern as agents/cipher/cipher_tools.py, using the same generic queue
(shared/pending_actions.py). All the real writing lives in atlas_logging.py.
You may approve or deny with the full id or any unique start of it (6+
characters) — the ids are long and you'll be typing them.
"""
from agents.atlas import atlas_logging as log
from agents.atlas.atlas_tools import load_fitness_data
from shared.pending_actions import (
    create_pending_action, get_pending_action, list_pending_actions,
    claim_action, finalize_action, resolve_action,
)

AGENT_NAME = "atlas"
MIN_ID_PREFIX = 6

TYPE_LOG_SWIM = "log_swim"
TYPE_LOG_GYM = "log_gym"
TYPE_LOG_INJURY = "log_injury"
TYPE_UPDATE_INJURY = "update_injury"


# ─────────────────────────────────────────────
# SECTION 1 — PLAIN-ENGLISH SUMMARIES
# ─────────────────────────────────────────────

def _stated(value, template: str, missing: str) -> str:
    """'45 min' when Joey gave it, 'duration not stated' when he didn't — never a made-up 0 or 5."""
    return template.format(value) if value else missing


def describe(action_type: str, d: dict) -> str:
    """One readable line for a proposal. Never crashes on odd details."""
    try:
        if action_type == TYPE_LOG_SWIM:
            return (f"log swim: {_stated(d['total_distance_yards'], '{} yards', 'distance not stated')}, "
                    f"{_stated(d['duration_minutes'], '{} min', 'duration not stated')}, "
                    f"{_stated(d['difficulty_1_to_10'], 'difficulty {}/10', 'difficulty not stated')}, on {d['date']}")
        if action_type == TYPE_LOG_GYM:
            names = ", ".join(e["name"] for e in d["exercises"])
            return (f"log gym workout: {len(d['exercises'])} exercise(s) ({names}), "
                    f"{_stated(d['duration_minutes'], '{} min', 'duration not stated')}, "
                    f"{_stated(d['difficulty_1_to_10'], 'difficulty {}/10', 'difficulty not stated')}, on {d['date']}")
        if action_type == TYPE_LOG_INJURY:
            return f"log injury: {d['description']} ({d['severity']}), on {d['date']}"
        if action_type == TYPE_UPDATE_INJURY:
            return f"update injury: {d['body_part']} -> {d['new_status']}"
    except (KeyError, TypeError):
        pass
    return f"{action_type}: {d}"


def _proposal_message(action_id: str, action_type: str, details: dict) -> str:
    return (f"Proposed: {describe(action_type, details)}\n"
            f"Nothing is saved until you approve. id: {action_id}")


# ─────────────────────────────────────────────
# SECTION 2 — PROPOSING (no effect on the fitness file)
# ─────────────────────────────────────────────

def _propose(action_type: str, clean: dict) -> tuple:
    action_id = create_pending_action(AGENT_NAME, action_type, clean)
    return action_id, _proposal_message(action_id, action_type, clean)


def propose_swim(raw) -> tuple:
    """Bad data raises ValueError HERE, so garbage never enters the queue."""
    return _propose(TYPE_LOG_SWIM, log.normalize_swim(raw))


def propose_gym(raw) -> tuple:
    return _propose(TYPE_LOG_GYM, log.normalize_gym(raw))


def propose_injury(raw) -> tuple:
    return _propose(TYPE_LOG_INJURY, log.normalize_injury(raw))


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
# SECTION 3 — FINDING AN ACTION BY (PART OF) ITS ID
# ─────────────────────────────────────────────

def _find_action(action_id: str):
    """Returns (action, None) or (None, error message). Only ATLAS's own actions."""
    if not isinstance(action_id, str) or not action_id.strip():
        return None, "No action id given."
    action_id = action_id.strip()
    action = get_pending_action(action_id)
    if action is not None:
        if action["agent"] != AGENT_NAME:
            return None, f"Action {action_id} doesn't belong to ATLAS."
        return action, None
    if len(action_id) >= MIN_ID_PREFIX:
        matches = [a for a in list_pending_actions(AGENT_NAME) if a["id"].startswith(action_id)]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, f"'{action_id}' matches more than one pending action — type more of the id."
    return None, f"No pending action found with id {action_id}."


# ─────────────────────────────────────────────
# SECTION 4 — APPROVING / DENYING
# ─────────────────────────────────────────────

def approve_and_execute(action_id: str) -> str:
    """
    The ONLY function here that actually writes to the fitness file. Claims
    the action atomically first (so it can never save twice), saves, and
    reports the real outcome. A failure is reported clearly and recorded as
    failed — never dressed up as a success (Lesson #12).
    """
    action, err = _find_action(action_id)
    if action is None:
        return err or "Action not found."
    real_id = action["id"]
    if action["status"] != "pending":
        return f"Action {real_id} was already {action['status']}, not executing again."
    if not claim_action(real_id):
        return f"Action {real_id} was already claimed by another approval, not executing again."

    try:
        t, d = action["type"], action["details"]
        if t == TYPE_LOG_SWIM:
            result = log.log_swim(d)
        elif t == TYPE_LOG_GYM:
            result = log.log_gym(d)
        elif t == TYPE_LOG_INJURY:
            result = log.log_injury(d)
        elif t == TYPE_UPDATE_INJURY:
            ok, result = log.update_injury_status(d)
            if not ok:
                finalize_action(real_id, "failed", result)
                return result
        else:
            result = f"Unknown action type: {t}"
            finalize_action(real_id, "failed", result)
            return result
        finalize_action(real_id, "executed", result)
        return result
    except Exception as e:
        error_result = f"Execution failed: {type(e).__name__}: {e}"
        finalize_action(real_id, "failed", error_result)
        return error_result


def deny_action(action_id: str) -> str:
    action, err = _find_action(action_id)
    if action is None:
        return err or "Action not found."
    real_id = action["id"]
    if action["status"] != "pending":
        return f"Action {real_id} was already {action['status']}."
    if not resolve_action(real_id, "denied"):
        return f"Action {real_id} was already resolved by someone else."
    return f"Denied: {describe(action['type'], action['details'])}"


def list_pending() -> str:
    """Everything of ATLAS's still waiting for approval, one per line."""
    actions = list_pending_actions(AGENT_NAME)
    if not actions:
        return "Nothing waiting for approval."
    return "\n".join(f"{a['id']}  {describe(a['type'], a['details'])}" for a in actions)