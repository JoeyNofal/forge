"""
Phase 0 shared functions — L1 (static) + L2 (smoke) test pass.
Self-check before handing to Youssef.
"""
import ast
import os
import sys
import tempfile
import shutil

sys.path.insert(0, os.path.dirname(__file__))

results = []

def check(name, condition, detail=""):
    status = "PASS" if condition else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and status == "FAIL" else ""))


# ============================================================
# L1 — STATIC
# ============================================================
print("=== L1 STATIC ===")

for fname in ["keyword_gate.py", "memory_context.py", "file_store.py", "agent_topics.py"]:
    path = os.path.join(os.path.dirname(__file__), fname)
    try:
        with open(path, "r", encoding="utf-8") as f:
            source = f.read()
        ast.parse(source)
        check(f"{fname} parses as valid Python", True)
    except SyntaxError as e:
        check(f"{fname} parses as valid Python", False, str(e))

import keyword_gate
import memory_context
import file_store
import agent_topics

check("keyword_gate defines contains_keyword", hasattr(keyword_gate, "contains_keyword"))
check("keyword_gate defines should_refuse", hasattr(keyword_gate, "should_refuse"))
check("memory_context defines format_memory_context", hasattr(memory_context, "format_memory_context"))
check("memory_context defines is_memory_worthy", hasattr(memory_context, "is_memory_worthy"))
check("file_store defines load_json", hasattr(file_store, "load_json"))
check("file_store defines update_json", hasattr(file_store, "update_json"))
for agent in ["CIPHER", "ASSET", "ATLAS", "DRIVE", "CASE"]:
    check(f"agent_topics defines {agent}_NON_TOPIC", hasattr(agent_topics, f"{agent}_NON_TOPIC"))
    check(f"agent_topics defines {agent}_INTENT", hasattr(agent_topics, f"{agent}_INTENT"))


# ============================================================
# L2 — SMOKE (real calls, sandboxed)
# ============================================================
print("\n=== L2 SMOKE ===")

# keyword_gate.py — the exact bugs from Lesson #6
check(
    "'workout program' does NOT trip CIPHER's refusal (old bug)",
    keyword_gate.should_refuse("give me a workout program", agent_topics.CIPHER_NON_TOPIC, agent_topics.CIPHER_INTENT) is False,
)
check(
    "'food' does NOT trip CIPHER's refusal on a real coding question (old bug)",
    keyword_gate.should_refuse("write me a script to log my food budget", agent_topics.CIPHER_NON_TOPIC, agent_topics.CIPHER_INTENT) is False,
)
check(
    "pure off-topic message DOES get refused (weather -> CIPHER)",
    keyword_gate.should_refuse("what's the weather today", agent_topics.CIPHER_NON_TOPIC, agent_topics.CIPHER_INTENT) is True,
)
check(
    "substring false-positive avoided: 'codependent' should not match 'code'",
    keyword_gate.contains_keyword("I feel codependent lately", ["code"]) is False,
)
check(
    "real whole-word match still works: 'code' matches 'code'",
    keyword_gate.contains_keyword("can you review my code", ["code"]) is True,
)

# memory_context.py
empty_result = memory_context.format_memory_context([])
check("empty memory list returns empty string", empty_result == "")

labeled = memory_context.format_memory_context(["Joey lives in South Bend"], label="memory")
check("non-empty memory gets labeled as background", "background" in labeled.lower() and "authoritative" in labeled.lower())

check("'workout_log' category is memory-worthy", memory_context.is_memory_worthy("workout_log") is True)
check("'conversation' category is NOT memory-worthy (Lesson #3 filter)", memory_context.is_memory_worthy("conversation") is False)

# file_store.py — real file I/O in a sandbox temp dir
tmpdir = tempfile.mkdtemp()
try:
    test_path = os.path.join(tmpdir, "test_data.json")

    # load_json on a file that doesn't exist yet
    loaded = file_store.load_json(test_path, default={"items": []})
    check("load_json returns default when file doesn't exist", loaded == {"items": []})

    # update_json creates the file and appends
    def add_item(data):
        data["items"].append("first")
        return data
    result1 = file_store.update_json(test_path, add_item, default={"items": []})
    check("update_json creates file and saves first item", result1 == {"items": ["first"]})

    # second update appends, doesn't overwrite (append-only check)
    def add_second(data):
        data["items"].append("second")
        return data
    result2 = file_store.update_json(test_path, add_second, default={"items": []})
    check("update_json appends without losing first item", result2 == {"items": ["first", "second"]})

    # confirm it's really on disk, not just in-memory
    on_disk = file_store.load_json(test_path, default=None)
    check("data really persisted to disk", on_disk == {"items": ["first", "second"]})

    # lock file was created
    check("lock file was created alongside data file", os.path.exists(test_path + ".lock"))

finally:
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
