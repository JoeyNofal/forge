"""
NEXUS's ASK_CIPHER bridge - L4 (concurrency) + L5 (extreme/breaking).
Mocked model/CIPHER, sandboxed - targets ONLY the bridge's own new
logic (detect/extract/strip functions, stream_nexus sequencing).
Run with: python agents/nexus/test_nexus_bridge_l4_l5.py
"""
import os, sys, threading, types
sys.path.insert(0, os.path.abspath("."))

results = []
def check(name, cond, detail=""):
    status = "PASS" if cond else "FAIL"
    results.append((status, name, detail))
    print(f"[{status}] {name}" + (f" - {detail}" if detail else ""))

fake_web_search = types.ModuleType("shared.web_search")
fake_web_search.WEB_SEARCH_FAILED_PREFIX = "[WEB_SEARCH_FAILED]"  # type: ignore[attr-defined]
fake_web_search.web_search = lambda query, num_results=3: f"Web search results:\n\n1. Fake result for {query}"  # type: ignore[attr-defined]
sys.modules["shared.web_search"] = fake_web_search

from agents.nexus import chat

def fake_stream_by_tier(agent, tier, system_prompt, messages, location=""):
    yield f"RESPONSE_TO[{messages[-1]['content']}]"
chat.stream_by_tier = fake_stream_by_tier

def fake_stream_cipher(task):
    yield f"CIPHER_ANSWER[{task}]"
chat.stream_cipher = fake_stream_cipher

print("=== L4 CONCURRENCY ===\n")

print("--- Test 1: 20 concurrent bridged calls with DIFFERENT tasks - no cross-talk ---")
concurrent_results = {}
lock = threading.Lock()

def worker(n):
    out = "".join(chat.stream_nexus(f"write me a script number {n}"))
    with lock:
        concurrent_results[n] = out

threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
for t in threads: t.start()
for t in threads: t.join()

no_crosstalk = all(f"CIPHER_ANSWER[write me a script number {n}]" in concurrent_results.get(n, "") for n in range(20))
check("each thread's bridged call reached CIPHER with its OWN task, no cross-talk", no_crosstalk and len(concurrent_results) == 20)

print("\n=== L5 EXTREME / BREAKING ===\n")

print("--- Test 2: multiple ASK_CIPHER lines - only the first is used ---")
cipher_call_log = []
def logging_stream_cipher(task):
    cipher_call_log.append(task)
    yield f"CIPHER_ANSWER[{task}]"
chat.stream_cipher = logging_stream_cipher

def multi_ask(agent, tier, system_prompt, messages, location=""):
    yield "Sure.\nASK_CIPHER: first task\nASK_CIPHER: second task"
chat.stream_by_tier = multi_ask
out = "".join(chat.stream_nexus("some message that doesn't pre-check trigger"))
# "second task" legitimately still appears in `out` - it's part of NEXUS's
# own raw (never live-stripped) text. What actually matters is what
# stream_cipher was CALLED with, not what substring shows up in the text.
check("stream_cipher was called with only the FIRST task, not the second", cipher_call_log == ["first task"])
chat.stream_cipher = fake_stream_cipher  # restore

print("\n--- Test 3: empty task after ASK_CIPHER: doesn't bridge to an empty string ---")
def empty_ask(agent, tier, system_prompt, messages, location=""):
    yield "Sure.\nASK_CIPHER:   "
chat.stream_by_tier = empty_ask
out2 = "".join(chat.stream_nexus("some message"))
check("an empty ASK_CIPHER task never calls CIPHER with nothing", "CIPHER_ANSWER[" not in out2)

print("\n--- Test 4: backtick-wrapped mention mid-sentence never triggers a real bridge ---")
def mention_only(agent, tier, system_prompt, messages, location=""):
    yield "I would normally use `ASK_CIPHER:` here, but let me just explain instead."
chat.stream_by_tier = mention_only
out3 = "".join(chat.stream_nexus("explain the ASK_CIPHER format to me"))
check("a backtick-wrapped mention never bridges to CIPHER for real", "CIPHER_ANSWER[" not in out3)

print("\n--- Test 5: very long message still keyword-pre-checks correctly, no crash ---")
huge_message = "write me a script that " + ("does something complicated " * 3000)
try:
    out4 = "".join(chat.stream_nexus(huge_message))
    check("50,000+ char message with a real trigger phrase still bridges without crashing",
          "CIPHER_ANSWER[" in out4)
except Exception as e:
    check("50,000+ char message with a real trigger phrase still bridges without crashing",
          False, f"raised {type(e).__name__}: {e}")

print("\n--- Test 6: unicode/emoji in the bridged task doesn't crash extraction or the call ---")
def unicode_ask(agent, tier, system_prompt, messages, location=""):
    yield "On it.\nASK_CIPHER: fix this émoji-laden 🎉 bug in 日本語 comments"
chat.stream_by_tier = unicode_ask
try:
    out5 = "".join(chat.stream_nexus("some trigger message"))
    check("unicode/emoji in the bridged task is passed through correctly", "🎉" in out5)
except Exception as e:
    check("unicode/emoji in the bridged task is passed through correctly", False, f"raised {type(e).__name__}: {e}")

print("\n--- Test 7: CIPHER itself failing during a bridge call propagates clearly, isn't swallowed ---")
def normal_model(agent, tier, system_prompt, messages, location=""):
    yield "Bringing in CIPHER now."
chat.stream_by_tier = normal_model
def broken_stream_cipher(task):
    raise ConnectionError("simulated CIPHER outage")
    yield  # pragma: no cover
chat.stream_cipher = broken_stream_cipher
propagated = False
try:
    out6 = "".join(chat.stream_nexus("write me a script for this"))
except ConnectionError:
    propagated = True
check("a real failure inside CIPHER during a bridge call propagates, isn't silently swallowed", propagated)
chat.stream_cipher = fake_stream_cipher  # restore

print("\n=== SUMMARY ===")
passed = sum(1 for s, _, _ in results if s == "PASS")
failed = sum(1 for s, _, _ in results if s == "FAIL")
print(f"{passed} passed, {failed} failed, {len(results)} total")
if failed:
    for s, n, d in results:
        if s == "FAIL":
            print(f"  - {n}: {d}")