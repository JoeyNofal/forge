"""
NEXUS Phase 2 core chat — L1 (static) + L2 (smoke, mocked model/search).
L3 (real end-to-end) is a separate script — needs your real API keys.
"""
import ast, os, sys, types
sys.path.insert(0, os.path.abspath("."))

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and status == "FAIL" else ""))

print("=== L1 STATIC ===")
with open("agents/nexus/chat.py") as f:
    src = f.read()
try:
    ast.parse(src)
    check("chat.py parses as valid Python", True)
except SyntaxError as e:
    check("chat.py parses as valid Python", False, str(e))

# Mock model/search so L1/L2 need zero real API keys or network calls
fake_model_client = types.ModuleType("shared.model_client")
fake_model_client.stream_by_tier = lambda agent, tier, system_prompt, messages, location="": iter(["mocked response chunk"])  # type: ignore[attr-defined]
sys.modules["shared.model_client"] = fake_model_client

fake_web_search = types.ModuleType("shared.web_search")
fake_web_search.WEB_SEARCH_FAILED_PREFIX = "[WEB_SEARCH_FAILED]"  # type: ignore[attr-defined]
fake_web_search.web_search = lambda query, num_results=3: f"Web search results:\n\n1. Fake result for {query}"  # type: ignore[attr-defined]
sys.modules["shared.web_search"] = fake_web_search

from agents.nexus import chat

check("chat defines stream_nexus", hasattr(chat, "stream_nexus"))
check("chat defines strip_unexecuted_action_markers", hasattr(chat, "strip_unexecuted_action_markers"))

print("\n=== L2 SMOKE (mocked model/search) ===")

out = list(chat.stream_nexus("how's the weather looking"))
check("weather message still gets a real (mocked) model response", out == ["mocked response chunk"])

q = chat._build_search_query("how's the weather looking", "South Bend, IN")
check("weather query gets location + 'tomorrow' baked in", "South Bend, IN" in q and "tomorrow" in q)

q2 = chat._build_search_query("what's the best way to learn guitar", "South Bend, IN")
check("non-weather query gets 'near <location>' appended", q2 == "what's the best way to learn guitar near South Bend, IN")

out2 = list(chat.stream_nexus("just chatting, nothing urgent"))
check("NEXUS never refuses anything (fully unrestricted)", out2 == ["mocked response chunk"])

raw = "Sure, on it.\nSET_REMINDER: call mom | call mom | tomorrow\nAll set."
stripped = chat.strip_unexecuted_action_markers(raw)
check("SET_REMINDER marker gets stripped and replaced with placeholder", "SET_REMINDER:" not in stripped and "isn't built yet" in stripped)

raw2 = "Let me check.\nASK_CIPHER: what does this error mean"
stripped2 = chat.strip_unexecuted_action_markers(raw2)
check("ASK_CIPHER bridge marker gets stripped", "ASK_CIPHER:" not in stripped2)

raw3 = "Here you go.\nLIST_REMINDERS\nThat's everything."
stripped3 = chat.strip_unexecuted_action_markers(raw3)
check("standalone LIST_REMINDERS (no colon) gets stripped", "LIST_REMINDERS" not in stripped3)

raw4 = "All set, sir.  SET_REMINDER: pay rent | pay rent | Friday"
stripped4 = chat.strip_unexecuted_action_markers(raw4)
check("marker appearing mid-line (after other text) still gets stripped", "SET_REMINDER:" not in stripped4 and "All set, sir." in stripped4)

history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
list(chat.stream_nexus("what's a good dinner idea tonight", history=history))
check("original history list is not mutated by stream_nexus", history == [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}])

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")