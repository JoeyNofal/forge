"""
CIPHER Phase 1 — L1 (static) + L2 (smoke, mocked model/search).
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
with open("agents/cipher/chat.py", encoding="utf-8") as f:
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

from agents.cipher import chat

check("chat defines stream_cipher", hasattr(chat, "stream_cipher"))
check("chat defines needs_search", hasattr(chat, "needs_search"))
check("chat defines strip_unexecuted_action_markers", hasattr(chat, "strip_unexecuted_action_markers"))

print("\n=== L2 SMOKE (mocked model/search) ===")

out = list(chat.stream_cipher("what's the weather today"))
check("off-topic message triggers refusal, no model call", out == [chat.REFUSAL_MESSAGE])

out = list(chat.stream_cipher("give me a workout program in python for tracking reps"))
check("'program' + coding intent does NOT wrongly refuse (old bug)", out != [chat.REFUSAL_MESSAGE])

check("'latest Python version' triggers search", chat.needs_search("what's the latest Python version") is True)
check("plain coding question does NOT trigger search", chat.needs_search("write a function to reverse a string") is False)

out = list(chat.stream_cipher("what's the latest version of FastAPI"))
check("search-triggering question still gets a real (mocked) model response", out == ["mocked response chunk"])

# SAVE_FILE/RUN_COMMAND are now REAL (Decision, later session) - they go
# through extract_pending_actions()/strip_action_markers() instead, with
# their own full coverage in test_cipher_actions.py. strip_unexecuted_
# action_markers() now only covers what's still genuinely unbuilt.
raw = "Sure, here it is.\nCREATE_BACKUP: milestone | summary\nDone."
stripped = chat.strip_unexecuted_action_markers(raw)
check("CREATE_BACKUP marker gets stripped and replaced with placeholder", "CREATE_BACKUP:" not in stripped and "isn't built yet in FORGE" in stripped)

raw2 = "Sure.\nWRITE_RECORD: some/path.txt | new content"
stripped2 = chat.strip_unexecuted_action_markers(raw2)
check("WRITE_RECORD marker gets stripped and replaced with placeholder", "WRITE_RECORD:" not in stripped2)

history = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}]
list(chat.stream_cipher("write a function to add two numbers", history=history))
check("original history list is not mutated by stream_cipher", history == [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "hello"}])

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")