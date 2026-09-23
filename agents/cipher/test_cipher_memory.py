"""
CIPHER memory increment - L1 (static) + L2 (smoke, mocked model,
real local ChromaDB in a throwaway temp dir).
Run with: python agents/cipher/test_cipher_memory.py
"""
import ast, os, sys, tempfile, types
sys.path.insert(0, os.path.abspath("."))

# Point CIPHER's memory at a throwaway temp dir BEFORE anything imports
# shared.cipher_memory, so this test run never touches the real
# D:\Projects\forge\memory\cipher data.
os.environ["CIPHER_MEMORY_PATH"] = tempfile.mkdtemp(prefix="cipher_memory_test_")

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))

print("=== L1 STATIC ===")
for f in ["shared/cipher_memory.py", "agents/cipher/chat.py", "shared/memory_context.py", "shared/agent_topics.py"]:
    try:
        ast.parse(open(f).read())
        check(f"{f} parses as valid Python", True)
    except SyntaxError as e:
        check(f"{f} parses as valid Python", False, str(e))

# Mock only the model - ChromaDB and search-labeling logic run for real
fake_model_client = types.ModuleType("shared.model_client")
fake_model_client.stream_gemini = lambda system_prompt, messages, location="": iter(["mocked response chunk"])  # type: ignore[attr-defined]
sys.modules["shared.model_client"] = fake_model_client

fake_web_search = types.ModuleType("shared.web_search")
fake_web_search.WEB_SEARCH_FAILED_PREFIX = "[WEB_SEARCH_FAILED]"  # type: ignore[attr-defined]
fake_web_search.web_search = lambda query, num_results=3: f"Web search results:\n\n1. Fake result for {query}"  # type: ignore[attr-defined]
sys.modules["shared.web_search"] = fake_web_search

from agents.cipher import chat
from shared import cipher_memory
from shared.memory_context import MEMORY_WORTHY_CATEGORIES

# TEST-ONLY: swap ChromaDB's default embedding function (which needs a
# one-time internet download) for a network-free stand-in, so this test
# suite stays true to the "L1/L2 need zero network" convention. This
# patch does NOT touch shared/cipher_memory.py itself.
import hashlib
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

class _FakeEmbeddingFunction(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        return [[b / 255.0 for b in hashlib.sha256(t.encode()).digest()[:16]] for t in input]  # type: ignore[return-value]

def _fake_get_collection():
    if cipher_memory._collection is None:
        os.makedirs(cipher_memory.CIPHER_MEMORY_PATH, exist_ok=True)
        cipher_memory._client = chromadb.PersistentClient(path=cipher_memory.CIPHER_MEMORY_PATH)
        cipher_memory._collection = cipher_memory._client.get_or_create_collection(
            name="cipher_memory", embedding_function=_FakeEmbeddingFunction())
    return cipher_memory._collection
cipher_memory._get_collection = _fake_get_collection

print("\n=== L2 SMOKE ===")

# --- needs_memory_search ---
check("'remember' triggers memory search", chat.needs_memory_search("what did you remember about my auth setup") is True)
check("'we discussed' triggers memory search", chat.needs_memory_search("like we discussed last week") is True)
check("plain coding question does NOT trigger memory search", chat.needs_memory_search("write a function to reverse a string") is False)

# --- extract_memory_saves ---
saves = chat.extract_memory_saves("Here's the fix.\nMEMORY_SAVE: decision | Using FastAPI, not Flask")
check("valid MEMORY_SAVE line extracted", saves == [("decision", "Using FastAPI, not Flask")])

saves2 = chat.extract_memory_saves("Sure.\nMEMORY_SAVE: nonsense_category | should be dropped")
check("invalid category is silently skipped, not saved", saves2 == [])

saves3 = chat.extract_memory_saves("Just a normal reply, nothing to remember here.")
check("normal response with no marker extracts nothing", saves3 == [])

# --- strip_memory_markers ---
raw = "Here's the fix.\nMEMORY_SAVE: decision | Using FastAPI, not Flask"
stripped = chat.strip_memory_markers(raw)
check("MEMORY_SAVE line removed from display/history text", "MEMORY_SAVE:" not in stripped and "Here's the fix." in stripped)

# --- shared.cipher_memory: filtering (Lesson #3) ---
check("category not in MEMORY_WORTHY_CATEGORIES is rejected", cipher_memory.save_memory("random_junk", "should not save") is False)
check("empty content is rejected even with a valid category", cipher_memory.save_memory("decision", "   ") is False)
saved_ok = cipher_memory.save_memory("project_fact", "Financial Tracker reads from finance.json")
check("valid category + real content is accepted", saved_ok is True)
check("CIPHER's four categories are all in the shared worth-saving set", {"decision", "correction", "preference", "project_fact"} <= MEMORY_WORTHY_CATEGORIES)

# --- shared.cipher_memory: retrieval ---
cipher_memory.save_memory("decision", "We are using FastAPI for the backend, not Flask")
found = cipher_memory.search_memory("what backend framework are we using")
check("search_memory retrieves a relevant saved item", any("FastAPI" in item for item in found))

# --- Lesson #2 fix: web search results get the background label ---
captured = {}
def capturing_stream_gemini(system_prompt, messages, location=""):
    captured["messages"] = messages
    return iter(["mocked response chunk"])
original_stream_gemini = chat.stream_gemini
chat.stream_gemini = capturing_stream_gemini
list(chat.stream_cipher("what's the latest version of FastAPI"))
sent = captured["messages"][-1]["content"]
check("web search results are wrapped in the 'Background ... may be outdated' label (Lesson #2 fix)",
      "Background web search results" in sent and "may be outdated or unrelated" in sent)
chat.stream_gemini = original_stream_gemini

# --- memory retrieval gets wired into the prompt when triggered ---
chat.search_memory = lambda query, n_results=3: ["We are using FastAPI for the backend, not Flask"]
captured2 = {}
def capturing_stream_gemini2(system_prompt, messages, location=""):
    captured2["messages"] = messages
    return iter(["mocked response chunk"])
chat.stream_gemini = capturing_stream_gemini2
list(chat.stream_cipher("remember what backend framework we picked?"))
sent2 = captured2["messages"][-1]["content"]
check("triggered memory retrieval gets wrapped in the background-memory label",
      "Background memory" in sent2 and "FastAPI" in sent2)
chat.stream_gemini = original_stream_gemini

# --- memory retrieval is NOT triggered on an unrelated message ---
captured3 = {}
def capturing_stream_gemini3(system_prompt, messages, location=""):
    captured3["messages"] = messages
    return iter(["mocked response chunk"])
chat.stream_gemini = capturing_stream_gemini3
list(chat.stream_cipher("write a function to reverse a string"))
sent3 = captured3["messages"][-1]["content"]
check("memory is NOT injected into an unrelated question", "Background memory" not in sent3)
chat.stream_gemini = original_stream_gemini

# --- end-to-end: a MEMORY_SAVE marker in the model's response actually gets saved ---
saved_calls = []
chat.save_memory = lambda category, content: saved_calls.append((category, content))
def model_with_memory_marker(system_prompt, messages, location=""):
    return iter(["Done. That's a solid approach.\nMEMORY_SAVE: preference | Always give FIND/REPLACE blocks, not prose diffs"])
chat.stream_gemini = model_with_memory_marker
out = list(chat.stream_cipher("from now on always give me find/replace blocks"))
check("MEMORY_SAVE marker in the response triggers save_memory() automatically",
      saved_calls == [("preference", "Always give FIND/REPLACE blocks, not prose diffs")])
check("raw response text is still what gets streamed out (marker included, caller strips for history)",
      "MEMORY_SAVE:" in "".join(out))
chat.stream_gemini = original_stream_gemini
chat.save_memory = cipher_memory.save_memory  # restore real one
chat.search_memory = cipher_memory.search_memory  # restore real one

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")
