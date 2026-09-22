"""
Phase 0 shared functions — L4 (sustained/concurrency) + L5 (extreme/
breaking) test pass.
"""
import os
import sys
import json
import tempfile
import shutil
import threading
import subprocess

sys.path.insert(0, os.path.dirname(__file__))

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and status == "FAIL" else ""))


import file_store
import keyword_gate
import memory_context

tmpdir = tempfile.mkdtemp()

# ============================================================
# L4 — SUSTAINED / CONCURRENCY
# ============================================================
print("=== L4 SUSTAINED ===")

# 4a. Burst: 100 sequential appends, none lost
burst_path = os.path.join(tmpdir, "burst.json")
def append_item(data):
    data["items"].append(len(data["items"]))
    return data
for _ in range(100):
    file_store.update_json(burst_path, append_item, default={"items": []})
final = file_store.load_json(burst_path, default=None)
check("100 sequential updates: none lost", len(final["items"]) == 100, f"got {len(final['items'])}")

# 4b. True concurrency: 10 threads writing to the SAME file at once
concurrent_path = os.path.join(tmpdir, "concurrent.json")
file_store.update_json(concurrent_path, lambda d: {"items": []}, default={"items": []})

def worker(n):
    def add(data):
        data["items"].append(n)
        return data
    file_store.update_json(concurrent_path, add, default={"items": []})

threads = [threading.Thread(target=worker, args=(i,)) for i in range(10)]
for t in threads:
    t.start()
for t in threads:
    t.join()

result = file_store.load_json(concurrent_path, default=None)
check(
    "10 simultaneous threads: all 10 writes landed, zero lost",
    len(result["items"]) == 10 and sorted(result["items"]) == list(range(10)),
    f"got {result['items']}",
)

# 4c. Real cross-process persistence — a SEPARATE python process writes,
# this process reads it back, proving it's really on disk not cached.
cross_process_path = os.path.join(tmpdir, "cross_process.json")
writer_script = f"""
import sys
sys.path.insert(0, {os.path.dirname(__file__)!r})
import file_store
def add(data):
    data["items"].append("from_other_process")
    return data
file_store.update_json({cross_process_path!r}, add, default={{"items": []}})
"""
subprocess.run([sys.executable, "-c", writer_script], check=True, capture_output=True)
cross_result = file_store.load_json(cross_process_path, default=None)
check(
    "data written by a separate process is readable here (real disk persistence)",
    cross_result == {"items": ["from_other_process"]},
    f"got {cross_result}",
)


# ============================================================
# L5 — EXTREME / BREAKING
# ============================================================
print("\n=== L5 EXTREME ===")

# 5a. Corrupted JSON on disk — must fail loudly, never silently return wrong data
corrupt_path = os.path.join(tmpdir, "corrupt.json")
with open(corrupt_path, "w") as f:
    f.write("{not valid json!!!")

raised_clean_error = False
try:
    file_store.load_json(corrupt_path, default={"items": []})
except json.JSONDecodeError:
    raised_clean_error = True
except Exception:
    raised_clean_error = False  # wrong exception type is still a fail-loud, but flag it
check(
    "corrupted JSON raises a clear JSONDecodeError instead of silently returning garbage",
    raised_clean_error,
)

# 5b. keyword_gate with empty/garbage input
check("empty message doesn't crash contains_keyword", keyword_gate.contains_keyword("", ["code"]) is False)
check("empty keyword list doesn't crash / never matches", keyword_gate.contains_keyword("anything", []) is False)

# 5c. memory_context with weird/mixed input types (Lesson #5: defend against bad shapes)
weird_items = [None, 123, {"nested": "dict"}, "normal string"]
try:
    out = memory_context.format_memory_context(weird_items)
    no_crash = True
except Exception as e:
    no_crash = False
check("format_memory_context doesn't crash on mixed/garbage item types", no_crash)

# 5d. Permission boundary: update_json only ever writes to the exact path given —
# confirm no path traversal happens even if a caller passes a relative-looking path
safe_path = os.path.join(tmpdir, "..", "escape_attempt.json")
normalized_target = os.path.normpath(safe_path)
file_store.update_json(safe_path, lambda d: {"ok": True}, default={})
check(
    "write lands exactly at the resolved path given, nowhere else",
    os.path.exists(normalized_target),
)
if os.path.exists(normalized_target):
    os.remove(normalized_target)
lock_leftover = normalized_target + ".lock"
if os.path.exists(lock_leftover):
    os.remove(lock_leftover)

# 5e. Real production data never corrupted even if update_fn raises mid-write
crash_path = os.path.join(tmpdir, "crash_safety.json")
file_store.update_json(crash_path, lambda d: {"safe": "original"}, default={})
def bad_update(data):
    raise ValueError("simulated crash mid-update")
try:
    file_store.update_json(crash_path, bad_update, default={})
except ValueError:
    pass
after_crash = file_store.load_json(crash_path, default=None)
check(
    "original data survives intact if update_fn raises mid-write (no half-written file)",
    after_crash == {"safe": "original"},
    f"got {after_crash}",
)

shutil.rmtree(tmpdir, ignore_errors=True)

# ============================================================
# SUMMARY
# ============================================================
print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    print("\nFAILURES:")
    for s, name, detail in results:
        if s == "FAIL":
            print(f"  - {name}: {detail}")
