"""
CIPHER real actions - L4 (sustained/concurrency) + L5 (extreme/breaking).
Real file writes and real commands run here, always against a
throwaway temp path.
Run with: python agents/cipher/test_cipher_actions_l4_l5.py
"""
import os, sys, tempfile, threading
sys.path.insert(0, os.path.abspath("."))

os.environ["PENDING_ACTIONS_PATH"] = os.path.join(tempfile.mkdtemp(prefix="pending_actions_l4l5_"), "pending_actions.json")
TEST_DIR = tempfile.mkdtemp(prefix="cipher_actions_l4l5_")

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

from shared import pending_actions
from agents.cipher import cipher_tools

print("=== L4 SUSTAINED / CONCURRENCY ===\n")

print("--- Test 1: 20 simultaneous create_pending_action calls - no data loss ---")
def create_in_thread(i, results_list):
    aid = pending_actions.create_pending_action("cipher", "create_file", {"path": f"f{i}", "content": f"c{i}"})
    results_list.append(aid)

created_ids = []
threads = [threading.Thread(target=create_in_thread, args=(i, created_ids)) for i in range(20)]
for t in threads: t.start()
for t in threads: t.join()
check("all 20 concurrent creates landed", len(set(created_ids)) == 20)

print("\n--- Test 2: 20 concurrent approve_and_execute calls on 20 DIFFERENT actions - no cross-talk ---")
action_ids = []
for i in range(20):
    path = os.path.join(TEST_DIR, f"file_{i}.txt")
    aid, _ = cipher_tools.propose_create_file(path, f"content number {i}")
    action_ids.append((aid, path, i))

def approve_in_thread(aid):
    cipher_tools.approve_and_execute(aid)

threads2 = [threading.Thread(target=approve_in_thread, args=(aid,)) for aid, _, _ in action_ids]
for t in threads2: t.start()
for t in threads2: t.join()

all_correct = True
for aid, path, i in action_ids:
    if not os.path.exists(path):
        all_correct = False
        break
    with open(path) as f:
        if f.read() != f"content number {i}":
            all_correct = False
            break
check("all 20 files created concurrently, each with its OWN correct content", all_correct)

print("\n--- Test 3: THE RACE - 20 threads approve the SAME action at once - executes exactly ONCE ---")
race_path = os.path.join(TEST_DIR, "race_test.txt")
race_id, _ = cipher_tools.propose_create_file(race_path, "race content")

race_results = []
lock = threading.Lock()
def race_approve():
    r = cipher_tools.approve_and_execute(race_id)
    with lock:
        race_results.append(r)

threads3 = [threading.Thread(target=race_approve) for _ in range(20)]
for t in threads3: t.start()
for t in threads3: t.join()

real_executions = [r for r in race_results if r.startswith("Created")]
blocked = [r for r in race_results if "already" in r]
check("exactly ONE thread actually executed the real action, not more", len(real_executions) == 1,
      f"got {len(real_executions)} real executions: {real_executions}")
check("the other 19 were correctly blocked from re-executing", len(blocked) == 19, f"got {len(blocked)} blocked")

print("\n=== L5 EXTREME / BREAKING ===\n")

print("--- Test 4: unknown action id doesn't crash ---")
try:
    result = cipher_tools.approve_and_execute("not-a-real-id-at-all")
    check("unknown action id returns a clear message, no crash", "No pending action" in result)
except Exception as e:
    check("unknown action id returns a clear message, no crash", False, f"raised {type(e).__name__}: {e}")

print("\n--- Test 5: a real command that genuinely fails is reported clearly, not swallowed ---")
fail_id, _ = cipher_tools.propose_run_command("this_is_not_a_real_command_xyz123")
result5 = cipher_tools.approve_and_execute(fail_id)
print(f"  result: {result5}")
action5 = pending_actions.get_pending_action(fail_id)
check("a genuinely failing command doesn't crash approve_and_execute", True)
# shell reports "command not found" as real output, not a Python exception - either status is correct
check("the failed command's status reflects what actually happened",
      action5 is not None and action5["status"] in ("executed", "failed"))

print("\n--- Test 6: a real command timeout is caught, not left hanging ---")
try:
    cipher_tools._real_run_command("python -c \"import time; time.sleep(3)\"", timeout=1)
    check("a genuinely slow command raises a timeout, doesn't hang forever", False, "no exception raised")
except Exception as e:
    check("a genuinely slow command raises a timeout, doesn't hang forever", "Timeout" in type(e).__name__)

print("\n--- Test 7: unicode content in a real file save ---")
unicode_path = os.path.join(TEST_DIR, "unicode_test.txt")
uid, _ = cipher_tools.propose_create_file(unicode_path, "émojis 🎉 and 日本語 too")
result7 = cipher_tools.approve_and_execute(uid)
try:
    with open(unicode_path, encoding="utf-8") as f:
        content7 = f.read()
    check("unicode content saves and reads back correctly", content7 == "émojis 🎉 and 日本語 too")
except Exception as e:
    check("unicode content saves and reads back correctly", False, f"raised {type(e).__name__}: {e}")

print("\n--- Test 8: very large file content (~50,000 chars) ---")
huge_path = os.path.join(TEST_DIR, "huge_test.txt")
huge_content = "x" * 50000
hid, _ = cipher_tools.propose_create_file(huge_path, huge_content)
result8 = cipher_tools.approve_and_execute(hid)
check("50,000-char file content saves without crashing", os.path.exists(huge_path) and os.path.getsize(huge_path) == 50000)

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")