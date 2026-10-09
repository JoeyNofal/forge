"""
CIPHER's real, permission-gated actions: creating files and running
commands. Per Decision: these two are the ONLY things that ever pause
for Joey's approval — a plain question to CIPHER, even routed through
NEXUS's bridge, never pauses for anything.

propose_* functions are called from chat.py the moment CIPHER's own
response contains a SAVE_FILE or RUN_COMMAND marker — they create a
pending action and return immediately; NOTHING real happens yet.
approve_and_execute() is the only way anything touches disk or runs a
real process, and only once Joey has said yes.

Consolidation (Lesson #9): the find-by-id / atomic claim / run-once /
record-the-real-outcome logic used to be a private copy here. It now lives
once in shared/action_gate.py (the same gate ATLAS and DRIVE use, with its own
full L1-L5 tests). This file only supplies what is truly CIPHER's: the two
real actions and the table of which one each action type runs.

You may approve or deny with the full id or any unique start of it (6+ characters).
"""
import os
import subprocess

from shared.action_gate import ActionGate

AGENT_NAME = "cipher"

TYPE_CREATE_FILE = "create_file"
TYPE_RUN_COMMAND = "run_command"


def describe(action_type: str, details) -> str:
    """One readable line for a proposal / denial (same wording CIPHER always used)."""
    return f"{action_type} ({details})"


# ─────────────────────────────────────────────
# THE TWO REAL ACTIONS (only the handlers below ever call these)
# ─────────────────────────────────────────────

def _real_create_file(path: str, content: str) -> str:
    os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        f.write(content)
    return f"Created {path} ({len(content)} chars)."


def _real_run_command(command: str, timeout: int = 30) -> tuple:
    """Runs a real command. Returns (exit code, combined output). A timeout raises, as it always did."""
    result = subprocess.run(
        command, shell=True, capture_output=True, text=True, timeout=timeout
    )
    return result.returncode, ((result.stdout or "") + (result.stderr or "")).strip()


# ─────────────────────────────────────────────
# WHAT EACH APPROVED ACTION RUNS (called only by the shared gate, after it has
# atomically claimed the action). Each returns (ok, message).
# ─────────────────────────────────────────────

def _run_create_file(d: dict) -> tuple:
    return True, _real_create_file(d["path"], d["content"])


def _run_command(d: dict) -> tuple:
    code, output = _real_run_command(d["command"])
    if code != 0:
        # Lesson #12: a command that failed is recorded as FAILED, never as a success.
        return False, f"Command failed (exit code {code}): {output or 'no output'}"
    return True, output or "(command exited 0, no output)"


_gate = ActionGate(
    AGENT_NAME,
    "CIPHER",
    describe,
    {
        TYPE_CREATE_FILE: _run_create_file,
        TYPE_RUN_COMMAND: _run_command,
    },
)


# ─────────────────────────────────────────────
# PROPOSING (nothing real happens)
# ─────────────────────────────────────────────

def propose_create_file(path: str, content: str) -> tuple:
    """Returns (action_id, a short human-readable description)."""
    action_id = _gate.propose(TYPE_CREATE_FILE, {"path": path, "content": content})
    return action_id, f"create {path}"


def propose_run_command(command: str) -> tuple:
    action_id = _gate.propose(TYPE_RUN_COMMAND, {"command": command})
    return action_id, f"run: {command}"


# ─────────────────────────────────────────────
# APPROVING / DENYING (thin wrappers over the shared gate)
# ─────────────────────────────────────────────

def approve_and_execute(action_id: str) -> str:
    """
    The ONLY way anything touches disk or runs a process. The shared gate atomically
    claims the action (so two near-simultaneous approvals can never both execute),
    runs it, and records and reports the REAL outcome. See shared/action_gate.py.
    """
    return _gate.approve_and_execute(action_id)


def deny_action(action_id: str) -> str:
    return _gate.deny_action(action_id)


def list_pending() -> str:
    """Everything of CIPHER's still waiting for approval, one per line."""
    return _gate.list_pending()