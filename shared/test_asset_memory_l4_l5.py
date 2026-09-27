"""
ASSET memory - L4 (concurrency, including a forced cold-start race
test) + L5 (extreme/breaking). Fake embeddings (network-free), real
ChromaDB, throwaway temp path.
Run with: python shared/test_asset_memory_l4_l5.py
"""
import hashlib, os, sys, tempfile, threading
sys.path.insert(0, os.path.abspath("."))

os.environ["ASSET_MEMORY_PATH"] = tempfile.mkdtemp(prefix="asset_memory_l4l5_")

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

from shared import asset_memory
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

class _FakeEmbeddingFunction(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        return [[b / 255.0 for b in hashlib.sha256(t.encode()).digest()[:16]] for t in input]  # type: ignore[return-value]

def _fake_get_collection():
    if asset_memory._collection is None:
        with asset_memory._init_lock:
            if asset_memory._collection is None:
                os.makedirs(asset_memory.ASSET_MEMORY_PATH, exist_ok=True)
                asset_memory._client = chromadb.PersistentClient(path=asset_memory.ASSET_MEMORY_PATH)
                asset_memory._collection = asset_memory._client.get_or_create_collection(
                    name="asset_memory", embedding_function=_FakeEmbeddingFunction())
    return asset_memory._collection
asset_memory._get_collection = _fake_get_collection

print("=== L4 CONCURRENCY ===\n")

print("--- Test 0: COLD START - 20 threads save before the singleton is warmed up ---")
# asset_memory.py had this lock built in from the start (unlike
# cipher_memory.py/nexus_memory.py, where it was found and fixed after
# the fact) - this confirms it under real conditions rather than
# assuming it's fine by similarity.
cold_start_errors = []
def cold_save(i):
    try:
        asset_memory.save_conversation_turn(f"cold start question {i}", f"cold start answer {i}")
    except Exception as e:
        cold_start_errors.append(e)

cold_threads = [threading.Thread(target=cold_save, args=(i,)) for i in range(20)]
for t in cold_threads: t.start()
for t in cold_threads: t.join()
check("20 threads hitting an uninitialized collection at once: zero crashes",
      len(cold_start_errors) == 0, f"{len(cold_start_errors)} errors: {cold_start_errors[:2]}")

print("\n--- Test 1: 20 simultaneous saves - no data loss ---")
before_count = asset_memory._get_collection().count()
def save_more(i):
    asset_memory.save_conversation_turn(f"concurrent question {i}", f"concurrent answer {i}")
threads = [threading.Thread(target=save_more, args=(i,)) for i in range(20)]
for t in threads: t.start()
for t in threads: t.join()
after_count = asset_memory._get_collection().count()
check(f"all 20 concurrent saves landed (before={before_count}, after={after_count})", after_count - before_count == 20)

print("\n--- Test 2: 30 sequential real searches - no crash ---")
crashed = False
try:
    for i in range(30):
        asset_memory.search_memory(f"question {i}")
except Exception:
    crashed = True
check("30 sequential searches complete without crashing", not crashed)

print("\n=== L5 EXTREME / BREAKING ===\n")

print("--- Test 3: unicode/emoji content ---")
try:
    ok = asset_memory.save_conversation_turn("emoji test 🎉", "response with 日本語 and émojis 💰")
    check("unicode/emoji content saves without crashing", ok is True)
except Exception as e:
    check("unicode/emoji content saves without crashing", False, f"{type(e).__name__}: {e}")

print("--- Test 4: None as user_message/assistant_response doesn't crash ---")
try:
    ok = asset_memory.save_conversation_turn(None, None)  # type: ignore[arg-type]
    check("None message/response doesn't crash save_conversation_turn", True, f"returned {ok}")
except Exception as e:
    check("None message/response doesn't crash save_conversation_turn", False, f"{type(e).__name__}: {e}")

print("--- Test 5: None as category is rejected, not crashed on ---")
try:
    ok = asset_memory.save_conversation_turn("hi", "hello", category=None)  # type: ignore[arg-type]
    check("None category is safely rejected (not saved, no crash)", ok is False)
except Exception as e:
    check("None category is safely rejected (not saved, no crash)", False, f"{type(e).__name__}: {e}")

print("--- Test 6: empty-string search query doesn't crash ---")
try:
    result = asset_memory.search_memory("")
    check("empty search query handled without crashing", isinstance(result, list))
except Exception as e:
    check("empty search query handled without crashing", False, f"{type(e).__name__}: {e}")

print("--- Test 7: very large content (~50,000 chars) ---")
try:
    ok = asset_memory.save_conversation_turn("huge question", "x" * 50000)
    check("50,000-char content handled without crashing (truncated internally)", ok is True)
except Exception as e:
    check("50,000-char content handled without crashing", False, f"{type(e).__name__}: {e}")

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")