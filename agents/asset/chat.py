"""
ASSET — Phase 3, core chat.

PERMANENTLY LOCAL-ONLY (Core Reference: "the one privacy-driven
exception, never part of the switcher") — this is a hard rule, not a
default. Unlike every other agent, stream_asset() has no model_tier
parameter at all; it always calls stream_ollama() directly, never
stream_by_tier(). Sensitive financial data never has a path to a cloud
call from this file.

Refusal gate reuses shared/agent_topics.py's ASSET_NON_TOPIC/ASSET_INTENT
(already pulled into Phase 0, word-boundary-safe via keyword_gate.py's
should_refuse() — same mechanism CIPHER uses).

Tool selection: ASSET_TOOL_KEYWORDS decides which of the 9 real
financial data-getters fire, based on the message — not an elif chain,
every matching tool runs, same as the old system, but word-boundary
safe now (Lesson #6; the old code used plain substring checks here).

A load_data() failure is no longer silently swallowed by a bare
`except: pass` the way the old code did (Lesson #2/#12) — it's caught
ONCE here and turned into an explicit note in the context, so ASSET's
own prompt instruction ("If specific data was not provided, say it
plainly") actually has something真 true to work with instead of quietly
answering off of whatever partial context happened to load.

Web search is narrow and trigger-gated (ASSET_NEWS_TRIGGERS) — "only
used when Joey explicitly asks for news or rates" per the old code's
own comment, unlike NEXUS's near-universal search. Uses shared/web_search.py
(the same tested SerpApi wrapper CIPHER/NEXUS use) instead of ASSET's
old separate, untested duplicate implementation (Lesson #9).

Memory saving reuses the old system's own real design (already
correctly filtered, just fixed for Lesson #6) — not every turn, only
when the message contains something genuinely worth remembering.
"""
import re
from typing import Optional

from shared.keyword_gate import should_refuse, contains_keyword
from shared.agent_topics import (
    ASSET_NON_TOPIC, ASSET_INTENT, ASSET_TOOL_KEYWORDS, ASSET_NEWS_TRIGGERS,
)
from shared.web_search import web_search, WEB_SEARCH_FAILED_PREFIX
from shared.model_client import stream_ollama
from shared.asset_memory import save_conversation_turn, search_memory
from agents.asset.prompt import ASSET_PROMPT
from agents.asset import asset_tools

REFUSAL_MESSAGE = "That is not what I do. Talk to NEXUS."

MEMORY_WORTHY_KEYWORDS = [
    "goal", "want to", "plan to", "decided", "decide", "priority",
    "prefer", "instead", "from now on", "always", "never",
    "remember this", "important", "save for", "saving for",
]

_TOOL_FUNCTIONS = {
    "spending_summary": lambda: asset_tools.get_spending_summary(months_back=1),
    "net_worth": lambda: asset_tools.get_net_worth(),
    "recent_transactions": lambda: asset_tools.get_recent_transactions(limit=5),
    "income_summary": lambda: asset_tools.get_income_summary(),
    "savings_rate": lambda: asset_tools.get_savings_rate(),
    "credit_score": lambda: asset_tools.get_credit_score_history(),
    "grocery_history": lambda: asset_tools.get_grocery_history(),
    "emergency_fund": lambda: asset_tools.get_emergency_fund_status(),
}


def build_tool_context(message: str) -> str:
    """
    Always includes the static account settings (Decision, carried from
    old system: "these almost never change, so there's no reason to
    ever ask Joey for them or guess"). On top of that, every real data
    tool whose keywords match the message also fires — word-boundary
    safe (Lesson #6), not an elif chain.

    A real load_data() failure propagates up from here rather than
    being caught and hidden — the CALLER (stream_asset) decides how to
    present that to Joey, exactly once, instead of each of the 9 tools
    silently doing their own thing.
    """
    context = asset_tools.get_account_settings() + "\n\n"
    for tool_name, keywords in ASSET_TOOL_KEYWORDS.items():
        if contains_keyword(message, keywords):
            context += _TOOL_FUNCTIONS[tool_name]() + "\n\n"
    return context


def stream_asset(message: str, history: Optional[list] = None, location: str = ""):
    """
    history: list of {"role": "user"|"assistant", "content": str}, or None
    Yields text chunks. No model_tier parameter — ASSET is ALWAYS local
    (Decision, hard rule, not a default).
    """
    if should_refuse(message, ASSET_NON_TOPIC, ASSET_INTENT):
        yield REFUSAL_MESSAGE
        return

    context_blocks = []

    try:
        context_blocks.append(f"[Live financial data:\n{build_tool_context(message)}]")
    except RuntimeError as e:
        # A real, specific failure (Lesson #12) — not swallowed the way
        # the old code's bare `except: pass` did. ASSET's own prompt
        # already instructs it to say plainly when data isn't provided.
        context_blocks.append(f"[FINANCIAL DATA UNAVAILABLE: {e}]")

    if contains_keyword(message, ASSET_NEWS_TRIGGERS):
        search_result = web_search(message)
        if search_result.startswith(WEB_SEARCH_FAILED_PREFIX):
            context_blocks.append(search_result)
        else:
            context_blocks.append(f"[Web search results:\n{search_result}]")

    memory_query = f"{message} financial goals priorities decisions preferences"
    memory_results = search_memory(memory_query)
    if memory_results:
        joined = "\n".join(memory_results)
        context_blocks.append(
            "[Background memory — older context from past conversations, which may "
            "or may not be from THIS chat. If Joey asks what he just said, or "
            "references something from earlier in this SAME conversation, trust the "
            "actual conversation history over this background block:\n"
            f"{joined}]"
        )

    full_message = "\n\n".join(context_blocks + [f"Joey's message: {message}"])

    messages = list(history) if history else []
    messages.append({"role": "user", "content": full_message})

    full_response = ""
    for chunk in stream_ollama(ASSET_PROMPT, messages, location):
        full_response += chunk
        yield chunk

    if contains_keyword(message, MEMORY_WORTHY_KEYWORDS):
        save_conversation_turn(message, full_response)