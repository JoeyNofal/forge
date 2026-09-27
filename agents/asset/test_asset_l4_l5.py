"""
ASSET core chat - L4 (sustained/concurrency) + L5 (extreme/breaking).
Mocked model, synthetic financial data - real numbers already proven
correct in L3; this targets robustness, not accuracy.
Run with: python agents/asset/test_asset_l4_l5.py
"""
import os, sys, threading, types
sys.path.insert(0, os.path.abspath("."))

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

fake_model_client = types.ModuleType("shared.model_client")
def fake_stream_ollama(system_prompt, messages, location=""):
    yield f"RESPONSE_TO[{messages[-1]['content']}]"
fake_model_client.stream_ollama = fake_stream_ollama  # type: ignore[attr-defined]
sys.modules["shared.model_client"] = fake_model_client

fake_web_search = types.ModuleType("shared.web_search")
fake_web_search.WEB_SEARCH_FAILED_PREFIX = "[WEB_SEARCH_FAILED]"  # type: ignore[attr-defined]
fake_web_search.web_search = lambda query, num_results=3: f"Web search results:\n\n1. Fake result for {query}"  # type: ignore[attr-defined]
sys.modules["shared.web_search"] = fake_web_search

fake_asset_memory = types.ModuleType("shared.asset_memory")
fake_asset_memory.save_conversation_turn = lambda msg, resp, category="conversation": None  # type: ignore[attr-defined]
fake_asset_memory.search_memory = lambda query, n_results=5: []  # type: ignore[attr-defined]
sys.modules["shared.asset_memory"] = fake_asset_memory

from agents.asset import chat
from agents.asset import asset_tools

SYNTHETIC_DATA = {
    "accounts": {"vault": 1000.0, "flex": -50.0, "funds": 5000.0, "cc": 200.0, "cc2": -30.0, "car_loan": 8000.0, "brex": 500.0},
    "settings": {"carLoanInitial": 15000, "carLoanMonthlyTarget": 300, "ccLimit": 5000, "ccTargetMin": 0, "ccTargetMax": 500,
                 "cc2Limit": 3000, "cc2TargetMin": 0, "cc2TargetMax": 300, "flexFloor": 500, "carFundTarget": 300,
                 "carFundMinimum": 1000, "creditScoreTarget": 750, "creditScoreTarget2": 750, "brexStartingBalance": 1000},
    "transactions": [{"date": "2026-09-01", "amount": -45.0, "accountId": "vault", "description": "Groceries", "type": "purchase"}],
    "paychecks": [{"date": "2026-09-15", "grossPay": 3000, "netPay": 2200, "taxes": {"federal": 500}, "deductions": {"401k": 300}}],
    "creditScores": [{"date": "2026-08-01", "score": 720, "source": "Chase"}],
    "groceries": {"2026-08": 400.0, "2026-09": 380.0},
    "fixedExpenses": [{"frequency": "monthly", "amount": 1200}],
    "fundsSubAccounts": {"savingsFund": 3000.0},
}
asset_tools.load_data = lambda: SYNTHETIC_DATA

print("=== L4 SUSTAINED / CONCURRENCY ===\n")

print("--- Test 1: 100 sequential calls - zero crashes, zero empty responses ---")
crashes = 0
empties = 0
for i in range(100):
    try:
        out = "".join(chat.stream_asset(f"what's my net worth, scenario {i}?"))
        if not out:
            empties += 1
    except Exception:
        crashes += 1
check("100 sequential calls: zero crashes", crashes == 0, f"{crashes} crashed")
check("100 sequential calls: zero empty responses", empties == 0, f"{empties} empty")

print("\n--- Test 2: 20 concurrent calls with DIFFERENT messages - no cross-talk ---")
concurrent_results = {}
lock = threading.Lock()

def worker(n):
    out = "".join(chat.stream_asset(f"what's my income summary, case {n}?"))
    with lock:
        concurrent_results[n] = out

threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
for t in threads: t.start()
for t in threads: t.join()

no_crosstalk = all(f"case {n}" in concurrent_results.get(n, "") for n in range(20))
check("20 concurrent calls: each got its own response, no cross-talk", no_crosstalk and len(concurrent_results) == 20)

print("\n--- Test 3: 30 sequential real net-worth calculations - deterministic, no drift ---")
net_worth_outputs = set()
for _ in range(30):
    net_worth_outputs.add(asset_tools.get_net_worth())
check("net worth calculation is fully deterministic across repeated calls", len(net_worth_outputs) == 1)

print("\n=== L5 EXTREME / BREAKING ===\n")

print("--- Test 4: empty message ---")
try:
    out = "".join(chat.stream_asset(""))
    check("empty string message doesn't crash", True)
except Exception as e:
    check("empty string message doesn't crash", False, f"{type(e).__name__}: {e}")

print("--- Test 5: 50,000-char message ---")
try:
    out = "".join(chat.stream_asset("tell me about my net worth " + ("x" * 50000)))
    check("50,000-char message doesn't crash", True)
except Exception as e:
    check("50,000-char message doesn't crash", False, f"{type(e).__name__}: {e}")

print("--- Test 6: unicode/emoji message ---")
try:
    out = "".join(chat.stream_asset("what's my net worth 💰 and 日本語 test"))
    check("unicode/emoji message doesn't crash", True)
except Exception as e:
    check("unicode/emoji message doesn't crash", False, f"{type(e).__name__}: {e}")

print("--- Test 7: None as message fails LOUDLY, not silently ---")
raised_clearly = False
try:
    "".join(chat.stream_asset(None))  # type: ignore[arg-type]
except (TypeError, AttributeError):
    raised_clearly = True
except Exception:
    raised_clearly = False
check("passing None as message fails loudly (clear error), not silently", raised_clearly)

print("--- Test 8: malformed financial data (missing keys entirely) doesn't crash tools ---")
asset_tools.load_data = lambda: {}
try:
    out = "".join(chat.stream_asset("what's my net worth?"))
    check("completely empty financial data doesn't crash - degrades gracefully", True)
except Exception as e:
    check("completely empty financial data doesn't crash - degrades gracefully", False, f"{type(e).__name__}: {e}")
asset_tools.load_data = lambda: SYNTHETIC_DATA

print("--- Test 9: malformed data - a transaction missing 'amount' entirely ---")
malformed_data = dict(SYNTHETIC_DATA)
malformed_data["transactions"] = [{"date": "2026-09-01", "accountId": "vault", "description": "Weird one", "type": "purchase"}]
asset_tools.load_data = lambda: malformed_data
try:
    out = "".join(chat.stream_asset("what are my recent transactions?"))
    check("a transaction missing 'amount' doesn't crash (defaults handled)", True)
except Exception as e:
    check("a transaction missing 'amount' doesn't crash (defaults handled)", False, f"{type(e).__name__}: {e}")
asset_tools.load_data = lambda: SYNTHETIC_DATA

print("--- Test 10: a real model/Ollama failure propagates clearly, isn't silently swallowed ---")
def broken_stream_ollama(system_prompt, messages, location=""):
    raise ConnectionError("simulated Ollama outage")
    yield  # pragma: no cover
original_stream_ollama = chat.stream_ollama
chat.stream_ollama = broken_stream_ollama
propagated = False
try:
    "".join(chat.stream_asset("what's my net worth?"))
except ConnectionError:
    propagated = True
check("a real Ollama failure propagates clearly, isn't silently swallowed", propagated)
chat.stream_ollama = original_stream_ollama

print("--- Test 11: refusal gate still intact after all this abuse ---")
out11 = "".join(chat.stream_asset("what's the weather like"))
check("refusal gate still works correctly after extreme-input tests", out11 == chat.REFUSAL_MESSAGE)

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")