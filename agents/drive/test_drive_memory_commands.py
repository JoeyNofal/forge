"""
DRIVE (c) Part 3 — L1, L2, L4, L5 tests for "what do you remember?" and "forget ...": detection, the list, forgetting
by meaning / id / "that" / everything, the approval gate, and the chat.py wiring. The EMBEDDINGS and DRIVE's reply
are FAKED. TEMP folders only: your real memory, vehicle file and approval queue are never touched.

Run from the repo root:  python -m agents.drive.test_drive_memory_commands
"""
import hashlib
import json
import math
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from typing import Any

os.environ["DRIVE_MEMORY_PATH"] = tempfile.mkdtemp(prefix="drive_cmd_import_")
_QUEUE_DIR = tempfile.mkdtemp(prefix="drive_cmd_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from chromadb import Documents, EmbeddingFunction, Embeddings

from agents.drive import chat
from agents.drive import drive_actions as A
from agents.drive import drive_memory_commands as C
from shared import agent_topics
from shared import drive_memory as dm
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
_results = []
_lock = threading.Lock()
reply_calls = []
model_calls = []
today = datetime.now().strftime("%Y-%m-%d")


def check(name):
    def deco(fn):
        try:
            fn()
            _results.append((name, True, ""))
            print(f"PASS  {name}")
        except Exception as e:
            _results.append((name, False, repr(e)))
            print(f"FAIL  {name}  -> {e!r}")
        return fn
    return deco


class FakeEmbed(EmbeddingFunction):
    """Word-overlap embeddings (see shared/test_drive_memory.py)."""

    def __call__(self, input: Documents) -> Embeddings:
        out = []
        for text in input:
            vec = [0.0] * 1024
            for word in re.findall(r"[a-z0-9]+", text.lower()) or ["emptytext"]:
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % 1024] += 1.0
            norm = math.sqrt(sum(x * x for x in vec))
            out.append([x / norm for x in vec])
        return out  # type: ignore[return-value]


def fake_local(system_prompt, user_text, timeout=90.0):
    with _lock:
        model_calls.append(user_text)
    return '{"kind": "none"}'


def fake_reply(agent, tier, system_prompt, messages, location=""):
    with _lock:
        reply_calls.append(list(messages))
    yield "Now. "
    yield "Listen carefully."


chat.stream_by_tier = fake_reply
chat.web_search = lambda q, num_results=3: "Web search results:\n\n1. x"
chat.prepare_recall_context = lambda message: (None, None)
chat.extract_and_propose = lambda message: []
chat.remember_from_message = lambda message: []
chat.memory_context_block = lambda message: None


def fresh():
    dm.DRIVE_MEMORY_PATH = tempfile.mkdtemp(prefix="drive_cmd_case_")
    dm._client = None
    dm._collection = None
    dm._embedding_function_factory = FakeEmbed
    d = tempfile.mkdtemp(prefix="drive_cmd_vehicle_")
    os.environ["VEHICLE_DATA_PATH"] = os.path.join(d, "vehicle.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    reply_calls.clear()
    model_calls.clear()


def save(category, text):
    r = dm.save_memory(category, text)
    assert r["status"] == "saved", r
    return r["id"]


def run(message):
    return C.handle_memory_command(C.detect_memory_command(message))


def say(message):
    return "".join(chat.stream_drive(message))


def queue_actions():
    p = QUEUE
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)["actions"]


def status_of(action_id):
    a = pa.get_pending_action(action_id)
    return a["status"] if a else "missing"


def put_queue(*entries):
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    with open(QUEUE, "w", encoding="utf-8") as f:
        json.dump({"actions": list(entries)}, f)


def raises(fn, exc: type[BaseException] = Exception):
    try:
        fn()
    except exc:
        return True
    return False


F1 = "I always use full synthetic 0W-20 oil"
F2 = "I am planning a road trip to Colorado in November"
F3 = "The left rear window sticks"

with open(C.__file__, encoding="utf-8") as _f:
    CSRC = _f.read()
with open(A.__file__, encoding="utf-8") as _f:
    ASRC = _f.read()
with open(chat.__file__, encoding="utf-8") as _f:
    CHATSRC = _f.read()


def _function_source(src, name):
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", src, re.S | re.M)
    assert m, name
    return m.group(0)


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 the command module never deletes or saves anything itself and never calls a model: deleting happens ONLY in an approved action")
def _():
    for banned in ("delete_memory", "delete_memories", "save_memory", "complete_ollama_json", "stream_by_tier",
                   "approve_and_execute", "json.dump"):
        assert banned not in CSRC, banned
    assert "drive_actions.propose_forget_memory" in CSRC and "drive_actions.propose_forget_all_memories" in CSRC
    assert not re.search(r"except\s*:", CSRC) and not re.search(r"\bopen\(", CSRC)


@check("L1 only approve_and_execute deletes memories; proposing never does")
def _():
    callers = [fn for fn in re.findall(r"^def (\w+)\(", ASRC, re.M) if "drive_memory.delete" in _function_source(ASRC, fn)]
    assert callers == ["approve_and_execute"], callers
    for fn in ("propose_forget_memory", "propose_forget_all_memories"):
        assert "drive_memory.delete" not in _function_source(ASRC, fn), fn


@check("L1 chat handles memory commands FIRST (before the topic refusal) and still never touches writers")
def _():
    assert CHATSRC.index("detect_memory_command(message)") < CHATSRC.index("should_refuse(message")
    for banned in ("drive_logging", "drive_actions", "approve_and_execute", "update_json", "delete_memor"):
        assert banned not in CHATSRC, banned


@check("L1 the list phrases live in shared/agent_topics, and the thresholds are sane")
def _():
    assert "what do you remember" in agent_topics.DRIVE_MEMORY_LIST_PHRASES
    assert dm.DEFAULT_MAX_DISTANCE <= C.FORGET_MAX_DISTANCE <= 0.7 and 0 < C.AMBIGUITY_MARGIN < 0.2


@check("L1 the no-invention rule is in DRIVE's context note")
def _():
    assert "Never invent what other people said" in chat.LOGGING_NOTE and "forum posts" in chat.LOGGING_NOTE


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 detection: list and forget forms are recognized; everyday phrases ('forget it', 'I forgot', 'don't forget') are NOT commands")
def _():
    yes = [
        ("what do you remember?", {"kind": "list"}), ("What do you know about me", {"kind": "list"}),
        ("what have I told you", {"kind": "list"}), ("show me your memory", {"kind": "list"}),
        ("list your memories", {"kind": "list"}),
        ("forget the Colorado trip", {"kind": "forget", "target": "the Colorado trip"}),
        ("forget that I always use 0W-20", {"kind": "forget", "target": "I always use 0W-20"}),
        ("please forget my dealer", {"kind": "forget", "target": "my dealer"}),
        ("Forget about the window!", {"kind": "forget", "target": "the window"}),
        ("can you please forget the window", {"kind": "forget", "target": "the window"}),
        ("forget that", {"kind": "forget_last"}), ("forget this one.", {"kind": "forget_last"}),
        ("forget the last thing", {"kind": "forget_last"}),
        ("forget a1b2c3", {"kind": "forget", "target": "a1b2c3"}),
        ("forget everything", {"kind": "forget_all"}), ("forget all of it", {"kind": "forget_all"}),
        ("forget everything you know about me", {"kind": "forget_all"}), ("wipe your memory", {"kind": "forget_all"}),
        ("clear all your memories", {"kind": "forget_all"}), ("delete your memory", {"kind": "forget_all"}),
    ]
    for message, want in yes:
        assert C.detect_memory_command(message) == want, (message, C.detect_memory_command(message))
    for message in ("forget it", "forget about it", "Forget it, I'll do it later", "I forgot to check my oil",
                    "don't forget to rotate my tires", "what do you think about my oil", "should I forget synthetic?",
                    "forget", "forget   ", "", "   ", "hello", "clear the check engine code", "delete the file",
                    None, 5, [], {}):
        assert C.detect_memory_command(message) is None, message


@check("L2 'what do you remember?': numbered, newest first, category/date/short id, how to remove; an empty memory says how to teach it")
def _():
    fresh()
    ids = []
    for cat, text in (("preference", F1), ("plan", F2), ("project_fact", F3)):
        ids.append(save(cat, text))
        time.sleep(0.01)
    out = run("what do you remember?")
    assert out.startswith("Here's what I remember (3):") and out.index(F3) < out.index(F2) < out.index(F1)
    assert f"1. {F3} [project_fact, {today}, id {ids[2][:6]}]" in out and f"3. {F1} [preference, {today}, id {ids[0][:6]}]" in out
    assert 'say "forget"' in out and "forget everything" in out
    fresh()
    assert "haven't been told anything to remember yet" in run("what do you remember?")


@check("L2 more than 20 memories: the first 20 are shown, then 'and N more'")
def _():
    fresh()
    for n in range(25):
        save("project_fact", f"unique statement {n} about subject{n}")
    out = run("what do you remember?")
    assert out.count("\n") >= 21 and "...and 5 more." in out and "20. " in out and "21. " not in out


@check("L2 forget BY MEANING: finds the one matching memory, proposes it with its full text, deletes NOTHING until approved; approval deletes exactly that one")
def _():
    fresh()
    save("preference", F1)
    trip = save("plan", F2)
    out = run("forget the road trip to Colorado")
    assert out.startswith(f'Proposed: forget this memory: "{F2}" (plan, saved {today})') and "Nothing is deleted until you approve" in out
    q = queue_actions()
    assert len(q) == 1 and q[0]["type"] == "forget_memory" and q[0]["status"] == "pending" and q[0]["details"]["memory_id"] == trip
    assert dm.memory_count() == 2
    assert A.approve_and_execute(q[0]["id"]) == f'Forgotten: "{F2}"'
    assert [m["text"] for m in dm.list_memories()] == [F1] and status_of(q[0]["id"]) == "executed"


@check("L2 forget BY ID: a unique short id works (any case); an ambiguous one lists the candidates and asks; an unknown one falls back to a search")
def _():
    fresh()
    a = save("preference", F1)
    save("plan", F2)
    short = a[:6]
    assert f'"{F1}"' in run(f"forget {short}") and f'"{F1}"' in run(f"FORGET {short.upper()}")
    metas: Any = [{"category": "preference", "saved_at": "2026-01-01T00:00:00"}] * 2
    dm._get_collection().add(documents=["x one", "x two"], ids=["abcdef-1", "abcdef-2"], metadatas=metas)
    before = len(queue_actions())
    out = run("forget abcdef")
    assert "more than one memory" in out and "abcdef" in out and "x one" in out and "x two" in out and len(queue_actions()) == before
    assert "couldn't find a memory matching" in run("forget deadbeef")


@check("L2 'forget that' proposes the NEWEST memory; with no memories there is nothing to forget")
def _():
    fresh()
    assert "nothing to forget" in run("forget that")
    save("preference", F1)
    time.sleep(0.01)
    save("plan", F2)
    out = run("forget that")
    assert f'"{F2}"' in out and f'"{F1}"' not in out


@check("L2 'forget everything' / 'wipe your memory': one proposal naming the count; approval deletes EXACTLY those, a memory saved afterwards survives; twice does nothing")
def _():
    fresh()
    for cat, text in (("preference", F1), ("plan", F2), ("project_fact", F3)):
        save(cat, text)
    out = run("forget everything")
    assert out.startswith("Proposed: forget ALL 3 memories DRIVE has saved about you") and "Nothing is deleted until you approve" in out
    aid = queue_actions()[0]["id"]
    assert dm.memory_count() == 3
    save("goal", "My goal is reaching 200k miles")
    assert A.approve_and_execute(aid) == "Forgot 3 memories." and [m["text"] for m in dm.list_memories()] == ["My goal is reaching 200k miles"]
    assert "already executed" in A.approve_and_execute(aid)
    assert "forget ALL 1 memories" in run("wipe your memory")


@check("L2 nothing matches: Joey is told, pointed to 'what do you remember?', and reminded logged data lives in the vehicle file; nothing is queued")
def _():
    fresh()
    save("preference", F1)
    out = run("forget the turbo wastegate")
    assert "couldn't find a memory matching" in out and "what do you remember?" in out
    assert "vehicle file" in out and "DRIVE Tracker" in out and queue_actions() == [] and dm.memory_count() == 1


@check("L2 two memories equally close: DRIVE lists both and asks, never guesses; nothing is queued")
def _():
    fresh()
    save("preference", "Joey likes red floor mats")
    save("preference", "Joey likes blue floor mats")
    out = run("forget floor mats")
    assert "more than one memory" in out and "red floor mats" in out and "blue floor mats" in out
    assert queue_actions() == [] and dm.memory_count() == 2


@check("L2 approval edge cases: already gone -> fails cleanly and touches nothing else; deny deletes nothing and can't be approved later; the waiting proposal is listed")
def _():
    fresh()
    keep = save("preference", F1)
    gone = save("plan", F2)
    run("forget the road trip to Colorado")
    aid = queue_actions()[0]["id"]
    assert "forget this memory" in A.list_pending()
    assert dm.delete_memory(gone) is True
    out = A.approve_and_execute(aid)
    assert out == "That memory is already gone, so nothing was deleted." and status_of(aid) == "failed"
    assert [m["id"] for m in dm.list_memories()] == [keep]
    run("forget that")
    aid2 = queue_actions()[-1]["id"]
    assert A.deny_action(aid2).startswith("Denied: forget this memory") and "already denied" in A.approve_and_execute(aid2)
    assert dm.memory_count() == 1


@check("L2 hand-damaged forget actions in the queue fail cleanly ('Execution failed') and delete nothing")
def _():
    fresh()
    save("preference", F1)
    base = {"agent": "drive", "status": "pending", "result": None, "created_at": "x", "resolved_at": None}
    put_queue(dict(base, id="bad-1", type="forget_memory", details={}),
              dict(base, id="bad-2", type="forget_all_memories", details="x"),
              dict(base, id="bad-3", type="forget_memory", details=None))
    for aid in ("bad-1", "bad-2", "bad-3"):
        assert A.approve_and_execute(aid).startswith("Execution failed"), aid
    assert dm.memory_count() == 1 and all(a["status"] == "failed" for a in queue_actions())


@check("L2 if the embeddings are down, forgetting by description says so and points to ids; forgetting by id still works")
def _():
    fresh()
    a = save("preference", F1)
    saved = dm.search_memories
    try:
        def boom(*args, **kwargs):
            raise RuntimeError("Ollama off")

        dm.search_memories = boom
        out = run("forget the road trip to Colorado")
        assert out.startswith("I couldn't search my memory right now (RuntimeError: Ollama off)") and "forget <id>" in out
        assert f'"{F1}"' in run(f"forget {a[:6]}")
    finally:
        dm.search_memories = saved


@check("L2 if the memory store itself fails, the answer is one plain sentence, never an exception")
def _():
    fresh()
    saved = dm.list_memories
    try:
        def boom(*args, **kwargs):
            raise RuntimeError("boom")

        dm.list_memories = boom
        for message in ("what do you remember?", "forget everything", "forget that", "forget the window"):
            assert run(message) == "I couldn't do that with my memory (RuntimeError: boom). Nothing was changed.", message
    finally:
        dm.list_memories = saved


@check("L2 chat: 'what do you remember?' is answered directly: no model call, nothing saved or recalled; it works even when the embeddings are down")
def _():
    fresh()
    save("preference", F1)
    saved = dm.search_memories
    try:
        def boom(*args, **kwargs):
            raise RuntimeError("Ollama off")

        dm.search_memories = boom
        out = say("what do you remember?")
    finally:
        dm.search_memories = saved
    assert F1 in out and reply_calls == [] and model_calls == [] and queue_actions() == []


@check("L2 chat: 'forget ...' gives only a PROPOSAL (nothing deleted, no model call); 'forget it' is NOT a command and goes through as a normal message")
def _():
    fresh()
    save("plan", F2)
    out = say("forget the road trip to Colorado")
    assert out.startswith("Proposed: forget this memory") and dm.memory_count() == 1 and reply_calls == []
    assert say("forget it") == "Now. Listen carefully." and len(reply_calls) == 1


@check("L2 chat: memory commands are NOT blocked by the topic refusal")
def _():
    fresh()
    save("preference", F1)
    out = say("forget what I said about the weather")
    assert out != chat.REFUSAL_MESSAGE and "couldn't find a memory matching" in out and reply_calls == []


@check("L2 chat: commands never trigger saving or recalling (the memory fakes would be called otherwise)")
def _():
    fresh()
    calls = []
    saved = (chat.remember_from_message, chat.memory_context_block)
    chat.remember_from_message = lambda m: calls.append("remember") or []
    chat.memory_context_block = lambda m: calls.append("recall")
    try:
        save("preference", F1)
        say("what do you remember?")
        say("forget that")
        say("forget everything")
    finally:
        chat.remember_from_message, chat.memory_context_block = saved
    assert calls == []


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 simultaneous approvals of the same forget: exactly one deletes, the rest are turned away")
def _():
    fresh()
    save("plan", F2)
    run("forget that")
    aid = queue_actions()[0]["id"]
    results = []

    def go():
        r = A.approve_and_execute(aid)
        with _lock:
            results.append(r)

    threads = [threading.Thread(target=go) for _n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert len([r for r in results if r.startswith("Forgotten:")]) == 1, results
    assert dm.memory_count() == 0


@check("L4 20 'forget everything' proposals approved at the same time: exactly one wipes, the other 19 find nothing left")
def _():
    fresh()
    for n in range(5):
        save("project_fact", f"unique statement {n} about subject{n}")
    for _n in range(20):
        run("forget everything")
    ids = [a["id"] for a in queue_actions()]
    assert len(ids) == 20
    results = []

    def go(aid):
        r = A.approve_and_execute(aid)
        with _lock:
            results.append(r)

    threads = [threading.Thread(target=go, args=(i,)) for i in ids]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert len([r for r in results if r == "Forgot 5 memories."]) == 1, results
    assert len([r for r in results if "already gone" in r]) == 19 and dm.memory_count() == 0


@check("L4 saving, listing and forgetting at the same time: no errors")
def _():
    fresh()
    save("preference", F1)
    errors = []

    def saver(n):
        try:
            dm.save_memory("project_fact", f"unique statement {n} about subject{n}")
        except Exception as e:
            errors.append(repr(e))

    def lister():
        try:
            assert run("what do you remember?")
        except Exception as e:
            errors.append(repr(e))

    def forgetter():
        try:
            assert run("forget that")
        except Exception as e:
            errors.append(repr(e))

    threads = ([threading.Thread(target=saver, args=(n,)) for n in range(10)] +
               [threading.Thread(target=lister) for _n in range(5)] + [threading.Thread(target=forgetter) for _n in range(5)])
    [x.start() for x in threads]; [x.join() for x in threads]
    assert not errors, errors


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 hostile messages (50,000 characters, newlines, unicode, regex characters, null characters, non-text) never crash and never delete anything")
def _():
    fresh()
    save("preference", F1)
    for msg in ("forget " + "x" * 50000, "forget\nthe window", "forget " + "é泳🔧" * 5000, "forget [(.*)] \\",
                "\x00forget", "forget \x00", None, 5, [], {}):
        out = C.handle_memory_command(C.detect_memory_command(msg))
        assert isinstance(out, str), msg
    assert dm.memory_count() == 1


@check("L5 hostile ids and targets (10,000 hex characters, SQL-looking text, odd symbols) delete nothing")
def _():
    fresh()
    save("preference", F1)
    for msg in ("forget " + "a" * 10000, "forget 'abc'; DROP TABLE memory; --", "forget %", "forget abcdef-", "forget #" + "f" * 36,
                "forget " + "0" * 40):
        assert isinstance(run(msg), str), msg
    assert dm.memory_count() == 1 and all(a["type"] != "forget_all_memories" for a in queue_actions())


@check("L5 hostile command objects handed straight to the handler (None, {}, wrong types) get a friendly sentence and change nothing")
def _():
    fresh()
    save("preference", F1)
    for bad in (None, {}, {"kind": 5}, {"kind": "forget"}, {"kind": "forget", "target": {"a": 1}}, {"kind": "forget", "target": None},
                "x", 5, [], {"kind": ["list"]}):
        assert isinstance(C.handle_memory_command(bad), str), bad
    assert dm.memory_count() == 1


@check("L5 odd entries already in the store (no metadata, very long text) are listed without trouble and can be forgotten by id")
def _():
    fresh()
    dm._get_collection().add(documents=["no meta here"], ids=["0badc0de-1"])
    save("preference", F1)
    out = run("what do you remember?")
    assert "no meta here" in out and "id 0badc0" in out and F1 in out
    assert 'no meta here' in run("forget 0badc0")


@check("L2 a vague target whose WORDS fit several memories ('the Civic') asks which, even with the embeddings down; nothing is queued")
def _():
    fresh()
    save("goal", "Joey plans to keep his Civic until it reaches 150k miles")
    save("preference", "Joey always uses full synthetic 0W-20 oil in his Civic")
    save("plan", "Joey is planning a road trip to Colorado in November")
    out = run("forget the Civic")
    assert "more than one memory" in out and "keep his Civic" in out and "0W-20" in out and "Colorado" not in out
    saved = dm.search_memories
    try:
        def boom(*args, **kwargs):
            raise RuntimeError("Ollama off")

        dm.search_memories = boom
        assert "more than one memory" in run("forget the Civic")
    finally:
        dm.search_memories = saved
    assert queue_actions() == [] and dm.memory_count() == 3


@check("L2 his exact words fit ONE memory but it is too far in meaning (long fact, short target): still proposed; same when the embeddings are down")
def _():
    fresh()
    long_fact = "Joey always uses full synthetic 0W-20 oil in his Civic and never mixes brands for any reason at all"
    save("preference", long_fact)
    save("plan", "Joey is planning a road trip to Colorado in November")
    assert dm.search_memories("mixes brands", max_distance=C.FORGET_MAX_DISTANCE) == []      # the premise
    assert run("forget mixes brands").startswith(f'Proposed: forget this memory: "{long_fact}"')
    saved = dm.search_memories
    try:
        def boom(*args, **kwargs):
            raise RuntimeError("Ollama off")

        dm.search_memories = boom
        assert run("forget mixes brands").startswith(f'Proposed: forget this memory: "{long_fact}"')
    finally:
        dm.search_memories = saved
    assert dm.memory_count() == 2


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)