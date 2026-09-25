"""
CIPHER tier-switching - L3 (real end-to-end, ALL THREE tiers).
Needs: real GEMINI_API_KEY and ANTHROPIC_API_KEY in .env, Ollama
running. This makes a REAL Sonnet 5 call - real (tiny) dollar cost.
Uses a throwaway budget DB so your real ledger isn't touched, but the
actual Anthropic charge is real either way.
Run with: python agents/cipher/test_cipher_tiers_l3.py
"""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath("."))

os.environ["FORGE_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="forge_budget_l3_"), "chat_history.db")
os.environ["CIPHER_MEMORY_PATH"] = tempfile.mkdtemp(prefix="cipher_memory_l3_")

from dotenv import load_dotenv
load_dotenv(override=True)

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

from agents.cipher import chat
from shared import api_budget

print("=== L3 REAL END-TO-END: ALL THREE TIERS ===\n")

print("--- Test 1: model_tier='local' (real Ollama, free) ---")
out = "".join(chat.stream_cipher("write a one-line python function to add two numbers", model_tier="local"))
print(f"  CIPHER said: {out[:150]}...")
check("real Local response is non-empty and looks like code", len(out) > 0 and "def " in out)

print("\n--- Test 2: model_tier='free_cloud' (real Gemini, free) ---")
out2 = "".join(chat.stream_cipher("write a one-line python function to subtract two numbers", model_tier="free_cloud"))
print(f"  CIPHER said: {out2[:150]}...")
check("real Free Cloud response is non-empty and looks like code", len(out2) > 0 and "def " in out2)

print("\n--- Test 3: model_tier='paid_cloud' (REAL Sonnet 5 - real tiny $ cost) ---")
balance_before = api_budget.get_balance()
out3 = "".join(chat.stream_cipher("write a one-line python function to multiply two numbers", model_tier="paid_cloud"))
balance_after = api_budget.get_balance()
print(f"  CIPHER said: {out3[:150]}...")
check("real Paid Cloud response is non-empty and looks like code", len(out3) > 0 and "def " in out3)
check(f"real usage was recorded (balance went from {balance_before} to {balance_after})",
      balance_after < balance_before)

print("\n--- Test 4: off-topic refusal never touches ANY tier, even paid_cloud ---")
balance_before_refusal = api_budget.get_balance()
out4 = list(chat.stream_cipher("what's a good recipe for dinner tonight", model_tier="paid_cloud"))
balance_after_refusal = api_budget.get_balance()
check("refusal happens with no model call and no budget spent even on paid_cloud",
      out4 == [chat.REFUSAL_MESSAGE] and balance_after_refusal == balance_before_refusal)

print("\n--- Test 5: memory + search still work correctly when routed through Paid Cloud ---")
api_budget_before = api_budget.get_balance()
save_out = "".join(chat.stream_cipher(
    "From now on, always use type hints in every function you write. Got it?",
    model_tier="paid_cloud"
))
print(f"  CIPHER said: {save_out}")
recall_out = "".join(chat.stream_cipher(
    "remember what I told you about type hints?",
    model_tier="paid_cloud"
))
print(f"  CIPHER said: {recall_out}")
check("real Paid Cloud response references type hints when asked to recall it",
      "type hint" in recall_out.lower())

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")