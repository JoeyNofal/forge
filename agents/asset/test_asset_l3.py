"""
ASSET - L3 (real end-to-end, real Ollama, real financial-tracker-data.json).
No mocks anywhere except memory, which uses a throwaway temp path so
this test run doesn't mix with any real day-to-day ASSET memory later.
Real financial figures WILL appear in your own terminal output below -
none of that gets sent anywhere, it's local to your machine.
Run with: python agents/asset/test_asset_l3.py
"""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath("."))

os.environ["ASSET_MEMORY_PATH"] = tempfile.mkdtemp(prefix="asset_memory_l3_")

from dotenv import load_dotenv
load_dotenv(override=True)

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

from agents.asset import chat

def run_case(label, message, history=None):
    print(f"\n{'='*60}\n{label}\nMESSAGE: {message}\n{'-'*60}")
    out = "".join(chat.stream_asset(message, history=history))
    print(out)
    print(f"{'-'*60}")
    return out

print("=== L3 REAL END-TO-END (real Ollama, real financial data) ===")

# --- 1. Real net worth question - eyeball this against what you know is true ---
out1 = run_case("CASE 1 — real net worth", "What's my net worth right now?")
check("real response is non-empty", len(out1) > 0)

# --- 2. Real spending/grocery question - tool selection + real numbers ---
out2 = run_case("CASE 2 — real grocery spending", "How much have I spent on groceries recently?")
check("real response is non-empty", len(out2) > 0)

# --- 3. Refusal still works on the real path ---
out3 = run_case("CASE 3 — off-topic refusal", "What's the weather like today?")
check("real off-topic message still refuses correctly", out3 == chat.REFUSAL_MESSAGE)

# --- 4. The 'car loan' false-refusal bug, confirmed fixed for real ---
out4 = run_case("CASE 4 — car loan (real regression check)", "What's my current car loan balance?")
check("'car loan' question does NOT wrongly refuse (real regression check)", out4 != chat.REFUSAL_MESSAGE)

# --- 5. The 'spend on food' false-refusal bug, confirmed fixed for real ---
out5 = run_case("CASE 5 — spend on food (real regression check)", "How much do I typically spend on food each month?")
check("'spend on food' question does NOT wrongly refuse (real regression check)", out5 != chat.REFUSAL_MESSAGE)

# --- 6. Real news/rate trigger - a real SerpApi call ---
out6 = run_case("CASE 6 — real news trigger", "What's happening with mortgage rates lately?")
check("real news-triggered response is non-empty", len(out6) > 0)

# --- 7. Real multi-turn memory (Ollama embeddings, real save + recall) ---
print(f"\n{'='*60}\nCASE 7 — real memory save + recall\n{'-'*60}")
out7a = run_case("  7a - stating a goal", "From now on, my goal is to build a small cash buffer before the end of the year.")
out7b = run_case("  7b - recalling it", "What did I just tell you my goal was?")
check("ASSET recalled the real stated goal via real memory retrieval",
      "buffer" in out7b.lower() or "cash" in out7b.lower() or "year" in out7b.lower())

print(f"\n{'='*60}")
print("Read through the outputs above yourself and confirm:")
print("  - Case 1/2: numbers match what you actually know to be true")
print("  - Case 3: correctly refused")
print("  - Case 4/5: correctly did NOT refuse, gave a real answer")
print("  - Case 6: sounds like real, current information, not stale training data")
print("  - Voice throughout: controlled, precise, Walter White/Heisenberg energy")
print("  - No invented numbers anywhere - if something wasn't in the data, it should say so plainly")

print("\n=== SUMMARY (mechanical checks only - read the real content above yourself) ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")