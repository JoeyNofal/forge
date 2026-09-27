"""
NEXUS's ASK_CIPHER bridge - L3 (real end-to-end, no mocks anywhere).
Needs: real GEMINI_API_KEY in .env, Ollama running.
Run with: python agents/nexus/test_nexus_bridge_l3.py
"""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath("."))

os.environ["NEXUS_MEMORY_PATH"] = tempfile.mkdtemp(prefix="nexus_memory_bridge_l3_")
os.environ["CIPHER_MEMORY_PATH"] = tempfile.mkdtemp(prefix="cipher_memory_bridge_l3_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(tempfile.mkdtemp(prefix="pending_actions_bridge_l3_"), "pending_actions.json")
TEST_DIR = tempfile.mkdtemp(prefix="bridge_l3_files_")

from dotenv import load_dotenv
load_dotenv(override=True)

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

from agents.nexus import chat
from agents.cipher import cipher_tools
from shared import pending_actions

print("=== L3 REAL END-TO-END ===\n")

# --- 1. Python-side pre-check path, real NEXUS + real CIPHER ---
print("--- Test 1: keyword pre-check routes to real CIPHER ---")
out = "".join(chat.stream_nexus("write me a script that prints the numbers 1 to 10"))
print(f"  FULL OUTPUT:\n{out}\n")
check("NEXUS's own brief part appears before the separator", "---\nCIPHER:" in out)
nexus_part = out.split("---\nCIPHER:")[0]
cipher_part = out.split("---\nCIPHER:")[1] if "---\nCIPHER:" in out else ""
check("NEXUS's part is brief (didn't try to answer the coding question itself)", len(nexus_part) < 400)
check("CIPHER's real part looks like an actual answer (non-trivial length)", len(cipher_part) > 20)

# --- 2. A real approval-gated action reaches all the way through the bridge ---
print("\n--- Test 2: a real SAVE_FILE proposal surfaces through the bridge (Lesson #1 proof) ---")
target_path = os.path.join(TEST_DIR, "bridge_hello.py").replace("\\", "\\\\")
out2 = "".join(chat.stream_nexus(
    f"write me a script that prints 'hello from the bridge' and save it at exactly this path using SAVE_FILE: {target_path}"
))
print(f"  FULL OUTPUT:\n{out2}\n")
check("the waiting-for-approval note surfaces through NEXUS's own output", "Waiting for your approval" in out2)
real_path = os.path.join(TEST_DIR, "bridge_hello.py")
check("the real file was NOT created yet (proposal only, exactly like direct CIPHER chat)", not os.path.exists(real_path))

pending = pending_actions.list_pending_actions(agent="cipher")
check("a real pending action exists in CIPHER's own queue (not a NEXUS-specific copy)", len(pending) >= 1)
if pending:
    result = cipher_tools.approve_and_execute(pending[-1]["id"])
    print(f"  approval result: {result}")
    check("approving it through the SAME queue actually creates the real file", os.path.exists(real_path))

# --- 3. Fallback scan path - real NEXUS deciding on its own to bridge ---
print("\n--- Test 3: NEXUS's own model decides to bridge, with no exact keyword match ---")
out3 = "".join(chat.stream_nexus("Something in my program keeps crashing and I have no idea why - can CIPHER take a look?"))
print(f"  FULL OUTPUT:\n{out3}\n")
bridged = "---\nCIPHER:" in out3
check("real model bridged this to CIPHER on its own (fallback scan)", bridged)
if not bridged:
    print("  NOTE: real models vary run to run - if this fails, read NEXUS's actual reply above before assuming a bug.")

# --- 4. No bridge at all for an ordinary message ---
print("\n--- Test 4: an ordinary message never reaches CIPHER ---")
out4 = "".join(chat.stream_nexus("what's a good way to unwind after a long day?"))
check("no CIPHER separator appears for an unrelated message", "---\nCIPHER:" not in out4)

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")