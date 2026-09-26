"""
NEXUS Phase 2 core chat — L3 (real end-to-end, live APIs, your real keys).
No mocking here — this is "does it actually work for real."
Some checks print output for you to read and judge, not just assert.

Because NEXUS searches on nearly every message by design, every case
below spends one real SerpApi call plus one real Gemini call.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

from agents.nexus.chat import stream_nexus, strip_unexecuted_action_markers

def run_case(label, message, history=None):
    print(f"\n{'='*60}\n{label}\nMESSAGE: {message}\n{'-'*60}")
    chunks = []
    try:
        for chunk in stream_nexus(message, history=history, location="South Bend, Indiana"):
            chunks.append(chunk)
        full = "".join(chunks)
        print("RAW (as actually streamed live):")
        print(full)
        cleaned = strip_unexecuted_action_markers(full)
        if cleaned != full:
            print(f"{'-'*60}\nCLEANED (what would be saved to history):")
            print(cleaned)
        print(f"{'-'*60}\n[{len(full)} chars, {len(chunks)} chunks, no crash]")
        return full
    except Exception as e:
        print(f"[CRASHED] {type(e).__name__}: {e}")
        return None


print("Checking .env loaded correctly...")
from shared.model_client import GEMINI_API_KEY
from shared.web_search import SERPAPI_KEY
print(f"GEMINI_API_KEY loaded: {'yes, ' + GEMINI_API_KEY[:6] + '...' if GEMINI_API_KEY else 'NO — MISSING'}")
print(f"SERPAPI_KEY loaded: {'yes, ' + SERPAPI_KEY[:6] + '...' if SERPAPI_KEY else 'NO — MISSING'}")

# Case 1: plain everyday message — confirms voice, confirms it still
# searches even though nothing about this needs current info (the
# "search nearly everything" behavior, working as designed).
run_case("CASE 1 — plain everyday message (voice + always-searches check)",
          "I've had a long day, any tips for winding down tonight?")

# Case 2: real weather question — confirms the location-aware query
# actually gets used and a real, current answer comes back.
run_case("CASE 2 — real weather question (location-aware search)",
          "What's the weather looking like?")

# Case 3: something that would trigger a bridge/tool marker in the old
# system (reminders) — no bridge/reminder system exists yet, so this
# checks strip_unexecuted_action_markers() against a REAL model
# response, not the mocked one from L2.
run_case("CASE 3 — reminder request (old system would emit SET_REMINDER)",
          "Remind me to call my mom tomorrow.")

# Case 4: something that would trigger an ASK_* bridge in the old
# system (finance) — checks the CRITICAL RULE against inventing
# numbers, and checks marker stripping on a bridge-style command.
run_case("CASE 4 — finance question (old system would emit ASK_ASSET)",
          "How much money do I have in my account right now?")

# Case 5: multi-turn — does it actually use the history it's given?
history = [
    {"role": "user", "content": "My dog's name is Biscuit."},
    {"role": "assistant", "content": "Biscuit — I'll remember that, sir."}
]
run_case("CASE 5 — uses conversation history correctly",
          "What's my dog's name again?", history=history)

print(f"\n{'='*60}\nDone. Read each response above and confirm:")
print("  1. Case 1: sounds like Alfred (measured, warm, dry wit, maybe 'sir'/'Master Joey'), real answer, no crash")
print("  2. Case 2: a real, current weather answer for South Bend, Indiana — not a guess")
print("  3. Case 3: RAW likely contains a SET_REMINDER: line (that's expected/fine) — CLEANED must NOT contain it, must show the placeholder instead")
print("  4. Case 4: must NOT invent a dollar figure — should say it doesn't have that data (per its own CRITICAL RULES); RAW may contain ASK_ASSET:, CLEANED must not")
print("  5. Case 5: correctly says 'Biscuit'")