"""
CIPHER — Phase 1, core chat only.
No memory (Lesson #2/#3 deferred to their own tested increment).
No real file-write/command-execution (Decision: gated behind a future
NEXUS approval workflow — Phase 2 — same safety pattern as the old
system, not built yet here).
Web search only fires when the question actually needs current info.
"""
import re
from forge.shared.keyword_gate import should_refuse
from forge.shared.agent_topics import CIPHER_NON_TOPIC, CIPHER_INTENT, CIPHER_SEARCH_TRIGGERS
from forge.shared.keyword_gate import contains_keyword
from forge.shared.web_search import web_search, WEB_SEARCH_FAILED_PREFIX
from forge.shared.model_client import stream_gemini
from forge.agents.cipher.prompt import CIPHER_PROMPT

REFUSAL_MESSAGE = "I'm C.I.P.H.E.R. — I handle programming tasks only. For that, please consult the appropriate NEXUS agent."


def needs_search(message: str) -> bool:
    return contains_keyword(message, CIPHER_SEARCH_TRIGGERS)


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
    Yields text chunks. Caller owns history persistence (no memory here).
    """
    if should_refuse(message, CIPHER_NON_TOPIC, CIPHER_INTENT):
        yield REFUSAL_MESSAGE
        return

    full_message = message
    if needs_search(message):
        search_result = web_search(message)
        if search_result.startswith(WEB_SEARCH_FAILED_PREFIX):
            full_message = f"{search_result}\n\nUser says: {message}"
        else:
            full_message = f"{search_result}\n\nUser says: {message}"

    messages = list(history) if history else []
    messages.append({"role": "user", "content": full_message})

    full_response = ""
    for chunk in stream_gemini(CIPHER_PROMPT, messages, location):
        full_response += chunk
        yield chunk

    # (caller is responsible for saving `strip_unexecuted_action_markers(full_response)`
    # to its own history — this function doesn't persist anything itself)