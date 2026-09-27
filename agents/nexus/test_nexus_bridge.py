"""
NEXUS's ASK_CIPHER bridge - L1 (static) + L2 (smoke).
Both NEXUS's own model and CIPHER's stream_cipher are mocked here -
this file tests NEXUS's bridge LOGIC in isolation; CIPHER's own
correctness (including its real approval-gated actions) already has
its own full test suite.
Run with: python agents/nexus/test_nexus_bridge.py
"""
import ast, os, sys, types
sys.path.insert(0, os.path.abspath("."))

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))

print("=== L1 STATIC ===")
for f in ["agents/nexus/chat.py", "shared/agent_topics.py", "shared/keyword_gate.py"]:
    try:
        ast.parse(open(f, encoding="utf-8").read())
        check(f"{f} parses as valid Python", True)
    except SyntaxError as e:
        check(f"{f} parses as valid Python", False, str(e))

fake_web_search = types.ModuleType("shared.web_search")
fake_web_search.WEB_SEARCH_FAILED_PREFIX = "[WEB_SEARCH_FAILED]"  # type: ignore[attr-defined]
fake_web_search.web_search = lambda query, num_results=3: f"Web search results:\n\n1. Fake result for {query}"  # type: ignore[attr-defined]
sys.modules["shared.web_search"] = fake_web_search

from agents.nexus import chat

print("\n=== L2 SMOKE ===")

# --- detect_cipher_bridge: word-boundary-safe keyword pre-check ---
check("'write me a script' triggers the bridge", chat.detect_cipher_bridge("write me a script to rename files"))
check("'python script' triggers the bridge", chat.detect_cipher_bridge("can you make a python script for this"))
check("unrelated message does NOT trigger the bridge", not chat.detect_cipher_bridge("what's a good dinner idea tonight"))

# --- extract_cipher_bridge_task: real marker vs a mention ---
task = chat.extract_cipher_bridge_task("Right away.\nASK_CIPHER: help debug this stack trace")
check("a real ASK_CIPHER: line is extracted", task == "help debug this stack trace")

mention = chat.extract_cipher_bridge_task("I'll write the `ASK_CIPHER:` command when needed, sir.")
check("a backtick-wrapped MENTION is not mistaken for a real command", mention is None)

check("normal text with no marker at all extracts nothing", chat.extract_cipher_bridge_task("just chatting") is None)

# --- strip_bridge_markers ---
stripped = chat.strip_bridge_markers("On it.\nASK_CIPHER: fix this bug")
check("ASK_CIPHER line replaced with a plain-English note for history", "ASK_CIPHER:" not in stripped and "Routed to CIPHER" in stripped)

# --- ASK_CIPHER removed from the placeholder-stripping list (it's real now) ---
untouched = chat.strip_unexecuted_action_markers("Here: ASK_CIPHER: do the thing")
check("ASK_CIPHER is no longer placeholder-stripped (handled separately now)", "ASK_CIPHER:" in untouched)

# --- End-to-end: Python-side pre-check path ---
print("\n--- End-to-end: keyword pre-check routes to CIPHER ---")
captured = {}
def fake_stream_by_tier(agent, tier, system_prompt, messages, location=""):
    captured["sent"] = messages[-1]["content"]
    return iter(["Of course, sir — I'll bring in CIPHER for this."])
chat.stream_by_tier = fake_stream_by_tier

cipher_calls = []
def fake_stream_cipher(task):
    cipher_calls.append(task)
    return iter([f"Here's the real answer to: {task}"])
chat.stream_cipher = fake_stream_cipher

out = "".join(chat.stream_nexus("write me a script to rename all files in a folder"))
check("NEXUS's own brief acknowledgment appears first", out.startswith("Of course, sir"))
check("a clear separator appears before CIPHER's part", "---\nCIPHER:" in out)
check("CIPHER's real answer appears in the final output", "Here's the real answer to:" in out)
check("stream_cipher was called with the ORIGINAL message (pre-check path)",
      cipher_calls == ["write me a script to rename all files in a folder"])
check("NEXUS's own model call was told NOT to answer the question itself",
      "do NOT attempt the technical answer yourself" in captured["sent"] or "SYSTEM NOTE" in captured["sent"])

# --- End-to-end: fallback scan path (model decides on its own) ---
print("\n--- End-to-end: NEXUS's own model decides to bridge (fallback scan) ---")
cipher_calls.clear()
def fake_stream_by_tier_2(agent, tier, system_prompt, messages, location=""):
    return iter(["Let me have CIPHER take a look.\nASK_CIPHER: explain this error message"])
chat.stream_by_tier = fake_stream_by_tier_2

out2 = "".join(chat.stream_nexus("hey what's going on with this weird error I'm getting"))
check("stream_cipher was called with the task from the model's own ASK_CIPHER line",
      cipher_calls == ["explain this error message"])
check("CIPHER's real answer appears after the separator", "---\nCIPHER:" in out2)

# --- No bridge at all: CIPHER never gets called ---
print("\n--- No bridge: CIPHER is never called for an ordinary message ---")
cipher_calls.clear()
def fake_stream_by_tier_3(agent, tier, system_prompt, messages, location=""):
    return iter(["A quiet evening in sounds lovely, sir."])
chat.stream_by_tier = fake_stream_by_tier_3

out3 = "".join(chat.stream_nexus("what should I do tonight"))
check("stream_cipher is never called for a message with no bridge trigger", cipher_calls == [])
check("output is just NEXUS's own text, no separator", "---\nCIPHER:" not in out3)

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")