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
import logging
import os
import threading
import time
from datetime import datetime
from dotenv import load_dotenv
from google import genai
from google.genai import types
from google.genai import errors as genai_errors
import ollama
import anthropic
from shared.api_budget import get_balance, record_usage, check_and_notify_hard_stop, get_agent_default_tiers

load_dotenv(override=True)  # Lesson #12: .env must win over a stale system env var
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
# Gemini model names and the thinking effort are plain settings (override them in .env, no code change needed):
#   GEMINI_MODEL           the model tried first            (default gemini-3.6-flash)
#   GEMINI_FALLBACK_MODEL  used when the first one is out of free requests or overloaded
#                          (default gemini-3.5-flash-lite; an EMPTY value turns the fallback off)
#   GEMINI_THINKING_LEVEL  minimal | low | medium | high    (default low)
GEMINI_MODEL = os.getenv("GEMINI_MODEL") or "gemini-3.6-flash"
GEMINI_FALLBACK_MODEL = os.getenv("GEMINI_FALLBACK_MODEL", "gemini-3.5-flash-lite").strip()
GEMINI_THINKING_LEVEL = (os.getenv("GEMINI_THINKING_LEVEL") or "low").strip().lower()
GEMINI_COOLDOWN_SECONDS = 300      # after a model says "out of requests", skip it for 5 minutes
THINKING_LEVELS = ("minimal", "low", "medium", "high")
LAST_GEMINI_MODEL = None           # which model answered the most recent call (so a fallback is never invisible)
_log = logging.getLogger("forge.model_client")
_now = time.monotonic
_cooldown_until = {}               # model name -> time (by _now) before which we do not try it
_cooldown_lock = threading.Lock()

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
    "nexus":  "free_cloud",
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


def _check_gemini_history(messages) -> None:
    """The new Gemini models reject a conversation whose LAST turn is the assistant's, with a confusing 400.
    Fail early and clearly instead (nothing is sent)."""
    if not isinstance(messages, list) or not messages:
        raise ValueError("Gemini needs at least one message")
    for m in messages:
        if not isinstance(m, dict) or m.get("role") not in ("user", "assistant"):
            raise ValueError("every message needs a role of 'user' or 'assistant'")
    if messages[-1]["role"] != "user":
        raise ValueError("the conversation must END with a user message (Gemini rejects a last assistant turn)")


def _is_model_unavailable(exc) -> bool:
    """True for 'this model has no free requests left right now' (429) or 'overloaded' (503)."""
    return isinstance(exc, genai_errors.APIError) and getattr(exc, "code", None) in (429, 503)


def stream_gemini(system_prompt: str, messages: list, location: str = ""):
    """
    messages: list of {"role": "user"|"assistant", "content": str}
    Yields text chunks. Tries GEMINI_MODEL first; if that model is out of requests (429) or overloaded (503)
    BEFORE it has said anything, the same request goes to GEMINI_FALLBACK_MODEL. The model that answered is
    in LAST_GEMINI_MODEL, and a fallback is logged as a warning. An error after text has started, or any
    other kind of error, is raised as it is (never mixed with a second model's answer, never swallowed).
    """
    global LAST_GEMINI_MODEL
    _check_gemini_history(messages)
    level = GEMINI_THINKING_LEVEL
    if level not in THINKING_LEVELS:
        raise ValueError(f"GEMINI_THINKING_LEVEL must be one of {', '.join(THINKING_LEVELS)} (got {level!r})")

    now = datetime.now().strftime("%A, %B %d, %Y — %I:%M:%S %p")
    location_line = f"\nUser's current location: {location}" if location else ""
    full_system = system_prompt + f"\n\nCurrent date and time: {now}{location_line}"

    gemini_contents = []
    for msg in messages:
        role = "model" if msg["role"] == "assistant" else "user"  # conversion happens HERE only
        gemini_contents.append(types.Content(role=role, parts=[types.Part(text=msg["content"])]))

    config = types.GenerateContentConfig(
        system_instruction=full_system,
        max_output_tokens=8192,
        # No temperature: Gemini 3.x ignores it (Google recommends leaving sampling alone).
        thinking_config=types.ThinkingConfig(thinking_level=types.ThinkingLevel[level.upper()]),
    )

    models = [GEMINI_MODEL]
    if GEMINI_FALLBACK_MODEL and GEMINI_FALLBACK_MODEL != GEMINI_MODEL:
        models.append(GEMINI_FALLBACK_MODEL)
    with _cooldown_lock:
        t = _now()
        ready = [m for m in models if _cooldown_until.get(m, 0) <= t]
    candidates = ready or models      # if every model is resting, still try them (in order) rather than give up

    client = get_gemini_client()
    last_error = None
    for model in candidates:
        started = False
        try:
            response = client.models.generate_content_stream(  # type: ignore[call-overload]
                model=model, contents=gemini_contents, config=config)
            for chunk in response:
                if chunk.text:
                    started = True
                    yield chunk.text
        except Exception as e:
            if started or not _is_model_unavailable(e):
                raise
            with _cooldown_lock:
                _cooldown_until[model] = _now() + GEMINI_COOLDOWN_SECONDS
            _log.warning("Gemini model %s is unavailable right now (%s); trying the next one", model, getattr(e, "code", "?"))
            last_error = e
            continue
        if model != models[0]:
            _log.warning("Answered by the fallback model %s (%s was unavailable)", model, models[0])
        LAST_GEMINI_MODEL = model
        return
    raise last_error  # every model refused: fail loudly


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


OLLAMA_JSON_TIMEOUT = 90.0


def complete_ollama_json(system_prompt: str, user_text: str, timeout: float = OLLAMA_JSON_TIMEOUT) -> str:
    """
    Local tier, NOT streamed, JSON-only. For structured extraction (e.g.
    ATLAS turning "did chest, bench 3x8 at 135" into a log entry). Same local
    model as stream_ollama (Lesson #1: one place decides which model that is).
    temperature 0 so the same message extracts the same way every time.

    Returns the model's raw JSON text. ANY failure (Ollama not running, a
    timeout, a bad response) raises — it never returns partial or empty text
    dressed up as an answer (Lesson #12); the caller decides what to tell Joey.
    """
    client = ollama.Client(timeout=timeout)
    response = client.chat(
        model=OLLAMA_MODEL,
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_text},
        ],
        format="json",
        options={"temperature": 0, "num_predict": 1024},
    )
    return response.get("message", {}).get("content", "")


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