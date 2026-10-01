"""
DRIVE ACTIONS — approval gate in front of every vehicle-data write
(increment (b), Part 2).

The rule (Youssef's decision): DRIVE never saves a mileage update, service,
fill-up or issue on its own. It PROPOSES; nothing touches the vehicle file
until you approve.

    propose_*()           -> cleans the data, puts it in the shared pending
                             queue, returns (action_id, plain-English summary).
                             ZERO effect on the vehicle file (it doesn't even
                             create it).
    approve_and_execute() -> the ONLY function here that writes. Claims the
                             action atomically first, so two near-simultaneous
                             approvals of the same action can never both save.
    deny_action()         -> throws the proposal away.

Same pattern as agents/atlas/atlas_actions.py, using the same generic queue
(shared/pending_actions.py). All the real writing lives in drive_logging.py.
You may approve or deny with the full id or any unique start of it (6+
characters) — the ids are long and you'll be typing them.

Warnings (shown on the proposal, never blocking):
- a mileage UPDATE lower than the current mileage
- any mileage more than MAX_JUMP_WARNING_MILES above the current mileage
A backdated service at a lower mileage is normal, so it does not warn.
"""
import os

from agents.drive import drive_logging as log
from agents.drive.drive_tools import get_data_path, load_data, get_active_vehicle
from shared.pending_actions import (
    create_pending_action, get_pending_action, list_pending_actions,
    claim_action, finalize_action, resolve_action,
)

AGENT_NAME = "drive"
MIN_ID_PREFIX = 6
MAX_JUMP_WARNING_MILES = 5000

TYPE_LOG_MILEAGE = "log_mileage"
TYPE_LOG_MAINTENANCE = "log_maintenance"
TYPE_LOG_FILLUP = "log_fillup"
TYPE_LOG_ISSUE = "log_issue"
TYPE_UPDATE_ISSUE = "update_issue"


# ─────────────────────────────────────────────
# SECTION 1 — PLAIN-ENGLISH SUMMARIES
# ─────────────────────────────────────────────

def _stated(value, template: str, missing: str) -> str:
    """'at 55,500 miles' when Joey gave it, 'mileage not stated' when he didn't — never a made-up 0."""
    return template.format(value) if value else missing


def describe(action_type: str, d: dict) -> str:
    """One readable line for a proposal. Never crashes on odd details."""
    try:
        if action_type == TYPE_LOG_MILEAGE:
            return f"update mileage to {d['mileage']:,} miles"
        if action_type == TYPE_LOG_MAINTENANCE:
            mil = _stated(d["mileage"], "at {:,} miles", "mileage not stated")
            cost = _stated(d["cost"], "${:.2f}", "cost not stated")
            return f"log maintenance: {d['display_name']} on {d['date']}, {mil}, {cost}"
        if action_type == TYPE_LOG_FILLUP:
            gal = _stated(d["gallons"], "{} gal", "gallons not stated")
            price = _stated(d["price_per_gallon"], "${}/gal", "price not stated")
            total = _stated(d["total_cost"], "${:.2f} total", "total cost not stated")
            mil = _stated(d["mileage"], "at {:,} miles", "mileage not stated (MPG can't be worked out)")
            return f"log fill-up: {gal}, {price}, {total}, {mil}, on {d['date']}"
        if action_type == TYPE_LOG_ISSUE:
            sev = d["severity"] or "not stated"
            return f"log issue: {d['description']} (severity: {sev}), on {d['date']}"
        if action_type == TYPE_UPDATE_ISSUE:
            what = d.get("issue_description") or d["issue_id"]
            return f"mark issue resolved: {what}"
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    return f"{action_type}: {d}"


def _proposal_message(action_id: str, action_type: str, details: dict, warnings=()) -> str:
    lines = [f"Proposed: {describe(action_type, details)}"]
    lines.extend(warnings)
    lines.append(f"Nothing is saved until you approve. id: {action_id}")
    return "\n".join(lines)


# ─────────────────────────────────────────────
# SECTION 2 — READ-ONLY CHECKS (used only while proposing)
# ─────────────────────────────────────────────

def _current_mileage():
    """(current mileage or None, problem text or None). READ-ONLY: never creates the file."""
    if not os.path.exists(get_data_path()):
        return None, None
    try:
        vehicle = get_active_vehicle(load_data())
    except RuntimeError as e:
        return None, str(e)
    current = vehicle.get("current_mileage")
    if isinstance(current, bool) or not isinstance(current, (int, float)):
        return None, None
    return current, None


def _mileage_warnings(action_type: str, mileage) -> list:
    if mileage is None:
        return []
    current, problem = _current_mileage()
    if problem:
        return ["⚠ Couldn't read the vehicle file to check this mileage against your current one."]
    if current is None:
        return []
    if action_type == TYPE_LOG_MILEAGE and mileage < current:
        return [f"⚠ {mileage:,} is LOWER than your current {current:,.0f} miles — approve only if you are correcting the odometer."]
    if mileage - current > MAX_JUMP_WARNING_MILES:
        return [f"⚠ {mileage:,} is {mileage - current:,.0f} miles above your current {current:,.0f} — check for a typo."]
    return []


def _issues_readonly() -> list:
    """The active vehicle's issues. A real file problem raises RuntimeError, loudly."""
    if not os.path.exists(get_data_path()):
        return []
    vehicle = get_active_vehicle(load_data())
    issues = vehicle.get("issues")
    return issues if isinstance(issues, list) else []


# ─────────────────────────────────────────────
# SECTION 3 — PROPOSING (no effect on the vehicle file)
# ─────────────────────────────────────────────

def _propose(action_type: str, clean: dict, warnings=()) -> tuple:
    action_id = create_pending_action(AGENT_NAME, action_type, clean)
    return action_id, _proposal_message(action_id, action_type, clean, warnings)


def propose_mileage(raw) -> tuple:
    """Bad data raises ValueError HERE, so garbage never enters the queue."""
    clean = log.normalize_mileage(raw)
    return _propose(TYPE_LOG_MILEAGE, clean, _mileage_warnings(TYPE_LOG_MILEAGE, clean["mileage"]))


def propose_maintenance(raw) -> tuple:
    clean = log.normalize_maintenance(raw)
    return _propose(TYPE_LOG_MAINTENANCE, clean, _mileage_warnings(TYPE_LOG_MAINTENANCE, clean["mileage"]))


def propose_fillup(raw) -> tuple:
    clean = log.normalize_fillup(raw)
    return _propose(TYPE_LOG_FILLUP, clean, _mileage_warnings(TYPE_LOG_FILLUP, clean["mileage"]))


def propose_issue(raw) -> tuple:
    return _propose(TYPE_LOG_ISSUE, log.normalize_issue(raw))


def propose_issue_update(raw) -> tuple:
    """
    Checks NOW (read-only) that the issue exists and is still unresolved, so you
    are never asked to approve something that can't work. Returns (None,
    explanation) when it can't be proposed; otherwise (id, summary).
    """
    clean = log.normalize_issue_update(raw)
    hits = [i for i in _issues_readonly() if isinstance(i, dict) and i.get("id") == clean["issue_id"]]
    if not hits:
        return None, f"No issue with id {clean['issue_id']} is on file — nothing to update."
    issue = hits[0]
    if (issue.get("status") or "open") == "resolved":
        return None, "That issue is already resolved — nothing to update."
    clean = dict(clean, issue_description=str(issue.get("description") or "")[:200])
    return _propose(TYPE_UPDATE_ISSUE, clean)


# ─────────────────────────────────────────────
# SECTION 4 — FINDING AN ACTION BY (PART OF) ITS ID
# ─────────────────────────────────────────────

def _find_action(action_id: str):
    """Returns (action, None) or (None, error message). Only DRIVE's own actions."""
    if not isinstance(action_id, str) or not action_id.strip():
        return None, "No action id given."
    action_id = action_id.strip()
    action = get_pending_action(action_id)
    if action is not None:
        if action["agent"] != AGENT_NAME:
            return None, f"Action {action_id} doesn't belong to DRIVE."
        return action, None
    if len(action_id) >= MIN_ID_PREFIX:
        matches = [a for a in list_pending_actions(AGENT_NAME) if a["id"].startswith(action_id)]
        if len(matches) == 1:
            return matches[0], None
        if len(matches) > 1:
            return None, f"'{action_id}' matches more than one pending action — type more of the id."
    return None, f"No pending action found with id {action_id}."


# ─────────────────────────────────────────────
# SECTION 5 — APPROVING / DENYING
# ─────────────────────────────────────────────

def approve_and_execute(action_id: str) -> str:
    """
    The ONLY function here that actually writes to the vehicle file. Claims the
    action atomically first (so it can never save twice), saves, and reports the
    real outcome. A failure is reported clearly and recorded as failed — never
    dressed up as a success (Lesson #12).
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
        if t == TYPE_LOG_MILEAGE:
            result = log.log_mileage(d)
        elif t == TYPE_LOG_MAINTENANCE:
            result = log.log_maintenance(d)
        elif t == TYPE_LOG_FILLUP:
            result = log.log_fillup(d)
        elif t == TYPE_LOG_ISSUE:
            result = log.log_issue(d)
        elif t == TYPE_UPDATE_ISSUE:
            ok, result = log.update_issue_status(d)
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
    """Everything of DRIVE's still waiting for approval, one per line."""
    actions = list_pending_actions(AGENT_NAME)
    if not actions:
        return "Nothing waiting for approval."
    return "\n".join(f"{a['id']}  {describe(a['type'], a['details'])}" for a in actions)