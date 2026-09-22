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

load_dotenv(override=True)  # Lesson #12: .env must win over a stale system env var
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")
GEMINI_MODEL = "gemini-2.5-flash"

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
    response = client.models.generate_content_stream(
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