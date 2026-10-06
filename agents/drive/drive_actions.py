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
from shared import drive_memory
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
TYPE_UPDATE_ISSUES = "update_issues"
TYPE_ADD_BRAKE_REMINDER = "add_brake_reminder"
TYPE_LOG_CARFAX = "log_carfax"
TYPE_SAVE_RECALLS = "save_recall_check"
TYPE_FORGET_MEMORY = "forget_memory"
TYPE_FORGET_ALL_MEMORIES = "forget_all_memories"


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
        if action_type == TYPE_UPDATE_ISSUES:
            names = d.get("issue_descriptions") or d["issue_ids"]
            return f"mark {len(d['issue_ids'])} issue(s) resolved: " + "; ".join(str(n) for n in names)
        if action_type == TYPE_ADD_BRAKE_REMINDER:
            return "add a brake reminder: Brake Inspection, due today (shows first on your tracker until you log brake work)"
        if action_type == TYPE_LOG_CARFAX:
            mil = _stated(d["mileage"], "at {:,} miles", "mileage not stated")
            return f"log Carfax entry (work by a previous owner): {d['display_name']} on {d['date']}, {mil}"
        if action_type == TYPE_SAVE_RECALLS:
            return (f"save this recall check to your vehicle file: NHTSA, {d['model_year']} {d['make']} {d['model']}, "
                    f"{d['count']} recall(s), checked {str(d['fetched_at'])[:10]}")
        if action_type == TYPE_FORGET_MEMORY:
            return f"forget this memory: \"{d['text']}\" ({d['category']}, saved {str(d['saved_at'])[:10]})"
        if action_type == TYPE_FORGET_ALL_MEMORIES:
            return f"forget ALL {d['count']} memories DRIVE has saved about you"
    except (KeyError, TypeError, ValueError, AttributeError):
        pass
    return f"{action_type}: {d}"


def _proposal_message(action_id: str, action_type: str, details: dict, warnings=()) -> str:
    lines = [f"Proposed: {describe(action_type, details)}"]
    lines.extend(warnings)
    verb = "deleted" if action_type in (TYPE_FORGET_MEMORY, TYPE_FORGET_ALL_MEMORIES) else "saved"
    lines.append(f"Nothing is {verb} until you approve. id: {action_id}")
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


def list_open_issues() -> list:
    """[(id, description)] of unresolved issues, in file order. READ-ONLY.
    A missing file is just 'none'; a real file problem raises RuntimeError."""
    out = []
    for i in _issues_readonly():
        if isinstance(i, dict) and isinstance(i.get("id"), str) and (i.get("status") or "open") != "resolved":
            out.append((i["id"], str(i.get("description") or "")[:100]))
    return out


def _has_brake_schedule_readonly() -> bool:
    """True if a brake inspection is already scheduled. READ-ONLY; a real file problem raises RuntimeError."""
    if not os.path.exists(get_data_path()):
        return False
    return log.has_brake_schedule(get_active_vehicle(load_data()))


def _last_nhtsa_snapshot_readonly():
    """The most recent saved NHTSA check, or None. READ-ONLY; a real file problem raises RuntimeError."""
    if not os.path.exists(get_data_path()):
        return None
    return log.last_nhtsa_snapshot(get_active_vehicle(load_data()))


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


def propose_brake_reminder() -> tuple:
    """
    Proposes the one-time 'Brake Inspection, due today' entry. Checks NOW (read-only) that a brake
    inspection isn't already scheduled; returns (None, explanation) if so.
    """
    if _has_brake_schedule_readonly():
        return None, "A brake inspection is already on your schedule — nothing to add."
    return _propose(TYPE_ADD_BRAKE_REMINDER, {"service_type": "brake_inspection"})


def propose_carfax(raw) -> tuple:
    """Bad data (including a missing date) raises ValueError HERE, so nothing half-formed is ever queued."""
    clean = log.normalize_carfax(raw)
    return _propose(TYPE_LOG_CARFAX, clean, _mileage_warnings(TYPE_LOG_CARFAX, clean["mileage"]))


def propose_recall_snapshot(raw) -> tuple:
    """
    Offers to save an NHTSA recall check — but ONLY when the list changed since the last saved check
    (Joey's choice). Returns (None, explanation) when it hasn't. Bad data raises ValueError here.
    """
    clean = log.normalize_recall_snapshot(raw)
    last = _last_nhtsa_snapshot_readonly()
    if last is not None and log.snapshot_signature(last) == log.snapshot_signature(clean):
        when = str(last.get("fetched_at") or last.get("searched_at") or "")[:10]
        return None, f"NHTSA's list hasn't changed since your last saved check ({when}), so I'm not offering to save it again."
    return _propose(TYPE_SAVE_RECALLS, clean)


def propose_forget_memory(memory) -> tuple:
    """Offers to delete ONE memory (a dict with at least 'id'). Nothing is deleted until Joey approves."""
    if not isinstance(memory, dict) or not isinstance(memory.get("id"), str) or not memory["id"].strip():
        raise ValueError("forget: I need a memory with an id")
    return _propose(TYPE_FORGET_MEMORY, {
        "memory_id": memory["id"].strip()[:200],
        "text": str(memory.get("text") or "")[:500],
        "category": str(memory.get("category") or "")[:40],
        "saved_at": str(memory.get("saved_at") or "")[:40],
    })


def propose_forget_all_memories(memories) -> tuple:
    """
    Offers to delete EXACTLY these memories (their ids are captured now, so a memory saved after the
    proposal survives an approval made later).
    """
    ids = ([m["id"].strip() for m in memories if isinstance(m, dict) and isinstance(m.get("id"), str) and m["id"].strip()]
           if isinstance(memories, list) else [])
    if not ids:
        raise ValueError("forget all: there are no memories")
    return _propose(TYPE_FORGET_ALL_MEMORIES, {"ids": ids, "count": len(ids)})


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


def propose_issues_update(raw) -> tuple:
    """
    'Everything is fixed.' Checks NOW (read-only) which of the listed issues
    really exist and are still unresolved, and proposes resolving exactly those,
    naming each one so you can see what you're approving. Returns (None,
    explanation) when none qualify.
    """
    clean = log.normalize_issues_update(raw)
    open_by_id = {i["id"]: i for i in _issues_readonly()
                  if isinstance(i, dict) and isinstance(i.get("id"), str)
                  and (i.get("status") or "open") != "resolved"}
    wanted = [iid for iid in clean["issue_ids"] if iid in open_by_id]
    if not wanted:
        return None, "None of those issues are on file and still unresolved — nothing to update."
    clean = dict(clean, issue_ids=wanted,
                 issue_descriptions=[str(open_by_id[i].get("description") or "")[:100] for i in wanted])
    return _propose(TYPE_UPDATE_ISSUES, clean)


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
        elif t == TYPE_UPDATE_ISSUES:
            ok, result = log.update_issues_status(d)
            if not ok:
                finalize_action(real_id, "failed", result)
                return result
        elif t == TYPE_ADD_BRAKE_REMINDER:
            ok, result = log.log_brake_reminder()
            if not ok:
                finalize_action(real_id, "failed", result)
                return result
        elif t == TYPE_LOG_CARFAX:
            ok, result = log.log_carfax_entry(d)
            if not ok:
                finalize_action(real_id, "failed", result)
                return result
        elif t == TYPE_SAVE_RECALLS:
            ok, result = log.save_recall_snapshot(d)
            if not ok:
                finalize_action(real_id, "failed", result)
                return result
        elif t == TYPE_FORGET_MEMORY:
            if not drive_memory.delete_memory(d["memory_id"]):
                result = "That memory is already gone, so nothing was deleted."
                finalize_action(real_id, "failed", result)
                return result
            result = f"Forgotten: \"{d['text']}\""
        elif t == TYPE_FORGET_ALL_MEMORIES:
            deleted = drive_memory.delete_memories(d["ids"])
            if deleted == 0:
                result = "Those memories are already gone, so nothing was deleted."
                finalize_action(real_id, "failed", result)
                return result
            result = f"Forgot {deleted} memor{'y' if deleted == 1 else 'ies'}."
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