"""
FORGE tier-switching - L4 (sustained/concurrency) + L5 (extreme/
breaking). Ollama tests run for real (free, local); Claude/budget
tests stay mocked (no real Sonnet 5 spend at this stage).
Run with: python shared/test_model_client_l4_l5.py
"""
import ast, os, sys, tempfile, threading
sys.path.insert(0, os.path.abspath("."))

os.environ["FORGE_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="forge_budget_l4l5_"), "chat_history.db")

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

from shared import api_budget
from shared import model_client as mc

print("=== L4 SUSTAINED / CONCURRENCY ===\n")

print("--- Test 1: 20 simultaneous record_usage calls - no lost updates (Lesson #4 shape, SQLite this time) ---")
balance_before = api_budget.get_balance()
input_rate, output_rate = api_budget.get_current_rates()
per_call_cost = 1000 / 1_000_000 * input_rate

def record_in_thread():
    api_budget.record_usage("concurrent_test", input_tokens=1000, output_tokens=0)

threads = [threading.Thread(target=record_in_thread) for _ in range(20)]
for t in threads:
    t.start()
for t in threads:
    t.join()

balance_after = api_budget.get_balance()
actual_drop = balance_before - balance_after
expected_drop = 20 * per_call_cost
check(f"all 20 concurrent deductions landed (expected drop ~{expected_drop:.6f}, actual {actual_drop:.6f})",
      abs(actual_drop - expected_drop) < 0.000001)

print("\n--- Test 2: 30 sequential real Ollama calls - no crash ---")
crashed = False
try:
    for i in range(30):
        "".join(mc.stream_ollama("You are CIPHER.", [{"role": "user", "content": f"say the number {i}"}]))
except Exception as e:
    crashed = True
    print(f"  crashed on iteration: {e}")
check("30 sequential real Ollama calls complete without crashing", not crashed)

print("\n=== L5 EXTREME / BREAKING ===\n")

print("--- Test 3: stream_by_tier with a garbage/unrecognized tier string ---")
original_stream_gemini = mc.stream_gemini
mc.stream_gemini = lambda system_prompt, messages, location="": iter(["GEMINI_FALLBACK"])
out = "".join(mc.stream_by_tier("cipher", "totally_not_a_real_tier", "sys", [{"role": "user", "content": "hi"}]))
check("an unrecognized tier string falls through to free_cloud, not a crash", out == "GEMINI_FALLBACK")
mc.stream_gemini = original_stream_gemini

print("\n--- Test 4: stream_ollama with an empty messages list ---")
try:
    out = "".join(mc.stream_ollama("You are CIPHER.", []))
    check("empty messages list handled without crashing", True, f"got: {out[:50]!r}")
except Exception as e:
    check("empty messages list handled without crashing", False, f"raised {type(e).__name__}: {e}")

print("\n--- Test 5: stream_ollama with malformed chunk shapes from Ollama ---")
def malformed_ollama_chat(model, messages, stream, options):
    return iter([
        {"message": {"content": "Good chunk. "}},
        {},                              # missing "message" entirely
        {"message": {}},                 # missing "content"
        {"message": {"content": None}},  # content is None
        {"message": {"content": "Still works."}},
    ])
original_ollama_chat = mc.ollama.chat
mc.ollama.chat = malformed_ollama_chat
try:
    out = "".join(mc.stream_ollama("You are CIPHER.", [{"role": "user", "content": "hi"}]))
    check("malformed chunk shapes are skipped, not crashed on", out == "Good chunk. Still works.")
except Exception as e:
    check("malformed chunk shapes are skipped, not crashed on", False, f"raised {type(e).__name__}: {e}")
mc.ollama.chat = original_ollama_chat

print("\n--- Test 6: record_usage with zero tokens (a free/failed call) ---")
try:
    warning = api_budget.record_usage("edge_case_agent", input_tokens=0, output_tokens=0)
    check("zero-token usage records without crashing", warning == "")
except Exception as e:
    check("zero-token usage records without crashing", False, f"raised {type(e).__name__}: {e}")

print("\n--- Test 7: get_effective_default_tier with an empty-string agent name ---")
try:
    tier = mc.get_effective_default_tier("")
    check("empty agent name falls back to free_cloud, not a crash", tier == "free_cloud")
except Exception as e:
    check("empty agent name falls back to free_cloud, not a crash", False, f"raised {type(e).__name__}: {e}")

print("\n--- Test 8: hard stop still fires correctly on a DEEPLY negative balance ---")
conn = api_budget._get_conn()
conn.execute("UPDATE api_balance SET balance = -500.0 WHERE id = 1")
conn.commit()
conn.close()
def fail_if_called():
    raise AssertionError("get_claude_client should NOT be called on a deeply negative balance")
original_get_claude_client = mc.get_claude_client
mc.get_claude_client = fail_if_called
out = "".join(mc.stream_claude("You are CIPHER.", [{"role": "user", "content": "hi"}]))
check("a deeply negative balance still triggers the hard stop, not a crash or a bypass", "⚠️" in out)
mc.get_claude_client = original_get_claude_client

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")