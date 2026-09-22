"""
CIPHER Phase 1 — L3 (real end-to-end, live APIs, your real keys).
No mocking here — this is "does it actually work for real."
Some checks print output for you to read and judge, not just assert.
"""
import sys, os
sys.path.insert(0, os.path.abspath("."))

from agents.cipher.chat import stream_cipher

def run_case(label, message, history=None):
    print(f"\n{'='*60}\n{label}\nMESSAGE: {message}\n{'-'*60}")
    chunks = []
    try:
        for chunk in stream_cipher(message, history=history):
            chunks.append(chunk)
        full = "".join(chunks)
        print(full)
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

# Case 1: real coding question, no search needed
run_case("CASE 1 — plain coding question (should NOT search)",
          "Write a Python function that checks if a number is prime.")

# Case 2: off-topic, should refuse before ever touching the model
run_case("CASE 2 — off-topic (should refuse instantly, no API call)",
          "What's the weather like today?")

# Case 3: the old substring bug, for real this time
run_case("CASE 3 — 'workout program' + coding intent (old bug: wrongly refused)",
          "Can you write a program in Python that logs my daily workouts to a JSON file?")

# Case 4: real search trigger — actually hits SerpApi + Gemini together
run_case("CASE 4 — needs current info (should trigger a REAL web search)",
          "What's the latest stable version of Python right now?")

# Case 5: multi-turn — does it actually use the history it's given?
history = [
    {"role": "user", "content": "My favorite language is Rust."},
    {"role": "assistant", "content": "Good choice — Rust's ownership model is great for safety."}
]
run_case("CASE 5 — uses conversation history correctly",
          "What did I just say my favorite language was?", history=history)

print(f"\n{'='*60}\nDone. Read each response above and confirm:")
print("  1. Case 1: real, correct, working prime-check code")
print("  2. Case 2: a clean refusal, NOT a weather answer")
print("  3. Case 3: real code, NOT a wrongful refusal")
print("  4. Case 4: a real current Python version, not a guess from training data")
print("  5. Case 5: correctly says 'Rust'")