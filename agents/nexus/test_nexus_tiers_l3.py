"""
NEXUS tier-switching - L3 (real end-to-end, ALL THREE tiers).
No new code here - shared/model_client.py's stream_by_tier and
shared/api_budget.py's record_usage were already built agent-generic
by CIPHER's Session 4. This test exists to CONFIRM that's actually
true for NEXUS, not to introduce anything new.
Needs: real GEMINI_API_KEY and ANTHROPIC_API_KEY in .env, Ollama
running. This makes a REAL Sonnet 5 call - real (tiny) dollar cost.
Uses a throwaway budget DB so your real ledger isn't touched, but the
actual Anthropic charge is real either way.
Run with: python agents/nexus/test_nexus_tiers_l3.py
"""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath("."))

os.environ["FORGE_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="forge_budget_l3_"), "chat_history.db")
os.environ["NEXUS_MEMORY_PATH"] = tempfile.mkdtemp(prefix="nexus_memory_l3_")

from dotenv import load_dotenv
load_dotenv(override=True)

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

from agents.nexus import chat
from shared import api_budget

print("=== L3 REAL END-TO-END: ALL THREE TIERS ===\n")

print("--- Test 1: model_tier='local' (real Ollama, free) ---")
out = "".join(chat.stream_nexus("give me one quick tip for staying organized", model_tier="local"))
print(f"  NEXUS said: {out[:150]}...")
check("real Local response is non-empty", len(out) > 0)

print("\n--- Test 2: model_tier='free_cloud' (real Gemini, free - NEXUS's actual live default) ---")
out2 = "".join(chat.stream_nexus("give me one quick tip for staying focused", model_tier="free_cloud"))
print(f"  NEXUS said: {out2[:150]}...")
check("real Free Cloud response is non-empty", len(out2) > 0)

print("\n--- Test 3: model_tier='paid_cloud' (REAL Sonnet 5 - real tiny $ cost) ---")
balance_before = api_budget.get_balance()
out3 = "".join(chat.stream_nexus("give me one quick tip for staying motivated", model_tier="paid_cloud"))
balance_after = api_budget.get_balance()
print(f"  NEXUS said: {out3[:150]}...")
check("real Paid Cloud response is non-empty", len(out3) > 0)
check(f"real usage was recorded (balance went from {balance_before} to {balance_after})",
      balance_after < balance_before)

print("\n--- Test 4: usage is correctly attributed to 'nexus', not another agent ---")
conn = api_budget._get_conn()
c = conn.cursor()
c.execute("SELECT agent FROM api_usage ORDER BY id DESC LIMIT 1")
last_agent = c.fetchone()[0]
conn.close()
check(f"the real Paid Cloud call just recorded was logged under agent='nexus'", last_agent == "nexus", f"got agent='{last_agent}'")

print("\n--- Test 5: memory + search still work correctly when routed through Paid Cloud ---")
save_out = "".join(chat.stream_nexus(
    "From now on, always double-check my spelling of Youssef when you write my name. Got it?",
    model_tier="paid_cloud"
))
print(f"  NEXUS said: {save_out}")
recall_out = "".join(chat.stream_nexus(
    "what did I just ask you to always double-check?",
    model_tier="paid_cloud"
))
print(f"  NEXUS said: {recall_out}")
check("real Paid Cloud response references spelling/name when asked to recall it",
      "spell" in recall_out.lower() or "youssef" in recall_out.lower() or "name" in recall_out.lower())

print("\n--- Test 6: NEXUS still fully unrestricted on paid_cloud too (no refusal gate anywhere) ---")
out6 = "".join(chat.stream_nexus("just saying hi, nothing needed", model_tier="paid_cloud"))
check("no refusal on paid_cloud (NEXUS has no refusal gate, unlike CIPHER)", len(out6) > 0)

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")