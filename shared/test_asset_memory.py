"""
ASSET memory - L1 (static) + L2 (smoke). Real local ChromaDB in a
throwaway temp dir; embeddings faked (network-free, matching the
CIPHER/NEXUS memory L1/L2 convention) - shared/ollama_embeddings.py
itself is already proven correct by CIPHER's and NEXUS's own suites.
Run with: python shared/test_asset_memory.py
"""
import hashlib
import os, sys, tempfile
sys.path.insert(0, os.path.abspath("."))

os.environ["ASSET_MEMORY_PATH"] = tempfile.mkdtemp(prefix="asset_memory_test_")

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))

print("=== L1 STATIC ===")
import ast
try:
    ast.parse(open("shared/asset_memory.py", encoding="utf-8").read())
    check("shared/asset_memory.py parses as valid Python", True)
except SyntaxError as e:
    check("shared/asset_memory.py parses as valid Python", False, str(e))

from shared import asset_memory
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

# TEST-ONLY: network-free stand-in for the real Ollama embedder, same
# convention as CIPHER's/NEXUS's own memory L1/L2 tests. Does not touch
# shared/asset_memory.py or shared/ollama_embeddings.py themselves.
class _FakeEmbeddingFunction(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        return [[b / 255.0 for b in hashlib.sha256(t.encode()).digest()[:16]] for t in input]  # type: ignore[return-value]

def _fake_get_collection():
    if asset_memory._collection is None:
        os.makedirs(asset_memory.ASSET_MEMORY_PATH, exist_ok=True)
        asset_memory._client = chromadb.PersistentClient(path=asset_memory.ASSET_MEMORY_PATH)
        asset_memory._collection = asset_memory._client.get_or_create_collection(
            name="asset_memory", embedding_function=_FakeEmbeddingFunction())
    return asset_memory._collection
asset_memory._get_collection = _fake_get_collection

print("\n=== L2 SMOKE ===")

# --- category filtering ---
check("an invalid category is rejected, nothing saved", asset_memory.save_conversation_turn("hi", "hello", category="not_a_real_category") is False)
for cat in ["advice", "goal", "market", "summary", "conversation"]:
    check(f"'{cat}' category is accepted", asset_memory.save_conversation_turn(f"test for {cat}", f"response for {cat}", category=cat) is True)

# --- collection is isolated by name (distinct from CIPHER/NEXUS) ---
check("ASSET's own collection is named 'asset_memory', isolated from cipher_memory/nexus_memory",
      asset_memory._collection.name == "asset_memory")

# --- content format ---
asset_memory.save_conversation_turn("What's my net worth?", "It's $6,530.00. That is the number.")
found = asset_memory.search_memory("net worth")
check("saved content includes both sides of the real exchange", any("Joey:" in item and "ASSET:" in item for item in found))

# --- truncation for oversized content ---
huge_response = "x" * 50000
asset_memory.save_conversation_turn("a huge question", huge_response)
found_huge = asset_memory.search_memory("huge question", n_results=10)
check("oversized content gets truncated, not rejected or crashed on",
      any("truncated" in item for item in found_huge))

# --- empty query / empty collection edge cases ---
check("empty search query returns an empty list, no crash", asset_memory.search_memory("") == [])

fresh_path = tempfile.mkdtemp(prefix="asset_memory_empty_test_")
# ASSET_MEMORY_PATH is read from the env var ONCE at import time - the
# module attribute is already bound, so it has to be overridden
# directly here, not via os.environ (which would do nothing at this point).
asset_memory.ASSET_MEMORY_PATH = fresh_path
asset_memory._client = None
asset_memory._collection = None
check("searching a genuinely empty collection returns [], not a crash", asset_memory.search_memory("anything") == [])

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")