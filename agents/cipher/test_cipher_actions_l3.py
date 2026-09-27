"""
CIPHER real actions - L3 (real end-to-end, real Gemini, real approval).
No mocks - this is a real Gemini call genuinely deciding to write
SAVE_FILE/RUN_COMMAND, then a real approval actually executing it.
Real files/commands run, but ALWAYS against a throwaway temp path.
Run with: python agents/cipher/test_cipher_actions_l3.py
"""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath("."))

os.environ["PENDING_ACTIONS_PATH"] = os.path.join(tempfile.mkdtemp(prefix="pending_actions_l3_"), "pending_actions.json")
TEST_DIR = tempfile.mkdtemp(prefix="cipher_actions_l3_")

from dotenv import load_dotenv
load_dotenv(override=True)

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

from agents.cipher import chat
from agents.cipher import cipher_tools
from shared import pending_actions

print("=== L3 REAL END-TO-END ===\n")

# --- 1. Real Gemini genuinely proposes a real file, nothing happens yet ---
print("--- Test 1: real model asked to save a file - proposes, doesn't execute ---")
target_path = os.path.join(TEST_DIR, "hello.py").replace("\\", "\\\\")
out = "".join(chat.stream_cipher(
    f"Save a python file at exactly this path: {target_path} — it should just print 'hello from cipher'. Use SAVE_FILE."
))
print(f"  CIPHER said: {out}")
real_path = os.path.join(TEST_DIR, "hello.py")
check("real model response includes the waiting-for-approval note", "Waiting for your approval" in out)
check("the real file was NOT created yet (only proposed)", not os.path.exists(real_path))

pending = pending_actions.list_pending_actions(agent="cipher")
check("a real pending action now exists in the queue", len(pending) >= 1)

# --- 2. Real approval actually executes it ---
print("\n--- Test 2: approving the real proposed action actually creates the file ---")
if pending:
    action_id = pending[-1]["id"]
    result = cipher_tools.approve_and_execute(action_id)
    print(f"  execution result: {result}")
    check("the real file now exists after approval", os.path.exists(real_path))
    if os.path.exists(real_path):
        with open(real_path) as f:
            content = f.read()
        print(f"  real file content:\n{content}")
        check("real file content looks like real, working Python", "print" in content)
else:
    check("a real pending action now exists in the queue (re-check)", False, "no pending action to approve")

# --- 3. Real model asked to run a command - proposes, doesn't execute ---
print("\n--- Test 3: real model asked to run a command - proposes, doesn't execute ---")
out2 = "".join(chat.stream_cipher(
    "Use RUN_COMMAND to run exactly this: echo hello_from_real_cipher_test"
))
print(f"  CIPHER said: {out2}")
check("real model response includes the waiting-for-approval note", "Waiting for your approval" in out2)

pending2 = pending_actions.list_pending_actions(agent="cipher")
run_actions = [a for a in pending2 if a["type"] == "run_command"]
check("a real pending run_command action now exists", len(run_actions) >= 1)

# --- 4. Real approval actually runs it ---
print("\n--- Test 4: approving the real proposed command actually runs it ---")
if run_actions:
    cmd_result = cipher_tools.approve_and_execute(run_actions[-1]["id"])
    print(f"  execution result: {cmd_result}")
    check("the real command actually ran and produced real output", "hello_from_real_cipher_test" in cmd_result)
else:
    check("the real command actually ran and produced real output", False, "no pending run_command to approve")

# --- 5. Denying a real proposed action never executes it ---
print("\n--- Test 5: a real proposal that gets DENIED never executes ---")
never_path = os.path.join(TEST_DIR, "never_real.py").replace("\\", "\\\\")
out3 = "".join(chat.stream_cipher(
    f"Save a python file at exactly this path: {never_path} — content doesn't matter. Use SAVE_FILE."
))
pending3 = pending_actions.list_pending_actions(agent="cipher")
new_action = [a for a in pending3 if a["details"].get("path", "").endswith("never_real.py")]
if new_action:
    deny_result = cipher_tools.deny_action(new_action[0]["id"])
    print(f"  deny result: {deny_result}")
    check("real file was never created after denial", not os.path.exists(os.path.join(TEST_DIR, "never_real.py")))
else:
    check("a matching pending action was found to deny", False, "model may not have used the exact path")

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")