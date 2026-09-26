"""
NEXUS memory increment - L3 (real end-to-end).
Needs: real GEMINI_API_KEY in .env, Ollama running locally with
nomic-embed-text already pulled. No mocks anywhere in this file.
Run with: python agents/nexus/test_nexus_memory_l3.py
"""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath("."))

# Real ChromaDB + real Ollama embeddings, but still a throwaway temp
# dir - L3 should prove the real pipeline works, not pollute
# D:\Projects\forge\memory\nexus with test data.
os.environ["NEXUS_MEMORY_PATH"] = tempfile.mkdtemp(prefix="nexus_memory_l3_")

from dotenv import load_dotenv
load_dotenv(override=True)

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

from agents.nexus import chat
from shared import nexus_memory

print("=== L3 REAL END-TO-END ===\n")

# --- 1. Real save + real semantic search (no fake embeddings this time) ---
print("--- Test 1: real Ollama embeddings actually distinguish topics ---")
ok1 = nexus_memory.save_memory("decision", "The rebuild project is officially called FORGE")
ok2 = nexus_memory.save_memory("project_fact", "The old NEXUS SYSTEM keeps running day-to-day during the rebuild")
check("both real saves succeeded", ok1 and ok2)

found = nexus_memory.search_memory("what is the rebuild project actually called")
print(f"  search_memory returned: {found}")
check("top result is the FORGE decision, not the unrelated fact",
      bool(found) and "FORGE" in found[0])

# --- 2. Real Gemini call, memory retrieval actually used (with NO
# trigger keyword in the message - proving "nearly everything", not
# CIPHER-style gating) ---
print("\n--- Test 2: NEXUS's real response uses retrieved memory correctly, unprompted ---")
out = "".join(chat.stream_nexus("what's this whole rebuild project I've been doing called again?"))
print(f"  NEXUS said: {out}")
check("real response mentions FORGE (proves retrieved memory was used, not hallucinated)",
      "FORGE" in out)

# --- 3. Memory always retrieves in the background, even on an
# unrelated question - must not derail or confuse the real answer ---
print("\n--- Test 3: irrelevant background memory doesn't derail an unrelated answer ---")
out2 = "".join(chat.stream_nexus("what's a good dinner idea for tonight?"))
print(f"  NEXUS said: {out2}")
check("unrelated question still gets a normal, sensible answer despite memory always injecting",
      len(out2) > 0 and "FORGE" not in out2)

# --- 4. Real Gemini decides on its own whether something is memory-worthy ---
print("\n--- Test 4: a real stated preference gets recognized and actually saved ---")
before_count = nexus_memory._get_collection().count()
out3 = "".join(chat.stream_nexus(
    "From now on, always give me your questions as a numbered list, not multiple choice. Got it?"
))
print(f"  NEXUS said: {out3}")
after_count = nexus_memory._get_collection().count()
check("a real MEMORY_SAVE marker resulted in an actual new entry in the collection",
      after_count > before_count, f"before={before_count}, after={after_count}")

# --- 5. NEXUS-specific: a real finance question never gets saved to
# NEXUS's own memory, even if the model tries - financial_fact isn't
# in NEXUS_MEMORY_SAVE_CATEGORIES no matter what the model writes ---
print("\n--- Test 5: a real finance mention never lands in NEXUS's own memory ---")
before_count2 = nexus_memory._get_collection().count()
out4 = "".join(chat.stream_nexus("Just so you know, I have $4,300 in my checking account right now."))
print(f"  NEXUS said: {out4}")
after_count2 = nexus_memory._get_collection().count()
found_balance = nexus_memory.search_memory("checking account balance", n_results=10)
check("no new entry mentioning the dollar figure landed in NEXUS's memory",
      not any("4,300" in item or "4300" in item for item in found_balance),
      f"before={before_count2}, after={after_count2}, found={found_balance}")

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")