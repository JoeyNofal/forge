"""
ASSET memory - L3 (real end-to-end, real Ollama embeddings, no fakes).
Tests shared/asset_memory.py directly - stream_asset()'s own real
save+recall was already proven in agents/asset/test_asset_l3.py; this
targets the memory module's real semantic behavior in isolation.
Run with: python shared/test_asset_memory_l3.py
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

from shared import asset_memory

print("=== L3 REAL END-TO-END ===\n")

# --- 1. Real semantic search distinguishes genuinely different topics ---
print("--- Test 1: real Ollama embeddings rank the relevant memory first ---")
asset_memory.save_conversation_turn(
    "What's my emergency fund goal?",
    "Your goal is a two-month buffer, roughly $5,800.60.", category="goal"
)
asset_memory.save_conversation_turn(
    "What's the current mortgage rate?",
    "Current average 30-year mortgage rate is 6.728%.", category="market"
)
found = asset_memory.search_memory("what did I say my emergency fund target was")
print(f"  top result: {found[0] if found else None}")
check("the emergency-fund memory ranks ahead of the unrelated mortgage-rate one",
      bool(found) and ("emergency" in found[0].lower() or "buffer" in found[0].lower() or "5,800" in found[0]))

# --- 2. Multiple categories, all real, all retrievable ---
print("\n--- Test 2: real saves across multiple categories are all retrievable ---")
asset_memory.save_conversation_turn(
    "Any advice on the credit card balance?",
    "Pay the Freedom card down below the target range this month.", category="advice"
)
asset_memory.save_conversation_turn(
    "Can you summarize my spending this quarter?",
    "Spending trended up April through June, then declined.", category="summary"
)
advice_found = asset_memory.search_memory("credit card advice")
summary_found = asset_memory.search_memory("quarterly spending summary")
check("real 'advice' category save is retrievable", any("Freedom" in item for item in advice_found))
check("real 'summary' category save is retrievable", any("trended" in item for item in summary_found))

# --- 3. Real, larger content (a realistic full ASSET response) saves and reads back intact ---
print("\n--- Test 3: a realistic full-length real response saves and reads back correctly ---")
realistic_response = (
    "The net worth is $6,530.00 in assets against $8,250.00 in liabilities, "
    "for a net worth of negative $1,720.00. The car loan at $8,000 remains "
    "the largest liability. I recommend directing any surplus toward it "
    "before increasing the emergency fund contribution further."
)
asset_memory.save_conversation_turn("Give me the full financial picture.", realistic_response, category="summary")
found3 = asset_memory.search_memory("full financial picture net worth")
check("a realistic full-length real response saves and reads back intact",
      any("$-1,720" in item or "1,720" in item for item in found3))

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")