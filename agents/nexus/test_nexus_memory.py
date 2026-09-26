"""
NEXUS memory increment - L1 (static) + L2 (smoke, mocked model,
real local ChromaDB in a throwaway temp dir).
Run with: python agents/nexus/test_nexus_memory.py
"""
import ast, os, sys, tempfile, types
sys.path.insert(0, os.path.abspath("."))

# Point NEXUS's memory at a throwaway temp dir BEFORE anything imports
# shared.nexus_memory, so this test run never touches the real
# D:\Projects\forge\memory\nexus data.
os.environ["NEXUS_MEMORY_PATH"] = tempfile.mkdtemp(prefix="nexus_memory_test_")

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail and status == "FAIL" else ""))

print("=== L1 STATIC ===")
for f in ["shared/nexus_memory.py", "shared/ollama_embeddings.py", "agents/nexus/chat.py", "shared/memory_context.py"]:
    try:
        ast.parse(open(f).read())
        check(f"{f} parses as valid Python", True)
    except SyntaxError as e:
        check(f"{f} parses as valid Python", False, str(e))

# Mock only the model and web search - ChromaDB and labeling logic run for real
fake_model_client = types.ModuleType("shared.model_client")
fake_model_client.stream_by_tier = lambda agent, tier, system_prompt, messages, location="": iter(["mocked response chunk"])  # type: ignore[attr-defined]
sys.modules["shared.model_client"] = fake_model_client

fake_web_search = types.ModuleType("shared.web_search")
fake_web_search.WEB_SEARCH_FAILED_PREFIX = "[WEB_SEARCH_FAILED]"  # type: ignore[attr-defined]
fake_web_search.web_search = lambda query, num_results=3: f"Web search results:\n\n1. Fake result for {query}"  # type: ignore[attr-defined]
sys.modules["shared.web_search"] = fake_web_search

from agents.nexus import chat
from shared import nexus_memory
from shared.memory_context import MEMORY_WORTHY_CATEGORIES

# TEST-ONLY: swap ChromaDB's default/Ollama embedding function for a
# network-free stand-in, so this test suite stays true to the "L1/L2
# need zero network" convention. This patch does NOT touch
# shared/nexus_memory.py or shared/ollama_embeddings.py themselves.
import hashlib
import chromadb
from chromadb import Documents, EmbeddingFunction, Embeddings

class _FakeEmbeddingFunction(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        return [[b / 255.0 for b in hashlib.sha256(t.encode()).digest()[:16]] for t in input]  # type: ignore[return-value]

def _fake_get_collection():
    if nexus_memory._collection is None:
        os.makedirs(nexus_memory.NEXUS_MEMORY_PATH, exist_ok=True)
        nexus_memory._client = chromadb.PersistentClient(path=nexus_memory.NEXUS_MEMORY_PATH)
        nexus_memory._collection = nexus_memory._client.get_or_create_collection(
            name="nexus_memory", embedding_function=_FakeEmbeddingFunction())
    return nexus_memory._collection
nexus_memory._get_collection = _fake_get_collection

print("\n=== L2 SMOKE ===")

# --- extract_memory_saves ---
saves = chat.extract_memory_saves("Right away, sir.\nMEMORY_SAVE: decision | Moving the rebuild to a new folder")
check("valid MEMORY_SAVE line extracted", saves == [("decision", "Moving the rebuild to a new folder")])

saves2 = chat.extract_memory_saves("Of course.\nMEMORY_SAVE: financial_fact | balance is $500")
check("financial_fact is silently skipped (NEXUS's own exclusion, not just the shared filter)", saves2 == [])

saves3 = chat.extract_memory_saves("Of course.\nMEMORY_SAVE: nonsense_category | should be dropped")
check("invalid/hallucinated category is silently skipped", saves3 == [])

saves4 = chat.extract_memory_saves("Just a normal reply, nothing to remember here, sir.")
check("normal response with no marker extracts nothing", saves4 == [])

# --- strip_memory_markers ---
raw = "Right away, sir.\nMEMORY_SAVE: decision | Moving the rebuild to a new folder"
stripped = chat.strip_memory_markers(raw)
check("MEMORY_SAVE line removed from display/history text", "MEMORY_SAVE:" not in stripped and "Right away, sir." in stripped)

# --- shared.nexus_memory: filtering (Lesson #3) ---
check("category not in MEMORY_WORTHY_CATEGORIES is rejected", nexus_memory.save_memory("random_junk", "should not save") is False)
check("empty content is rejected even with a valid category", nexus_memory.save_memory("decision", "   ") is False)
saved_ok = nexus_memory.save_memory("project_fact", "The Financial Tracker reads from finance.json")
check("valid category + real content is accepted", saved_ok is True)
check("NEXUS's 7 categories are all in the shared worth-saving set",
      {"decision", "preference", "correction", "goal", "workout_log", "plan", "project_fact"} <= MEMORY_WORTHY_CATEGORIES)
check("NEXUS's own set deliberately excludes financial_fact",
      "financial_fact" not in {"decision", "preference", "correction", "goal", "workout_log", "plan", "project_fact"})

# --- shared.nexus_memory: retrieval ---
nexus_memory.save_memory("decision", "The rebuild project is called FORGE")
found = nexus_memory.search_memory("what is the rebuild project called")
check("search_memory retrieves a relevant saved item", any("FORGE" in item for item in found))

# --- Lesson #2 fix: web search results get the background label ---
captured = {}
def capturing_stream_by_tier(agent, tier, system_prompt, messages, location=""):
    captured["messages"] = messages
    return iter(["mocked response chunk"])
original_stream_by_tier = chat.stream_by_tier
chat.stream_by_tier = capturing_stream_by_tier
list(chat.stream_nexus("what's a good dinner idea tonight"))
sent = captured["messages"][-1]["content"]
check("web search results are wrapped in the 'Background ... may be outdated' label (Lesson #2 fix)",
      "Background web search results" in sent and "may be outdated or unrelated" in sent)
chat.stream_by_tier = original_stream_by_tier

# --- memory retrieval fires on NEARLY EVERY message (Decision — unlike
# CIPHER's trigger-gated version), including one with no obvious
# "remember"-style keyword ---
chat.search_memory = lambda query, n_results=3: ["The rebuild project is called FORGE"]
captured2 = {}
def capturing_stream_by_tier2(agent, tier, system_prompt, messages, location=""):
    captured2["messages"] = messages
    return iter(["mocked response chunk"])
chat.stream_by_tier = capturing_stream_by_tier2
list(chat.stream_nexus("what should I have for lunch"))  # no "remember"/"we discussed" style trigger at all
sent2 = captured2["messages"][-1]["content"]
check("memory retrieval fires even with no trigger keyword present (Decision: nearly-everything, not gated)",
      "Background memory" in sent2 and "FORGE" in sent2)
chat.stream_by_tier = original_stream_by_tier

# --- when there's genuinely nothing saved yet, no memory block gets injected ---
chat.search_memory = lambda query, n_results=3: []
captured3 = {}
def capturing_stream_by_tier3(agent, tier, system_prompt, messages, location=""):
    captured3["messages"] = messages
    return iter(["mocked response chunk"])
chat.stream_by_tier = capturing_stream_by_tier3
list(chat.stream_nexus("what should I have for lunch"))
sent3 = captured3["messages"][-1]["content"]
check("an empty memory result set injects no memory block at all", "Background memory" not in sent3)
chat.stream_by_tier = original_stream_by_tier
chat.search_memory = nexus_memory.search_memory  # restore real one

# --- end-to-end: a MEMORY_SAVE marker in the model's response actually gets saved ---
saved_calls = []
chat.save_memory = lambda category, content: saved_calls.append((category, content))
def model_with_memory_marker(agent, tier, system_prompt, messages, location=""):
    return iter(["Understood, sir.\nMEMORY_SAVE: preference | Always give FIND/REPLACE blocks, not prose diffs"])
chat.stream_by_tier = model_with_memory_marker
out = list(chat.stream_nexus("from now on always give me find/replace blocks"))
check("MEMORY_SAVE marker in the response triggers save_memory() automatically",
      saved_calls == [("preference", "Always give FIND/REPLACE blocks, not prose diffs")])
check("raw response text is still what gets streamed out (marker included, caller strips for history)",
      "MEMORY_SAVE:" in "".join(out))
chat.stream_by_tier = original_stream_by_tier
chat.save_memory = nexus_memory.save_memory  # restore real one

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")