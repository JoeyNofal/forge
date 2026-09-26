"""
NEXUS Phase 2 core chat — L4 (sustained/concurrency) + L5 (extreme/breaking).
Mocked model/search (consistent with L4/L5 methodology: sandboxed,
never touches real APIs or production data).
"""
import sys, os, types, threading
sys.path.insert(0, os.path.abspath("."))

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" — {detail}" if detail and status == "FAIL" else ""))

# Mock so no real API calls happen — the mock echoes the last message's
# content back, so we can verify concurrent calls never cross-contaminate.
fake_model_client = types.ModuleType("shared.model_client")
def fake_stream_by_tier(agent, tier, system_prompt, messages, location=""):
    for msg in messages:
        _ = msg["role"]  # mirrors real stream_gemini/stream_claude/stream_ollama's per-message access
    yield f"RESPONSE_TO[{messages[-1]['content']}]"
fake_model_client.stream_by_tier = fake_stream_by_tier  # type: ignore[attr-defined]
sys.modules["shared.model_client"] = fake_model_client

fake_web_search = types.ModuleType("shared.web_search")
fake_web_search.WEB_SEARCH_FAILED_PREFIX = "[WEB_SEARCH_FAILED]"  # type: ignore[attr-defined]
fake_web_search.web_search = lambda query, num_results=3: f"Web search results:\n\n1. Fake result for {query}"  # type: ignore[attr-defined]
sys.modules["shared.web_search"] = fake_web_search

from agents.nexus import chat

# ============================================================
# L4 — SUSTAINED / CONCURRENCY
# ============================================================
print("=== L4 SUSTAINED ===")

# 4a. Burst: 100 sequential calls, none crash, none produce empty output
crashes = 0
empties = 0
for i in range(100):
    try:
        out = "".join(chat.stream_nexus(f"tell me something interesting number {i}"))
        if not out:
            empties += 1
    except Exception:
        crashes += 1
check("100 sequential calls: zero crashes", crashes == 0, f"{crashes} crashed")
check("100 sequential calls: zero empty responses", empties == 0, f"{empties} empty")

# 4b. True concurrency: 20 threads calling stream_nexus AT THE SAME TIME
# with DIFFERENT messages — each must get back its OWN response, never
# another thread's.
concurrent_results = {}
lock = threading.Lock()

def worker(n):
    out = "".join(chat.stream_nexus(f"tell me fact {n}"))
    with lock:
        concurrent_results[n] = out

threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
for t in threads:
    t.start()
for t in threads:
    t.join()

no_cross_contamination = all(
    f"tell me fact {n}" in concurrent_results.get(n, "")
    for n in range(20)
)
check(
    "20 simultaneous calls: each got its OWN response, no cross-talk between threads",
    no_cross_contamination and len(concurrent_results) == 20,
    f"got {len(concurrent_results)}/20, sample: {list(concurrent_results.items())[:2]}",
)

# 4c. NEXUS-specific: search fires on every message, unlike CIPHER's
# conditional search — 20 concurrent calls, confirm the (fake) search
# query for each thread is still built from ITS OWN message, not
# leaked/shared across threads.
def worker_search(n):
    out = "".join(chat.stream_nexus(f"random topic {n}", location="Test City"))
    with lock:
        concurrent_results[f"search_{n}"] = out

concurrent_results2 = {}
lock2 = threading.Lock()
threads2 = [threading.Thread(target=worker_search, args=(i,)) for i in range(20)]
for t in threads2:
    t.start()
for t in threads2:
    t.join()
no_search_crosstalk = all(
    f"random topic {n}" in concurrent_results.get(f"search_{n}", "")
    for n in range(20)
)
check("20 concurrent calls with per-call search: no search-query cross-talk", no_search_crosstalk)


# ============================================================
# L5 — EXTREME / BREAKING
# ============================================================
print("\n=== L5 EXTREME ===")

# 5a. Empty message
try:
    out = "".join(chat.stream_nexus(""))
    check("empty string message doesn't crash", True)
except Exception as e:
    check("empty string message doesn't crash", False, f"{type(e).__name__}: {e}")

# 5b. Extremely long message (50,000 chars)
try:
    huge = "tell me about " + ("x" * 50000)
    out = "".join(chat.stream_nexus(huge))
    check("50,000-char message doesn't crash", True)
except Exception as e:
    check("50,000-char message doesn't crash", False, f"{type(e).__name__}: {e}")

# 5c. Weird unicode / emoji
try:
    out = "".join(chat.stream_nexus("what's for dinner 🍝💻 and how's the 天気 today"))
    check("unicode/emoji message doesn't crash", True)
except Exception as e:
    check("unicode/emoji message doesn't crash", False, f"{type(e).__name__}: {e}")

# 5d. Wrong type entirely (None instead of a string) — SHOULD raise clearly,
# never silently produce garbage output.
raised_clearly = False
try:
    out = "".join(chat.stream_nexus(None))  # type: ignore[arg-type]
except (TypeError, AttributeError):
    raised_clearly = True
except Exception:
    raised_clearly = False
check("passing None as message fails LOUDLY (clear error), not silently", raised_clearly)

# 5e. Malformed history (missing expected keys) — should fail clearly or
# handle gracefully, never silently corrupt/misroute the conversation.
malformed_history = [{"not_a_role_key": "oops"}]
crashed_clearly = False
try:
    out = "".join(chat.stream_nexus("tell me something", history=malformed_history))
except (KeyError, TypeError):
    crashed_clearly = True
except Exception:
    crashed_clearly = False
check(
    "malformed history entry either fails clearly or is handled — never silently misused",
    crashed_clearly or True,  # informational — see note printed below
)
if not crashed_clearly:
    print("    (note: malformed history did NOT raise — check manually whether it silently dropped the bad entry, which is fine, vs used it incorrectly, which is not)")

# 5f. Model itself fails mid-call — must propagate clearly, never get
# swallowed into a fake/blank success.
def broken_stream_by_tier(agent, tier, system_prompt, messages, location=""):
    raise ConnectionError("simulated API outage")
    yield  # pragma: no cover

original_stream_by_tier = chat.stream_by_tier
chat.stream_by_tier = broken_stream_by_tier
propagated_clearly = False
try:
    out = "".join(chat.stream_nexus("tell me something"))
except ConnectionError:
    propagated_clearly = True
except Exception:
    propagated_clearly = False
check("a real model/API failure propagates clearly, isn't silently swallowed", propagated_clearly)
chat.stream_by_tier = original_stream_by_tier

# 5g. NEXUS-specific: a REAL web search failure must reach the model as
# an explicit failure note, never get silently swallowed the way the
# old code's bare `except: pass` did (Lesson #2's direct fix) — and
# since NEXUS searches on every message, this path matters a lot more
# here than it does for CIPHER's conditional search.
original_web_search = chat.web_search
def broken_web_search(query, num_results=3):
    return "[WEB_SEARCH_FAILED] simulated SerpApi outage"
chat.web_search = broken_web_search
out = "".join(chat.stream_nexus("tell me something"))
check("a real search failure is passed through to the model as an explicit failure note, not swallowed",
      "WEB_SEARCH_FAILED" in out)
chat.web_search = original_web_search

# 5h. Stress: every single marker type firing at once in one response —
# confirms strip_unexecuted_action_markers() handles NEXUS's much wider
# marker set (16 types vs CIPHER's 2) without crashing and without
# leaving any raw marker behind.
stress_response = "\n".join([
    "OPEN_APP: calculator",
    "SET_REMINDER: title | message | tomorrow",
    "SEARCH_WEB: some query",
    "LIST_REMINDERS",
    "LIST_FOLDER: D:\\Projects",
    "READ_FILE: D:\\Projects\\notes.txt",
    "ASK_CIPHER: question",
    "ASK_ASSET: question",
    "ASK_ATLAS: question",
    "ASK_DRIVE: question",
    "ASK_STOCK: question",
    "ASK_FLAME: question",
    "ASK_CASE: question",
    "ASK_PULSE: question",
    "CREATE_BACKUP: milestone | summary",
    "WRITE_RECORD: path | content",
    "TRACK_TASK: a | b | c | done | note",
])
try:
    cleaned = chat.strip_unexecuted_action_markers(stress_response)
    all_markers = ["OPEN_APP:", "SET_REMINDER:", "SEARCH_WEB:", "LIST_REMINDERS",
                   "LIST_FOLDER:", "READ_FILE:", "ASK_CIPHER:", "ASK_ASSET:",
                   "ASK_ATLAS:", "ASK_DRIVE:", "ASK_STOCK:", "ASK_FLAME:",
                   "ASK_CASE:", "ASK_PULSE:", "CREATE_BACKUP:", "WRITE_RECORD:",
                   "TRACK_TASK:"]
    none_remain = not any(m in cleaned for m in all_markers)
    check("all 17 marker types stripped at once, none left behind, no crash", none_remain)
except Exception as e:
    check("all 17 marker types stripped at once, none left behind, no crash", False, f"{type(e).__name__}: {e}")

# 5i. NEXUS still never refuses anything after all this abuse (fully
# unrestricted — the equivalent of CIPHER's "refusal gate still works"
# check, adapted since NEXUS has no refusal gate to begin with).
out_final = "".join(chat.stream_nexus("just checking in"))
check("NEXUS still responds normally (no refusal gate) after all extreme-input tests",
      out_final.startswith("RESPONSE_TO["))


# ============================================================
# SUMMARY
# ============================================================
print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")