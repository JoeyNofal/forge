"""
CIPHER's real, permission-gated actions: creating files and running
commands. Per Decision: these two are the ONLY things that ever pause
for Joey's approval — a plain question to CIPHER, even routed through
NEXUS's future bridge, never pauses for anything.

propose_* functions are called from chat.py the moment CIPHER's own
response contains a SAVE_FILE or RUN_COMMAND marker — they create a
pending action and return immediately; NOTHING real happens yet.
approve_and_execute() is the only function that actually touches disk
or runs a real process, and only once Joey has said yes.
"""
import os
import subprocess

from shared.pending_actions import create_pending_action, get_pending_action, claim_action, finalize_action, resolve_action

AGENT_NAME = "cipher"


def propose_create_file(path: str, content: str) -> tuple[str, str]:
    """Returns (action_id, a short human-readable description)."""
    action_id = create_pending_action(AGENT_NAME, "create_file", {"path": path, "content": content})
    return action_id, f"create {path}"


def propose_run_command(command: str) -> tuple[str, str]:
    action_id = create_pending_action(AGENT_NAME, "run_command", {"command": command})
    return action_id, f"run: {command}"


def _real_create_file(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Created {path} ({len(content)} chars)."


def _real_run_command(command: str, timeout: int = 30) -> str:
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=timeout
    )
    output = (result.stdout or "") + (result.stderr or "")
    return output.strip() or f"(command exited {result.returncode}, no output)"


def approve_and_execute(action_id: str) -> str:
    """
    The ONLY function that actually touches disk or runs a process.
    Looks up the pending action, ATOMICALLY claims it (so two
    near-simultaneous approvals of the same action can never both
    execute for real), then executes it and returns a plain-English
    result to show Joey. A real execution failure is reported back
    clearly (Lesson #12: fail loudly), never silently swallowed as a
    fake success.
    """
    action = get_pending_action(action_id)
    if action is None:
        return f"No pending action found with id {action_id}."
    if action["agent"] != AGENT_NAME:
        return f"Action {action_id} doesn't belong to CIPHER."
    if action["status"] != "pending":
        return f"Action {action_id} was already {action['status']}, not executing again."

    if not claim_action(action_id):
        # Lost a real race to another near-simultaneous approval of the
        # exact same action - it's already being (or was already)
        # executed elsewhere. Never execute twice.
        return f"Action {action_id} was already claimed by another approval, not executing again."

    try:
        if action["type"] == "create_file":
            result = _real_create_file(action["details"]["path"], action["details"]["content"])
        elif action["type"] == "run_command":
            result = _real_run_command(action["details"]["command"])
        else:
            result = f"Unknown action type: {action['type']}"
            finalize_action(action_id, "failed", result)
            return result
        finalize_action(action_id, "executed", result)
        return result
    except Exception as e:
        error_result = f"Execution failed: {type(e).__name__}: {e}"
        finalize_action(action_id, "failed", error_result)
        return error_result


def deny_action(action_id: str) -> str:
    action = get_pending_action(action_id)
    if action is None:
        return f"No pending action found with id {action_id}."
    if action["status"] != "pending":
        return f"Action {action_id} was already {action['status']}."
    resolve_action(action_id, "denied")
    return f"Denied: {action['type']} ({action['details']})"