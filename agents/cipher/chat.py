"""
CIPHER — Phase 1, core chat + memory.
No real file-write/command-execution (Decision: gated behind a future
NEXUS approval workflow — Phase 2 — same safety pattern as the old
system, not built yet here).
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
from shared.model_client import stream_gemini
from shared.memory_context import format_memory_context
from shared.cipher_memory import save_memory, search_memory
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


def strip_unexecuted_action_markers(text: str) -> str:
    """
    Direct chat with CIPHER never actually saves files or runs commands
    (Decision: option (a) — real execution stays gated behind a future
    NEXUS approval workflow). Strip any marker CIPHER writes so it
    never sits in saved history as confusing, non-functional syntax.
    """
    text = re.sub(
        r"SAVE_FILE:.*?<<<CODE_START>>>.*?<<<CODE_END>>>",
        "(File save is only available through an approved NEXUS build task — not yet built in FORGE.)",
        text, flags=re.DOTALL,
    )
    for marker in ["RUN_COMMAND:", "CREATE_BACKUP:", "WRITE_RECORD:", "TRACK_TASK:"]:
        text = re.sub(rf"{marker}.*", "(That action requires an approved NEXUS build task — not yet built in FORGE.)", text)
    return text


from typing import Optional

def stream_cipher(message: str, history: Optional[list] = None, location: str = ""):
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
    for chunk in stream_gemini(CIPHER_PROMPT, messages, location):
        full_response += chunk
        yield chunk

    for category, content in extract_memory_saves(full_response):
        save_memory(category, content)

    # (caller is still responsible for saving
    # `strip_unexecuted_action_markers(strip_memory_markers(full_response))`
    # to its own conversation history — this function persists MEMORY_SAVE
    # items but does not persist the turn itself)
