"""
CIPHER — Phase 1, core chat + memory + real, permission-gated actions.
Real file-write/command-execution is now wired in (Decision, this
session): CIPHER's own SAVE_FILE/RUN_COMMAND markers create a pending
action via agents/cipher/cipher_tools.py — NOTHING happens for real
until Joey explicitly approves that specific action. This is the ONLY
thing in FORGE that pauses for approval; a plain question to CIPHER,
even routed through NEXUS's future bridge, never pauses for anything.
Web search only fires when the question actually needs current info.
Memory search only fires when the message looks like it's referencing
something past (Decision, Session 4) — not on every message.
Memory saving is inline: CIPHER's own response carries a MEMORY_SAVE
marker when something is genuinely worth remembering (Decision:
option (b) — no extra classification API call per turn).
"""
import re
from shared.keyword_gate import should_refuse, contains_keyword
from shared.agent_topics import (
    CIPHER_NON_TOPIC, CIPHER_INTENT, CIPHER_SEARCH_TRIGGERS, CIPHER_MEMORY_TRIGGERS,
)
from shared.web_search import web_search, WEB_SEARCH_FAILED_PREFIX
from shared.model_client import stream_by_tier
from shared.memory_context import format_memory_context
from shared.cipher_memory import save_memory, search_memory
from agents.cipher.cipher_tools import propose_create_file, propose_run_command
from agents.cipher.prompt import CIPHER_PROMPT

REFUSAL_MESSAGE = "I'm C.I.P.H.E.R. — I handle programming tasks only. For that, please consult the appropriate NEXUS agent."

# Must match shared.memory_context.MEMORY_WORTHY_CATEGORIES — kept as its
# own set here (rather than imported) so an unrelated category added for
# another agent later can't silently start being accepted from CIPHER's
# own inline marker without a deliberate prompt.py update to match.
MEMORY_SAVE_CATEGORIES = {"decision", "correction", "preference", "project_fact"}
MEMORY_SAVE_PATTERN = re.compile(r"MEMORY_SAVE:\s*(\w+)\s*\|\s*(.+)")


def needs_search(message: str) -> bool:
    return contains_keyword(message, CIPHER_SEARCH_TRIGGERS)


def needs_memory_search(message: str) -> bool:
    return contains_keyword(message, CIPHER_MEMORY_TRIGGERS)


def extract_memory_saves(text: str) -> list[tuple[str, str]]:
    """
    Pulls out any MEMORY_SAVE: <category> | <content> line(s) CIPHER
    wrote inline. A category that isn't one of MEMORY_SAVE_CATEGORIES
    (e.g. a hallucinated word) is silently skipped rather than saved —
    this is the validation step, not shared.cipher_memory's filter,
    which is a second independent check.
    """
    saves = []
    for match in MEMORY_SAVE_PATTERN.finditer(text):
        category = match.group(1).strip().lower()
        content = match.group(2).strip()
        if category in MEMORY_SAVE_CATEGORIES and content:
            saves.append((category, content))
    return saves


def strip_memory_markers(text: str) -> str:
    """
    Removes MEMORY_SAVE lines from text before it's kept as saved
    conversation history — unlike SAVE_FILE/RUN_COMMAND, this marker
    IS fully functional (the save already happened), so it's removed
    outright rather than replaced with a "not yet built" placeholder.
    """
    return MEMORY_SAVE_PATTERN.sub("", text).rstrip()


SAVE_FILE_PATTERN = re.compile(r"SAVE_FILE:\s*(.+?)\s*\n<<<CODE_START>>>\n(.*?)\n<<<CODE_END>>>", re.DOTALL)
RUN_COMMAND_PATTERN = re.compile(r"RUN_COMMAND:\s*(.+)")


def extract_pending_actions(text: str) -> list[dict]:
    """
    Scans CIPHER's raw response for real SAVE_FILE/RUN_COMMAND markers
    and PROPOSES each one — this creates a pending action (nothing real
    happens yet) and returns what's now waiting on Joey's approval.
    Each dict: {"id": ..., "type": "create_file"/"run_command", "description": ...}
    """
    proposals = []
    for match in SAVE_FILE_PATTERN.finditer(text):
        path, content = match.group(1).strip(), match.group(2)
        action_id, description = propose_create_file(path, content)
        proposals.append({"id": action_id, "type": "create_file", "description": description})
    for match in RUN_COMMAND_PATTERN.finditer(text):
        command = match.group(1).strip()
        action_id, description = propose_run_command(command)
        proposals.append({"id": action_id, "type": "run_command", "description": description})
    return proposals


def strip_action_markers(text: str) -> str:
    """
    Replaces raw SAVE_FILE/RUN_COMMAND syntax in what gets saved to
    history with a short plain-English note instead of erasing it
    outright — a pending approval is real, ongoing state Joey may ask
    about later ("did I already approve that file?"), so history
    should still reflect that something was proposed, just not the raw
    machine syntax.
    """
    text = SAVE_FILE_PATTERN.sub(
        lambda m: f"(Proposed: create {m.group(1).strip()} — awaiting your approval.)", text
    )
    text = RUN_COMMAND_PATTERN.sub(
        lambda m: f"(Proposed: run `{m.group(1).strip()}` — awaiting your approval.)", text
    )
    return text


def strip_unexecuted_action_markers(text: str) -> str:
    """
    CREATE_BACKUP/WRITE_RECORD/TRACK_TASK belong to NEXUS's own
    completion-record system (not built in FORGE yet, for any agent) —
    unlike SAVE_FILE/RUN_COMMAND, which are now real (see
    extract_pending_actions/strip_action_markers above), these three
    still get replaced with a plain placeholder.
    """
    for marker in ["CREATE_BACKUP:", "WRITE_RECORD:", "TRACK_TASK:"]:
        text = re.sub(rf"{marker}.*", "(That capability isn't built yet in FORGE.)", text)
    return text


from typing import Optional

def stream_cipher(message: str, history: Optional[list] = None, location: str = "", model_tier: Optional[str] = None):
    """
    history: list of {"role": "user"|"assistant", "content": str}, or None
    Yields text chunks. Caller still owns conversation-history persistence.
    Permanent memory (decision/correction/preference/project_fact) is
    saved automatically inside this function when CIPHER's response
    carries a MEMORY_SAVE marker — the caller doesn't need to do
    anything extra for that part.
    """
    if should_refuse(message, CIPHER_NON_TOPIC, CIPHER_INTENT):
        yield REFUSAL_MESSAGE
        return

    context_blocks = []

    if needs_search(message):
        search_result = web_search(message)
        if search_result.startswith(WEB_SEARCH_FAILED_PREFIX):
            context_blocks.append(search_result)
        else:
            context_blocks.append(format_memory_context([search_result], label="web search results"))

    if needs_memory_search(message):
        retrieved = search_memory(message)
        if retrieved:
            context_blocks.append(format_memory_context(retrieved, label="memory"))

    full_message = "\n\n".join(context_blocks + [f"User says: {message}"]) if context_blocks else message

    messages = list(history) if history else []
    messages.append({"role": "user", "content": full_message})

    full_response = ""
    for chunk in stream_by_tier("cipher", model_tier, CIPHER_PROMPT, messages, location):
        full_response += chunk
        yield chunk

    for category, content in extract_memory_saves(full_response):
        save_memory(category, content)

    proposals = extract_pending_actions(full_response)
    for p in proposals:
        yield f"\n\n⏳ Waiting for your approval to {p['description']} (id: {p['id']})"

    # (caller is still responsible for saving
    # `strip_unexecuted_action_markers(strip_action_markers(strip_memory_markers(full_response)))`
    # to its own conversation history — this function persists MEMORY_SAVE
    # items and PROPOSES pending actions, but never executes them itself
    # and does not persist the turn)
