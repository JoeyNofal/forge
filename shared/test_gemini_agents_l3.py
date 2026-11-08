"""
FORGE agents on the free Gemini tier - L3 (REAL Google + SerpApi calls: about 6 Gemini requests and 3 searches).
Run with:  python -m shared.test_gemini_agents_l3      (from D:\\Projects\\Forge)
Checks the two things that changed with the new Gemini models:
  - NEXUS answers a search-type question from the results FORGE already fetched (it must not write a SEARCH_WEB line)
  - CIPHER works on the free tier (its own default is the paid tier, so this forces free_cloud)
Memory is pointed at throwaway folders for this run, so nothing is saved to your real agent memory.
Read the printed replies: the PASS/FAIL lines are mechanical only.
"""
import os, re, sys, tempfile, time
sys.path.insert(0, os.path.abspath("."))
_tmp = tempfile.mkdtemp(prefix="forge_gem_agents_")
os.environ["CIPHER_MEMORY_PATH"] = os.path.join(_tmp, "cipher_memory")   # BEFORE the agents are imported
os.environ["NEXUS_MEMORY_PATH"] = os.path.join(_tmp, "nexus_memory")
os.environ["FORGE_DB_PATH"] = os.path.join(_tmp, "chat_history.db")

from shared import model_client as mc
from agents.cipher import chat as cipher_chat
from agents.nexus import chat as nexus_chat

print(f"settings: GEMINI_MODEL={mc.GEMINI_MODEL}  fallback={mc.GEMINI_FALLBACK_MODEL!r}  thinking={mc.GEMINI_THINKING_LEVEL}")
results = []
def check(name, cond):
    results.append(bool(cond)); print(("   PASS  " if cond else "   FAIL  ") + name)

def run(label, make_stream):
    print("\n" + "=" * 70 + "\n" + label + "\n" + "=" * 70)
    try:
        t0 = time.time(); out = "".join(make_stream()); dt = time.time() - t0
    except Exception as e:
        print("ERROR:", type(e).__name__, str(e)[:500]); check("it answered without an error", False); return ""
    print(f"(model: {mc.LAST_GEMINI_MODEL}, {dt:.1f}s)\n{out.strip()}\n")
    time.sleep(3)
    return out

out = run("NEXUS - weather (this was the broken case)", lambda: nexus_chat.stream_nexus("What's the weather looking like?", location="South Bend, Indiana", model_tier="free_cloud"))
check("NEXUS did not answer with a SEARCH_WEB line", "SEARCH_WEB" not in out)
check("NEXUS gave a real answer with at least one number in it (a temperature or a time)", bool(re.search(r"\d", out)))
check("NEXUS did not ask for permission to look it up ('allow me to check', 'one moment')", not re.search(r"allow me to check|one moment|let me check", out, re.I))

out = run("NEXUS - an ordinary message", lambda: nexus_chat.stream_nexus("I've had a long day, any tips for winding down tonight?", location="South Bend, Indiana", model_tier="free_cloud"))
check("NEXUS answered and wrote no tool line", len(out.strip()) > 80 and not re.search(r"^(SEARCH_WEB|ASK_[A-Z]+|SET_REMINDER|OPEN_APP):", out, re.M))

out = run("CIPHER - free tier, a small coding task", lambda: cipher_chat.stream_cipher("write a one-line python function to subtract two numbers", model_tier="free_cloud"))
check("CIPHER wrote a function", "def " in out or "lambda" in out)

hist = [{"role": "user", "content": "write a one-line python function named add that adds two numbers"},
        {"role": "assistant", "content": "def add(a, b): return a + b"}]
out = run("CIPHER - free tier, a follow-up that needs the earlier turn", lambda: cipher_chat.stream_cipher("now rename that function to total", history=hist, model_tier="free_cloud"))
check("CIPHER used the earlier turn (the new name is there, the code is for the same function)", "total" in out and ("a + b" in out or "a+b" in out))

print(f"\n{sum(results)}/{len(results)} mechanical checks passed (READ the replies above)")
sys.exit(0 if all(results) else 1)