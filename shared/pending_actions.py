"""
Pending-approval queue for CIPHER's real, gated actions — creating
files and running commands. Per Decision: these are the ONLY two
action types that ever pause for approval; everything else CIPHER
does (answering questions, even when reached through NEXUS's future
bridge) runs immediately, no approval needed.

Generic/shared (not CIPHER-specific) so any future agent that needs
its own gated real action can reuse this same queue rather than
building its own — the actual execution logic for what "approved"
means stays in each agent's own tools module (e.g.
agents/cipher/cipher_tools.py), not here.

Uses shared/file_store.py's locked read-modify-write (Lesson #4) since
this file gets written both when an action is proposed and, later,
when it's approved/denied/executed — potentially from different
callers at different times.
"""
import os
import uuid
from datetime import datetime

from filelock import FileLock

from shared.file_store import load_json, update_json

PENDING_ACTIONS_PATH = os.getenv("PENDING_ACTIONS_PATH", r"D:\Projects\forge\data\pending_actions.json")

_DEFAULT = {"actions": []}


def _locked_load() -> dict:
    """
    Read the queue under the SAME lock the writers hold. Writers rewrite the
    whole file in place, so an unlocked reader can catch it half-written and
    crash with a JSON error (found by ATLAS's 20-thread approval test).
    """
    with FileLock(PENDING_ACTIONS_PATH + ".lock", timeout=10):
        return load_json(PENDING_ACTIONS_PATH, _DEFAULT)


def create_pending_action(agent: str, action_type: str, details: dict) -> str:
    """
    action_type: e.g. "create_file" or "run_command" — this module
    doesn't care what the string is, only the calling agent's tools
    module does.
    details: whatever the agent's own tools module needs to actually
    execute this later (e.g. {"path": ..., "content": ...}).
    Returns the new action's id.
    """
    action_id = str(uuid.uuid4())

    def _modify(data):
        data.setdefault("actions", []).append({
            "id": action_id,
            "agent": agent,
            "type": action_type,
            "details": details,
            "status": "pending",
            "result": None,
            "created_at": datetime.now().isoformat(),
            "resolved_at": None,
        })
        return data

    update_json(PENDING_ACTIONS_PATH, _modify, default=_DEFAULT)
    return action_id


def get_pending_action(action_id: str) -> dict | None:
    data = _locked_load()
    for action in data.get("actions", []):
        if action["id"] == action_id:
            return action
    return None


def resolve_action(action_id: str, status: str, result: str | None = None) -> bool:
    """
    status: "denied", "executed", or "failed". Returns False if the
    action doesn't exist or was already resolved — never re-resolves
    something already decided.
    """
    resolved = {"ok": False}

    def _modify(data):
        for action in data.get("actions", []):
            if action["id"] == action_id and action["status"] == "pending":
                action["status"] = status
                action["result"] = result
                action["resolved_at"] = datetime.now().isoformat()
                resolved["ok"] = True
                break
        return data

    update_json(PENDING_ACTIONS_PATH, _modify, default=_DEFAULT)
    return resolved["ok"]


def claim_action(action_id: str) -> bool:
    """
    Atomically transitions a pending action to "executing" — this is
    what actually prevents two near-simultaneous approvals of the SAME
    action from both proceeding to real execution. A plain "is it still
    pending?" read followed by a later write has a race window; this
    doesn't, since it reuses resolve_action's locked read-modify-write.
    Returns True only for the one caller that actually won the race.
    """
    return resolve_action(action_id, "executing")


def finalize_action(action_id: str, status: str, result: str | None = None) -> None:
    """
    Unconditionally sets an action's final status/result. Only ever
    call this AFTER claim_action() returned True for this same
    action_id — by that point this caller is the sole owner, so no
    pending-status check is needed (or correct) here.
    """
    def _modify(data):
        for action in data.get("actions", []):
            if action["id"] == action_id:
                action["status"] = status
                action["result"] = result
                action["resolved_at"] = datetime.now().isoformat()
                break
        return data

    update_json(PENDING_ACTIONS_PATH, _modify, default=_DEFAULT)


def list_pending_actions(agent: str | None = None) -> list[dict]:
    data = _locked_load()
    actions = [a for a in data.get("actions", []) if a["status"] == "pending"]
    if agent:
        actions = [a for a in actions if a["agent"] == agent]
    return actions