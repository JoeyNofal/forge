"""
CIPHER real actions (create_file / run_command, approval-gated) -
L1 (static) + L2 (smoke). Real file writes and real commands run here,
but ALWAYS against a throwaway temp path - never Youssef's real files.
Run with: python agents/cipher/test_cipher_actions.py
"""
import ast, os, sys, tempfile, types
sys.path.insert(0, os.path.abspath("."))

os.environ["PENDING_ACTIONS_PATH"] = os.path.join(tempfile.mkdtemp(prefix="pending_actions_test_"), "pending_actions.json")
TEST_DIR = tempfile.mkdtemp(prefix="cipher_actions_test_")

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))

print("=== L1 STATIC ===")
for f in ["shared/pending_actions.py", "agents/cipher/cipher_tools.py", "agents/cipher/chat.py"]:
    try:
        ast.parse(open(f, encoding="utf-8").read())
        check(f"{f} parses as valid Python", True)
    except SyntaxError as e:
        check(f"{f} parses as valid Python", False, str(e))

# Mock only the model - everything else (queue, real file writes, real
# commands) runs for real, against the throwaway paths above.
fake_model_client = types.ModuleType("shared.model_client")
fake_model_client.stream_by_tier = lambda agent, tier, system_prompt, messages, location="": iter(["mocked response chunk"])  # type: ignore[attr-defined]
sys.modules["shared.model_client"] = fake_model_client

fake_web_search = types.ModuleType("shared.web_search")
fake_web_search.WEB_SEARCH_FAILED_PREFIX = "[WEB_SEARCH_FAILED]"  # type: ignore[attr-defined]
fake_web_search.web_search = lambda query, num_results=3: f"Web search results:\n\n1. Fake result for {query}"  # type: ignore[attr-defined]
sys.modules["shared.web_search"] = fake_web_search

from shared import pending_actions
from agents.cipher import cipher_tools
from agents.cipher import chat

print("\n=== L2 SMOKE ===")

# --- shared.pending_actions: basic round-trip ---
action_id = pending_actions.create_pending_action("cipher", "create_file", {"path": "x", "content": "y"})
fetched = pending_actions.get_pending_action(action_id)
check("created action can be fetched back", fetched is not None and fetched["status"] == "pending")

ok = pending_actions.resolve_action(action_id, "executed", "did the thing")
check("resolving a pending action succeeds", ok is True)
check("resolved action can't be re-resolved", pending_actions.resolve_action(action_id, "executed", "again") is False)

# --- cipher_tools: propose creates a real pending entry, nothing executes yet ---
test_file_path = os.path.join(TEST_DIR, "hello.py")
proposed_id, desc = cipher_tools.propose_create_file(test_file_path, "print('hello')")
check("proposing create_file returns an id and description", bool(proposed_id) and test_file_path in desc)
check("proposing does NOT create the real file yet", not os.path.exists(test_file_path))

# --- cipher_tools: approve_and_execute actually writes the real file ---
result = cipher_tools.approve_and_execute(proposed_id)
check("approve_and_execute actually creates the real file", os.path.exists(test_file_path))
check("approve_and_execute returns a real result message", "Created" in result)
with open(test_file_path) as f:
    check("real file content matches what was proposed", f.read() == "print('hello')")

# --- cipher_tools: can't execute the same action twice ---
result2 = cipher_tools.approve_and_execute(proposed_id)
check("executing an already-executed action doesn't re-run it", "already executed" in result2)

# --- cipher_tools: run_command actually runs a real, harmless command ---
cmd_id, cmd_desc = cipher_tools.propose_run_command("echo hello_from_cipher_test")
cmd_result = cipher_tools.approve_and_execute(cmd_id)
check("approve_and_execute actually runs the real command", "hello_from_cipher_test" in cmd_result)

# --- cipher_tools: deny_action never executes anything ---
deny_id, _ = cipher_tools.propose_create_file(os.path.join(TEST_DIR, "never.py"), "should never be written")
deny_result = cipher_tools.deny_action(deny_id)
check("deny_action marks it denied", "Denied" in deny_result)
check("denying a create_file action never creates the real file", not os.path.exists(os.path.join(TEST_DIR, "never.py")))
check("an already-denied action can't later be approved", "already denied" in cipher_tools.approve_and_execute(deny_id))

# --- cipher_tools: unknown action id is handled clearly, not a crash ---
check("unknown action id returns a clear message, no crash", "No pending action" in cipher_tools.approve_and_execute("not-a-real-id"))

# --- chat.py: extract_pending_actions parses a real SAVE_FILE block and proposes it for real ---
raw_save = f"Sure thing.\nSAVE_FILE: {os.path.join(TEST_DIR, 'from_chat.py')}\n<<<CODE_START>>>\nprint('from chat')\n<<<CODE_END>>>"
proposals = chat.extract_pending_actions(raw_save)
check("extract_pending_actions finds the SAVE_FILE block", len(proposals) == 1 and proposals[0]["type"] == "create_file")
check("the proposed action is real and pending", pending_actions.get_pending_action(proposals[0]["id"])["status"] == "pending")  # type: ignore[index]

# --- chat.py: extract_pending_actions parses a real RUN_COMMAND line ---
raw_run = "On it.\nRUN_COMMAND: echo from_chat_test"
proposals2 = chat.extract_pending_actions(raw_run)
check("extract_pending_actions finds the RUN_COMMAND line", len(proposals2) == 1 and proposals2[0]["type"] == "run_command")

# --- chat.py: strip_action_markers sanitizes for history, doesn't erase context ---
stripped = chat.strip_action_markers(raw_save)
check("SAVE_FILE block removed from history text", "SAVE_FILE:" not in stripped and "<<<CODE_START>>>" not in stripped)
check("history text still notes something was proposed, not silently erased", "awaiting your approval" in stripped)

# --- end-to-end: stream_cipher yields the approval note when the (mocked) model proposes a file ---
def model_with_save_file(agent, tier, system_prompt, messages, location=""):
    return iter([f"Sure.\nSAVE_FILE: {os.path.join(TEST_DIR, 'end_to_end.py')}\n<<<CODE_START>>>\nprint('e2e')\n<<<CODE_END>>>"])
chat.stream_by_tier = model_with_save_file
out = "".join(chat.stream_cipher("write me a hello world script"))
check("stream_cipher's output includes the waiting-for-approval note", "Waiting for your approval" in out)
check("the real file was NOT created yet (only proposed, not approved)", not os.path.exists(os.path.join(TEST_DIR, "end_to_end.py")))

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")