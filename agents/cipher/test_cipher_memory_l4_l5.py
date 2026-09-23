"""
CIPHER memory increment - L4 (sustained/concurrency) + L5 (extreme/
breaking). Real ChromaDB + real Ollama embeddings, no mocks - same
rigor as agents/cipher/test_cipher_l4_l5.py for core chat.
Needs: Ollama running locally, nomic-embed-text already pulled.
Run with: python agents/cipher/test_cipher_memory_l4_l5.py
"""
import os, sys, tempfile, threading
sys.path.insert(0, os.path.abspath("."))

os.environ["CIPHER_MEMORY_PATH"] = tempfile.mkdtemp(prefix="cipher_memory_l4l5_")

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

from shared import cipher_memory
from agents.cipher import chat

print("=== L4 SUSTAINED / CONCURRENCY ===\n")

print("--- Test 1: 20 simultaneous save_memory calls - no data loss ---")
before_count = cipher_memory._get_collection().count()

def save_in_thread(i):
    cipher_memory.save_memory("project_fact", f"Concurrent test fact number {i}")

threads = [threading.Thread(target=save_in_thread, args=(i,)) for i in range(20)]
for t in threads:
    t.start()
for t in threads:
    t.join()

after_count = cipher_memory._get_collection().count()
check(f"all 20 concurrent saves landed (before={before_count}, after={after_count})",
      after_count - before_count == 20)

print("\n--- Test 2: 30 sequential real searches - no crash ---")
crashed = False
try:
    for i in range(30):
        cipher_memory.search_memory(f"test query number {i}")
except Exception as e:
    crashed = True
    print(f"  crashed on iteration: {e}")
check("30 sequential real searches complete without crashing", not crashed)

print("\n=== L5 EXTREME / BREAKING ===\n")

print("--- Test 3: very large content (~50,000 chars) ---")
huge_content = "The system architecture decision is X. " * 1250
try:
    ok = cipher_memory.save_memory("decision", huge_content)
    check("50,000-char content handled without a raw crash", True, f"save_memory returned {ok}")
except Exception as e:
    check("50,000-char content handled without a raw crash", False, f"raised {type(e).__name__}: {e}")

print("\n--- Test 4: unicode and emoji content ---")
try:
    ok = cipher_memory.save_memory("preference", "Use émojis 🎉 and ünïcödé in comments — 日本語 too")
    check("unicode/emoji content saves without crashing", ok is True)
except Exception as e:
    check("unicode/emoji content saves without crashing", False, f"raised {type(e).__name__}: {e}")

print("--- Test 5: None as content is rejected, not crashed on ---")
try:
    ok = cipher_memory.save_memory("decision", None)  # type: ignore[arg-type]
    check("None content is safely rejected (not saved, no crash)", ok is False)
except Exception as e:
    check("None content is safely rejected (not saved, no crash)", False, f"raised {type(e).__name__}: {e}")

print("\n--- Test 6: None as category is rejected, not crashed on ---")
try:
    ok = cipher_memory.save_memory(None, "some real content here")  # type: ignore[arg-type]
    check("None category is safely rejected (not saved, no crash)", ok is False)
except Exception as e:
    check("None category is safely rejected (not saved, no crash)", False, f"raised {type(e).__name__}: {e}")
print("\n--- Test 7: empty-string search query doesn't crash ---")
try:
    result = cipher_memory.search_memory("")
    check("empty search query handled without crashing", isinstance(result, list))
except Exception as e:
    check("empty search query handled without crashing", False, f"raised {type(e).__name__}: {e}")

print("\n--- Test 8: multiple MEMORY_SAVE lines - all valid ones extracted, none dropped silently ---")
multi = "First point.\nMEMORY_SAVE: decision | Point A\nSecond point.\nMEMORY_SAVE: preference | Point B"
saves = chat.extract_memory_saves(multi)
check("both valid MEMORY_SAVE lines are extracted (prompt says 'just one', code still handles more)",
      saves == [("decision", "Point A"), ("preference", "Point B")])

print("\n--- Test 9: malformed MEMORY_SAVE lines don't crash extraction ---")
malformed = "No pipe here.\nMEMORY_SAVE: decision no delimiter at all\nMEMORY_SAVE: |  \nMEMORY_SAVE: DECISION | Uppercase category still works"
try:
    saves2 = chat.extract_memory_saves(malformed)
    check("malformed lines skipped, uppercase category still normalized and accepted",
          saves2 == [("decision", "Uppercase category still works")])
except Exception as e:
    check("malformed lines skipped, uppercase category still normalized and accepted", False, f"raised {type(e).__name__}: {e}")

print("\n--- Test 10: Ollama unreachable fails loudly, not silently ---")
original_url = cipher_memory.OLLAMA_EMBED_URL
cipher_memory.OLLAMA_EMBED_URL = "http://localhost:1/api/embeddings"  # nothing listens here
try:
    cipher_memory.save_memory("decision", "this should fail to embed")
    check("unreachable Ollama raises a clear error instead of saving silently", False, "no exception was raised")
except RuntimeError as e:
    check("unreachable Ollama raises the clear RuntimeError we wrote (Lesson #12: fail loudly)",
          "Ollama" in str(e) and "nomic-embed-text" in str(e))
except Exception as e:
    check("unreachable Ollama raises the clear RuntimeError we wrote (Lesson #12: fail loudly)",
          False, f"raised the wrong exception type instead: {type(e).__name__}: {e}")
finally:
    cipher_memory.OLLAMA_EMBED_URL = original_url

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")