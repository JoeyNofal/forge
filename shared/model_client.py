"""
Gemini (Free Cloud tier) streaming client. Hardcoded to this one tier
for Phase 1 — Local and Paid Cloud tiers get added as their own tested
increment later, not guessed at now.

Lesson #11: Gemini's "model" role name is converted ONLY inside this
one function, at the single point where Gemini's API is actually
called. Every caller outside this file uses "user"/"assistant" only —
never let "model" leak into agent-level code.

On real failure, this raises — it does NOT silently fall back to
anything. A silent fallback is exactly what hid the Lesson #11 bug for
an unknown period of time last time; better to fail loud here until a
real fallback tier is actually built and tested.
"""
import os
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
import ollama
import anthropic
from shared.api_budget import get_balance, record_usage, check_and_notify_hard_stop, get_agent_default_tiers

load_dotenv(override=True)  # Lesson #12: .env must win over a stale system env var
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"

ANTHROPIC_API_KEY = os.getenv("ANTHROPIC_API_KEY")
ANTHROPIC_MODEL = "claude-sonnet-5"
OLLAMA_MODEL = "gemma3:12b"

_claude_client = None

def get_claude_client():
    global _claude_client
    if _claude_client is None:
        if not ANTHROPIC_API_KEY:
            raise ValueError(
                "ANTHROPIC_API_KEY is not set. Check your .env file - "
                "this must be loaded explicitly, never silently picked up "
                "by an SDK's own fallback behavior."
            )
        _claude_client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY, timeout=60.0, max_retries=1)
    return _claude_client

# Which tier each agent uses when no explicit model_tier is passed for a
# given message. Ported from the old system's proven default map.
# ASSET is deliberately excluded — it's permanently local-only, and
# never calls stream_by_tier at all (privacy rule, not a routing choice).
AGENT_DEFAULT_TIERS_DEFAULT = {
    "nexus":  "paid_cloud",
    "cipher": "paid_cloud",
    "atlas":  "free_cloud",
    "drive":  "free_cloud",
    "flame":  "free_cloud",
    "case":   "free_cloud",
    "stock":  "free_cloud",
    "pulse":  "free_cloud",
}

def get_effective_default_tier(agent: str) -> str:
    """Live default tier for an agent — checks for a dashboard override
    first (stored in shared.api_budget's app_settings, read fresh every
    call), falls back to the hardcoded default above."""
    overrides = get_agent_default_tiers()
    if agent in overrides and overrides[agent] in ("local", "free_cloud", "paid_cloud"):
        return overrides[agent]
    return AGENT_DEFAULT_TIERS_DEFAULT.get(agent, "free_cloud")

_client = None

def get_gemini_client():
    global _client
    if _client is None:
        if not GEMINI_API_KEY:
            raise ValueError(
                "GEMINI_API_KEY is not set. Check your .env file — "
                "this must be loaded explicitly, never silently picked up "
                "by an SDK's own fallback behavior."
            )
        _client = genai.Client(api_key=GEMINI_API_KEY)
    return _client


def stream_gemini(system_prompt: str, messages: list, location: str = ""):
    """
    messages: list of {"role": "user"|"assistant", "content": str}
    Yields text chunks.
    """
    now = datetime.now().strftime("%A, %B %d, %Y — %I:%M:%S %p")
    location_line = f"\nUser's current location: {location}" if location else ""
    full_system = system_prompt + f"\n\nCurrent date and time: {now}{location_line}"

    gemini_contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"  # conversion happens HERE only
        gemini_contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    client = get_gemini_client()
    response = client.models.generate_content_stream(  # type: ignore[call-overload]
        model=GEMINI_MODEL,
        contents=gemini_contents,
        config=types.GenerateContentConfig(
            system_instruction=full_system,
            temperature=0.7,
            max_output_tokens=8192,
        )
    )
    for chunk in response:
        if chunk.text:
            yield chunk.text


def stream_ollama(system_prompt: str, messages: list, location: str = ""):
    """
    Local tier. messages: list of {"role": "user"|"assistant", "content": str}.
    """
    now = datetime.now().strftime("%A, %B %d, %Y — %I:%M:%S %p")
    location_line = f"\nUser's current location: {location}" if location else ""
    time_context = f"\n\nCurrent date and time: {now}{location_line}"
    full_messages = [{"role": "system", "content": system_prompt + time_context}] + messages
    stream = ollama.chat(
        model=OLLAMA_MODEL,
        messages=full_messages,
        stream=True,
        options={"num_predict": 1024},
    )
    for chunk in stream:
        text = chunk.get("message", {}).get("content", "")
        if text:
            yield text


def stream_claude(system_prompt: str, messages: list, location: str = "", agent: str = "cipher"):
    """
    Paid Cloud tier. Budget-gated: a real $0 balance is a deliberate,
    visible hard stop (Joey wants to notice, not silently degrade) —
    NOT the same thing as a real API failure below, which falls back
    to Local, but only ever visibly (Lesson #11: a silent Paid->Local
    fallback is exactly what hid the role-name bug and undercounted
    real spend for an unknown period last time).
    """
    if get_balance() <= 0:
        if check_and_notify_hard_stop():
            pass  # a future NEXUS reminder-setting hook can go here later
        yield (
            "⚠️ I've maxed out today's Sonnet 5 budget, so I'm stopping here "
            "rather than falling back to Local. This resets tomorrow, or you "
            "can raise the daily cap yourself."
        )
        return

    now = datetime.now().strftime("%A, %B %d, %Y — %I:%M:%S %p")
    location_line = f"\nUser's current location: {location}" if location else ""
    dynamic_context = f"Current date and time: {now}{location_line}"

    system_blocks = [
        {"type": "text", "text": system_prompt, "cache_control": {"type": "ephemeral", "ttl": "1h"}},
        {"type": "text", "text": dynamic_context},
    ]

    claude_messages = [{"role": msg["role"], "content": msg["content"]} for msg in messages]

    try:
        client = get_claude_client()
        with client.messages.stream(
            model=ANTHROPIC_MODEL,
            max_tokens=4096,
            system=system_blocks,
            messages=claude_messages,  # type: ignore[arg-type]
            extra_headers={"anthropic-beta": "extended-cache-ttl-2025-04-11"},
        ) as stream:
            for text in stream.text_stream:
                yield text
            final_message = stream.get_final_message()

        input_tokens = final_message.usage.input_tokens
        output_tokens = final_message.usage.output_tokens
        cache_creation_tokens = getattr(final_message.usage, "cache_creation_input_tokens", 0) or 0
        cache_read_tokens = getattr(final_message.usage, "cache_read_input_tokens", 0) or 0
        warning_message = record_usage(agent, input_tokens, output_tokens, cache_creation_tokens, cache_read_tokens)
        if warning_message:
            yield f"\n\n{warning_message}"

    except Exception as e:
        # A REAL failure (rate limit, network, timeout) - NOT a budget cap,
        # that's handled above before this point. Visible fallback only —
        # never silent (Lesson #11).
        print(f"[CLAUDE ERROR] agent={agent} | {type(e).__name__}: {e} — falling back to Local")
        yield f"\n⚠️ Paid Cloud (Sonnet 5) failed, falling back to Local for this response.\n\n"
        yield from stream_ollama(system_prompt, messages, location)


def stream_by_tier(agent: str, tier: str | None, system_prompt: str, messages: list, location: str = ""):
    """
    Routes to the right tier. tier must be "local", "free_cloud",
    "paid_cloud", or None — None means "use this agent's live default"
    (get_effective_default_tier), same behavior as passing nothing at
    all from the dashboard.
    """
    effective_tier = tier or get_effective_default_tier(agent)

    if effective_tier == "local":
        yield from stream_ollama(system_prompt, messages, location)
    elif effective_tier == "paid_cloud":
        yield from stream_claude(system_prompt, messages, location, agent=agent)
    else:
        yield from stream_gemini(system_prompt, messages, location)