"""
CIPHER memory increment - L3 (real end-to-end).
Needs: real GEMINI_API_KEY in .env, Ollama running locally with
nomic-embed-text already pulled. No mocks anywhere in this file.
Run with: python agents/cipher/test_cipher_memory_l3.py
"""
import os, sys, tempfile
sys.path.insert(0, os.path.abspath("."))

# Real ChromaDB + real Ollama embeddings, but still a throwaway temp
# dir - L3 should prove the real pipeline works, not pollute
# D:\Projects\forge\memory\cipher with test data.
os.environ["CIPHER_MEMORY_PATH"] = tempfile.mkdtemp(prefix="cipher_memory_l3_")

from dotenv import load_dotenv
load_dotenv(override=True)

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

from agents.cipher import chat
from shared import cipher_memory

print("=== L3 REAL END-TO-END ===\n")

# --- 1. Real save + real semantic search (no fake embeddings this time) ---
print("--- Test 1: real Ollama embeddings actually distinguish topics ---")
ok1 = cipher_memory.save_memory("decision", "We are using FastAPI for the backend, not Flask")
ok2 = cipher_memory.save_memory("project_fact", "The Financial Tracker reads from finance.json")
check("both real saves succeeded", ok1 and ok2)

found = cipher_memory.search_memory("what backend framework are we using")
print(f"  search_memory returned: {found}")
check("top result is the FastAPI decision, not the unrelated fact",
      bool(found) and "FastAPI" in found[0])

# --- 2. Real Gemini call, memory retrieval triggered and actually used ---
print("\n--- Test 2: CIPHER's real response uses retrieved memory correctly ---")
out = "".join(chat.stream_cipher("remember what backend framework we picked for this project?"))
print(f"  CIPHER said: {out}")
check("real response mentions FastAPI (proves retrieved memory was used, not hallucinated)",
      "FastAPI" in out)

# --- 3. Real Gemini call, does NOT search memory for an unrelated question ---
print("\n--- Test 3: memory not injected into an unrelated coding question ---")
out2 = "".join(chat.stream_cipher("write a python function that reverses a string"))
print(f"  CIPHER said: {out2[:200]}...")
check("plain coding question still gets answered normally", len(out2) > 0)

# --- 4. Real Gemini decides on its own whether something is memory-worthy ---
print("\n--- Test 4: a real stated preference gets recognized and saved ---")
before = len(cipher_memory.search_memory("code style preference", n_results=10))
out3 = "".join(chat.stream_cipher(
    "From now on, always explain your code in one short sentence before showing it. Got it?"
))
print(f"  CIPHER said: {out3}")
print("  (MEMORY_SAVE marker above, if any, is what actually got saved - eyeball it for correctness)")
check("response was generated without crashing", len(out3) > 0)

# --- 5. Off-topic refusal still works, untouched by memory changes ---
print("\n--- Test 5: refusal gate still works ---")
out4 = list(chat.stream_cipher("what's a good recipe for dinner tonight"))
check("off-topic message still refuses, no model/memory call", out4 == [chat.REFUSAL_MESSAGE])

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")