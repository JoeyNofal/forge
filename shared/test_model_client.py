"""
FORGE tier-switching + budget - L1 (static) + L2 (smoke, all three
model tiers mocked, real budget math against a throwaway temp DB).
Run with: python shared/test_model_client.py
"""
import ast, os, sys, tempfile
sys.path.insert(0, os.path.abspath("."))

# Throwaway DB BEFORE anything imports shared.api_budget, so this run
# never touches the real D:\Projects\forge\data\chat_history.db.
os.environ["FORGE_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="forge_budget_test_"), "chat_history.db")

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))

print("=== L1 STATIC ===")
for f in ["shared/model_client.py", "shared/api_budget.py"]:
    try:
        ast.parse(open(f, encoding="utf-8").read())
        check(f"{f} parses as valid Python", True)
    except SyntaxError as e:
        check(f"{f} parses as valid Python", False, str(e))

from shared import api_budget
from shared import model_client as mc

print("\n=== L2 SMOKE: BUDGET (real sqlite, temp DB) ===")

check("fresh balance starts at the $10 daily topup", api_budget.get_balance() == 10.0)

input_rate, output_rate = api_budget.get_current_rates()
warning = api_budget.record_usage("cipher", input_tokens=1000, output_tokens=500)
expected_cost = (1000 / 1_000_000 * input_rate) + (500 / 1_000_000 * output_rate)
new_balance = api_budget.get_balance()
check("record_usage subtracts the correct real cost from the balance",
      abs(new_balance - (10.0 - expected_cost)) < 0.0001,
      f"expected ~{10.0 - expected_cost}, got {new_balance}")

check("get_agent_default_tiers starts empty (no overrides set yet)", api_budget.get_agent_default_tiers() == {})
api_budget.set_agent_default_tier("stock", "local")
check("set_agent_default_tier round-trips correctly", api_budget.get_agent_default_tiers() == {"stock": "local"})

check("cipher's default tier is paid_cloud with no override", mc.get_effective_default_tier("cipher") == "paid_cloud")
check("stock's default tier is now local, after the override just set", mc.get_effective_default_tier("stock") == "local")
check("an unknown agent falls back to free_cloud", mc.get_effective_default_tier("nonexistent_agent") == "free_cloud")

print("\n=== L2 SMOKE: TIER ROUTING (mocked - zero network) ===")

original_stream_ollama = mc.stream_ollama
original_stream_gemini = mc.stream_gemini
original_stream_claude = mc.stream_claude

mc.stream_ollama = lambda system_prompt, messages, location="": iter(["OLLAMA_CALLED"])
mc.stream_gemini = lambda system_prompt, messages, location="": iter(["GEMINI_CALLED"])
mc.stream_claude = lambda system_prompt, messages, location="", agent="cipher": iter(["CLAUDE_CALLED"])

out = "".join(mc.stream_by_tier("cipher", "local", "sys", [{"role": "user", "content": "hi"}]))
check("tier='local' routes to stream_ollama", out == "OLLAMA_CALLED")

out = "".join(mc.stream_by_tier("cipher", "free_cloud", "sys", [{"role": "user", "content": "hi"}]))
check("tier='free_cloud' routes to stream_gemini", out == "GEMINI_CALLED")

out = "".join(mc.stream_by_tier("cipher", "paid_cloud", "sys", [{"role": "user", "content": "hi"}]))
check("tier='paid_cloud' routes to stream_claude", out == "CLAUDE_CALLED")

out = "".join(mc.stream_by_tier("cipher", None, "sys", [{"role": "user", "content": "hi"}]))
check("tier=None falls back to cipher's live default (paid_cloud)", out == "CLAUDE_CALLED")

out = "".join(mc.stream_by_tier("stock", None, "sys", [{"role": "user", "content": "hi"}]))
check("tier=None for stock uses ITS live default (local, overridden above)", out == "OLLAMA_CALLED")

mc.stream_ollama = original_stream_ollama
mc.stream_gemini = original_stream_gemini
mc.stream_claude = original_stream_claude

print("\n=== L2 SMOKE: OLLAMA (Local tier, mocked ollama.chat) ===")

def fake_ollama_chat(model, messages, stream, options):
    check("stream_ollama calls the right local model", model == mc.OLLAMA_MODEL)
    return iter([{"message": {"content": "Hello "}}, {"message": {"content": "from Gemma"}}])

original_ollama_chat = mc.ollama.chat
mc.ollama.chat = fake_ollama_chat
out = "".join(mc.stream_ollama("You are CIPHER.", [{"role": "user", "content": "hi"}]))
check("stream_ollama yields the real streamed text", out == "Hello from Gemma")
mc.ollama.chat = original_ollama_chat

print("\n=== L2 SMOKE: CLAUDE / PAID CLOUD (mocked anthropic client) ===")

class FakeUsage:
    def __init__(self, input_tokens, output_tokens):
        self.input_tokens = input_tokens
        self.output_tokens = output_tokens

class FakeFinalMessage:
    def __init__(self, usage):
        self.usage = usage

class FakeStreamContext:
    def __init__(self, chunks, usage):
        self._chunks = chunks
        self._usage = usage
    def __enter__(self):
        return self
    def __exit__(self, *a):
        return False
    @property
    def text_stream(self):
        return iter(self._chunks)
    def get_final_message(self):
        return FakeFinalMessage(self._usage)

class FakeClaudeClient:
    def __init__(self, chunks, usage):
        self._chunks = chunks
        self._usage = usage
        self.messages = self
    def stream(self, **kwargs):
        return FakeStreamContext(self._chunks, self._usage)

# --- budget hard stop: drain the balance below zero first ---
api_budget.record_usage("test_drain", input_tokens=0, output_tokens=1_000_000)
check("balance is now at or below zero after draining it", api_budget.get_balance() <= 0)

def fail_if_called():
    raise AssertionError("get_claude_client should NOT be called when the budget is already at $0")
original_get_claude_client = mc.get_claude_client
mc.get_claude_client = fail_if_called

out = "".join(mc.stream_claude("You are CIPHER.", [{"role": "user", "content": "hi"}]))
check("hard stop fires BEFORE any real API call, with a visible message",
      "budget" in out.lower() and "⚠️" in out)

mc.get_claude_client = original_get_claude_client

# --- top the balance back up for the remaining tests ---
# set_daily_topup() only takes effect on the NEXT calendar day (by
# design - that's the real rollover-forever behavior working
# correctly), so it can't refill a same-day balance. Reset the row
# directly instead, purely for test setup - production code never
# does this.
conn = api_budget._get_conn()
conn.execute("UPDATE api_balance SET balance = 1000.0 WHERE id = 1")
conn.commit()
conn.close()
check("balance was reset directly for the remaining tests", api_budget.get_balance() == 1000.0)

print("\n--- real success path (mocked client, real budget deduction) ---")
mc.get_claude_client = lambda: FakeClaudeClient(["Hello ", "from Sonnet"], FakeUsage(1000, 500))
balance_before = api_budget.get_balance()
out = "".join(mc.stream_claude("You are CIPHER.", [{"role": "user", "content": "hi"}], agent="cipher"))
check("stream_claude yields the real streamed text", "Hello from Sonnet" in out)
check("a successful call actually records real usage and reduces the balance",
      api_budget.get_balance() < balance_before)
mc.get_claude_client = original_get_claude_client

print("\n--- real API failure -> visible fallback to Local, never silent (Lesson #11) ---")
def raise_error():
    raise RuntimeError("simulated Anthropic API failure")
mc.get_claude_client = raise_error
mc.stream_ollama = lambda system_prompt, messages, location="": iter(["FALLBACK_FROM_OLLAMA"])
out = "".join(mc.stream_claude("You are CIPHER.", [{"role": "user", "content": "hi"}]))
check("a real Claude failure falls back to Local, but VISIBLY (not silently)",
      "⚠️" in out and "Paid Cloud" in out and "FALLBACK_FROM_OLLAMA" in out)
mc.get_claude_client = original_get_claude_client
mc.stream_ollama = original_stream_ollama

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")