"""
NEXUS "search already done" note - L1 (static) + L2 (mocked) + L4 (sustained / concurrent) + L5 (extreme).
Why it exists: NEXUS's prompt says "YOU MUST write a SEARCH_WEB line when Joey asks for a search", but FORGE already
searches on every message. Gemini 3.6 followed the prompt literally and answered with a SEARCH_WEB line instead of
the weather. The fix is a plain system note telling the model the search is done. Real-model check: see
shared/test_gemini_agents_l3.py.
Run with:  python -m agents.nexus.test_nexus_search_note      (from the forge folder)
"""
import os, sys, tempfile, threading
sys.path.insert(0, os.path.abspath("."))
os.environ["FORGE_DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="forge_nexus_note_"), "chat_history.db")

passed = failed = 0
def check(name, cond, detail=""):
    global passed, failed
    if cond: passed += 1
    else:
        failed += 1
        print(f"FAIL: {name}" + (f"  -> {detail}" if detail else ""))

import agents.nexus.chat as chat

SRC = open("agents/nexus/chat.py", encoding="utf-8").read()
NOTE = chat.SEARCH_DONE_NOTE

# ---------------- L1 static
check("L1 the note tells the model not to write SEARCH_WEB and to answer from the results", "Do NOT write a SEARCH_WEB line" in NOTE and "results" in NOTE)
check("L1 NEXUS's own prompt is unchanged (it still carries the SEARCH_WEB rule - the fix is a note, not a prompt edit)", "SEARCH_WEB: search query" in chat.NEXUS_PROMPT)
check("L1 the note is added in exactly one place, and only after the CIPHER branch", SRC.count("instruction_lines.append(SEARCH_DONE_NOTE)") == 1 and SRC.index("elif not search_result.startswith(WEB_SEARCH_FAILED_PREFIX):") > SRC.index("if routed_to_cipher:"))

# ---------------- fakes
sent = []                    # every list of messages sent to the model
search_mode = {"fail": False}
def fake_stream_by_tier(agent, tier, system_prompt, messages, location=""):
    sent.append(messages)
    return iter(["Very good, sir."])
chat.stream_by_tier = fake_stream_by_tier
chat.web_search = lambda q, num_results=3: (chat.WEB_SEARCH_FAILED_PREFIX + " no connection") if search_mode["fail"] else f"Web search results:\n\n1. Fake result for {q}"
chat.search_memory = lambda m: []
chat.save_memory = lambda c, t: None
chat.stream_cipher = lambda task: iter(["cipher answer"])

def run(message, history=None, location=""):
    sent.clear()
    out = "".join(chat.stream_nexus(message, history=history, location=location))
    return out, sent[-1]

# ---------------- L2
out, msgs = run("What's the weather looking like?", location="South Bend, Indiana")
last = msgs[-1]["content"]
check("L2 normal message: the model's answer is passed through untouched", out == "Very good, sir.")
check("L2 the search results are still in the message, labelled as background", "Background web search results" in last and "Fake result for" in last)
check("L2 the note is there exactly once, AFTER 'Joey says:' and after the search block", last.count(NOTE) == 1 and last.index("Joey says: What's the weather") < last.index(NOTE) and last.index("Background web search results") < last.index("Joey says:"))
check("L2 the note is the last thing the model reads", last.rstrip().endswith(NOTE))

search_mode["fail"] = True
out, msgs = run("What's the weather looking like?", location="South Bend, Indiana")
last = msgs[-1]["content"]
check("L2 search FAILED: no 'already searched' note (that would be a lie), and the failure text is passed on", NOTE not in last and chat.WEB_SEARCH_FAILED_PREFIX in last)
search_mode["fail"] = False

out, msgs = run("write me a script to rename my files")
last = msgs[-1]["content"]
check("L2 a message routed to CIPHER gets the CIPHER note and NOT the search note", "routed to CIPHER" in last and NOTE not in last and "cipher answer" in out, last[-200:])

hist = [{"role": "user", "content": "My dog is Biscuit."}, {"role": "assistant", "content": "Noted, sir."}]
out, msgs = run("What's my dog's name?", history=hist)
check("L2 history is kept as it was, and only the LAST message carries the note", msgs[:2] == hist and all(NOTE not in m["content"] for m in msgs[:2]) and msgs[-1]["content"].count(NOTE) == 1 and len(msgs) == 3)

chat.search_memory = lambda m: ["Joey's dog is Biscuit."]
out, msgs = run("What's my dog's name?")
last = msgs[-1]["content"]
check("L2 with a memory block too: both background blocks come first, then 'Joey says:', then the note", last.index("Background memory") < last.index("Joey says:") < last.index(NOTE) and last.count(NOTE) == 1)
chat.search_memory = lambda m: []

# ---------------- L4
ok = True
for i in range(100):
    out, msgs = run(f"question number {i}")
    c = msgs[-1]["content"]
    if c.count(NOTE) != 1 or f"Joey says: question number {i}" not in c: ok = False; break
check("L4 100 sequential messages: the note is always there exactly once", ok)

lock = threading.Lock(); bad = []; seen = {}
def fake_concurrent(agent, tier, system_prompt, messages, location=""):
    with lock: seen[messages[-1]["content"].split("Joey says: ")[1].split("\n")[0]] = messages[-1]["content"]
    return iter(["ok"])
chat.stream_by_tier = fake_concurrent
def worker(i):
    try: "".join(chat.stream_nexus(f"concurrent message {i}"))
    except Exception as e: bad.append(repr(e))
ts = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
[t.start() for t in ts]; [t.join() for t in ts]
check("L4 20 simultaneous messages: no errors, each carries its own text and exactly one note", not bad and len(seen) == 20 and all(v.count(NOTE) == 1 and k in v for k, v in seen.items()), str(bad[:2]))
chat.stream_by_tier = fake_stream_by_tier

# ---------------- L5
for name, msg in [("empty message", ""), ("50,000 characters", "x" * 50000), ("unicode and emoji", "héllo 😀 日本語 \u202e"), ("a message that itself contains the word SEARCH_WEB:", "please SEARCH_WEB: cats")]:
    out, msgs = run(msg)
    check(f"L5 {name}: still exactly one note, the message intact", msgs[-1]["content"].count(NOTE) == 1 and f"Joey says: {msg}" in msgs[-1]["content"])

print(f"{passed}/{passed + failed} passed")
sys.exit(1 if failed else 0)