"""
ASSET - L1 (static) + L2 (smoke). Synthetic financial data throughout
- NEVER touches Youssef's real financial-tracker-data.json.
Run with: python agents/asset/test_asset.py
"""
import ast, inspect, os, sys, types
sys.path.insert(0, os.path.abspath("."))

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))

print("=== L1 STATIC ===")
for f in ["agents/asset/chat.py", "agents/asset/asset_tools.py", "agents/asset/prompt.py", "shared/asset_memory.py"]:
    try:
        ast.parse(open(f, encoding="utf-8").read())
        check(f"{f} parses as valid Python", True)
    except SyntaxError as e:
        check(f"{f} parses as valid Python", False, str(e))

# Mock model, web search, and memory - none of these need real
# network/Ollama for L1/L2.
fake_model_client = types.ModuleType("shared.model_client")
fake_model_client.stream_ollama = lambda system_prompt, messages, location="": iter(["mocked ASSET response"])  # type: ignore[attr-defined]
sys.modules["shared.model_client"] = fake_model_client

fake_web_search = types.ModuleType("shared.web_search")
fake_web_search.WEB_SEARCH_FAILED_PREFIX = "[WEB_SEARCH_FAILED]"  # type: ignore[attr-defined]
fake_web_search.web_search = lambda query, num_results=3: f"Web search results:\n\n1. Fake result for {query}"  # type: ignore[attr-defined]
sys.modules["shared.web_search"] = fake_web_search

fake_asset_memory = types.ModuleType("shared.asset_memory")
_save_calls = []
fake_asset_memory.save_conversation_turn = lambda msg, resp, category="conversation": _save_calls.append((msg, resp, category))  # type: ignore[attr-defined]
fake_asset_memory.search_memory = lambda query, n_results=5: []  # type: ignore[attr-defined]
sys.modules["shared.asset_memory"] = fake_asset_memory

from agents.asset import chat
from agents.asset import asset_tools

print("\n=== L2 SMOKE ===")

# --- Hard rule: ASSET has NO model_tier parameter at all ---
sig = inspect.signature(chat.stream_asset)
check("stream_asset has NO model_tier parameter (permanently local-only)", "model_tier" not in sig.parameters)

# --- Refusal gate (reused from Phase 0) ---
out = "".join(chat.stream_asset("what's the weather like today"))
check("off-topic message triggers refusal, no model call", out == chat.REFUSAL_MESSAGE)

# --- The specific false-refusal bug found this session ---
out2 = "".join(chat.stream_asset("how much do I spend on food each month"))
check("'spend on food' does NOT wrongly refuse (real bug found this session)", out2 != chat.REFUSAL_MESSAGE)

# --- Synthetic financial data for everything below ---
SYNTHETIC_DATA = {
    "accounts": {
        "vault": 1000.0, "flex": -50.0, "funds": 5000.0,
        "cc": 200.0, "cc2": -30.0, "car_loan": 8000.0, "brex": 500.0,
    },
    "settings": {
        "carLoanInitial": 15000, "carLoanMonthlyTarget": 300,
        "ccLimit": 5000, "ccTargetMin": 0, "ccTargetMax": 500,
        "cc2Limit": 3000, "cc2TargetMin": 0, "cc2TargetMax": 300,
        "flexFloor": 500, "carFundTarget": 5000, "carFundMinimum": 1000,
        "creditScoreTarget": 750, "creditScoreTarget2": 750,
        "brexStartingBalance": 1000,
    },
    "transactions": [
        {"date": "2026-09-01", "amount": -45.0, "accountId": "vault", "description": "Groceries", "type": "purchase"},
    ],
    "paychecks": [{"date": "2026-09-15", "grossPay": 3000, "netPay": 2200, "taxes": {"federal": 500}, "deductions": {"401k": 300}}],
    "creditScores": [{"date": "2026-08-01", "score": 720, "source": "Chase"}, {"date": "2026-09-01", "score": 735, "source": "Chase"}],
    "groceries": {"2026-08": 400.0, "2026-09": 380.0},
    "fixedExpenses": [{"frequency": "monthly", "amount": 1200}],
    "fundsSubAccounts": {"savingsFund": 3000.0},
}
asset_tools.load_data = lambda: SYNTHETIC_DATA

# --- The net-worth fix (Decisions, this session), tested directly ---
net_worth_output = asset_tools.get_net_worth()
print(f"  get_net_worth() output:\n{net_worth_output}\n")
# assets: vault 1000 + funds 5000 + cc2 credit-in-favor 30 + brex 500 = 6530
# liabilities: flex overdraft 50 + cc owed 200 + car_loan 8000 = 8250
# net worth: 6530 - 8250 = -1720
check("cc2's negative balance counts as an ASSET (credit in your favor)", "SAVOR" in net_worth_output and "credit in your favor" in net_worth_output)
check("cc's positive balance counts as a LIABILITY (owed)", "FREEDOM" in net_worth_output and "owed" in net_worth_output)
check("flex's negative balance (overdraft) counts as a LIABILITY, not silently dropped", "overdraft" in net_worth_output)
check("BREX counts as a normal ASSET (Decision, confirmed with Youssef)", "$500.00" in net_worth_output and "BREX" in net_worth_output)
check("total assets computed correctly (6530.00)", "Total assets: $6,530.00" in net_worth_output)
check("total liabilities computed correctly (8250.00)", "Total liabilities: $8,250.00" in net_worth_output)
check("final net worth computed correctly (-1720.00)", "NET WORTH: $-1,720.00" in net_worth_output)

# --- build_tool_context: word-boundary-safe tool selection ---
ctx = chat.build_tool_context("what's my net worth?")
check("'net worth' question includes the NET WORTH SNAPSHOT", "NET WORTH SNAPSHOT" in ctx)
check("account settings are ALWAYS included regardless of the question", "ACCOUNT SETTINGS" in ctx)

ctx2 = chat.build_tool_context("what's my net worth and what are my recent transactions?")
check("a message matching MULTIPLE tools fires all of them, not just one", "NET WORTH SNAPSHOT" in ctx2 and "RECENT TRANSACTIONS" in ctx2)

ctx3 = chat.build_tool_context("just saying hi")
check("a message matching NO tool keywords still gets account settings, nothing else extra",
      "ACCOUNT SETTINGS" in ctx3 and "NET WORTH SNAPSHOT" not in ctx3)

# --- A real load_data() failure is surfaced, not silently swallowed ---
def broken_load_data():
    raise RuntimeError("Financial data file not found at /fake/path.json.")
original_load_data = asset_tools.load_data
asset_tools.load_data = broken_load_data

captured = {}
def capturing_stream_ollama(system_prompt, messages, location=""):
    captured["sent"] = messages[-1]["content"]
    return iter(["mocked response"])
chat.stream_ollama = capturing_stream_ollama

out3 = "".join(chat.stream_asset("what's my net worth?"))
check("a real data-load failure is NOT silently swallowed - it reaches the model as an explicit note",
      "FINANCIAL DATA UNAVAILABLE" in captured.get("sent", ""))
check("ASSET still responds (doesn't crash) even when the data file is unavailable", out3 == "mocked response")

asset_tools.load_data = lambda: SYNTHETIC_DATA  # restore

# --- ASSET_NEWS_TRIGGERS: narrow, trigger-gated web search ---
chat.stream_ollama = fake_model_client.stream_ollama
search_calls = []
original_web_search = chat.web_search
chat.web_search = lambda query, num_results=3: (search_calls.append(query), "Web search results:\n\n1. fake")[1]

list(chat.stream_asset("what are current mortgage rates?"))
check("a message with a real news/rate trigger DOES call web search", len(search_calls) == 1)

search_calls.clear()
list(chat.stream_asset("what's my net worth?"))
check("an ordinary financial question does NOT call web search (narrow, trigger-gated by design)", len(search_calls) == 0)
chat.web_search = original_web_search

# --- Memory saving: reused old filter, now word-boundary safe ---
_save_calls.clear()
list(chat.stream_asset("I've decided my goal is to pay off the car loan by December"))
check("a message with real save-worthy language triggers save_conversation_turn", len(_save_calls) == 1)

_save_calls.clear()
list(chat.stream_asset("what's my net worth?"))
check("a routine question does NOT trigger a memory save", len(_save_calls) == 0)

# --- History isn't mutated ---
history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "State your business."}]
list(chat.stream_asset("what's my net worth?", history=history))
check("original history list is not mutated by stream_asset",
      history == [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "State your business."}])

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")