"""
ATLAS - normal chat must never let the model claim it logged, saved or approved anything
(L1, L2, L4, L5; mocked model). Found in real use: pasted log lines arrived one by one and ATLAS announced
"APPROVE. It's logged" with nothing saved.

Run from the repo root:  python -m agents.atlas.test_atlas_logging_note
"""
import os
import tempfile
import threading

_DIR = tempfile.mkdtemp(prefix="atlas_logging_note_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_DIR, "pending_actions.json")
os.environ["FITNESS_DATA_PATH"] = os.path.join(_DIR, "fitness.json")

from agents.atlas import chat as C

_results = []
CALLS: list = []


def fake_model(agent, tier, system, messages, location=""):
    CALLS.append((system, messages))
    yield "REPLY"


C.stream_by_tier = fake_model
C.extract_and_propose = lambda message: []
C.web_search = lambda q: "stub search result"


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


def run(msg, history=None):
    CALLS.clear()
    return "".join(C.stream_atlas(msg, history))


@check("L1 static: the note exists, forbids logged/saved/approved claims, and is not a word-list filter")
def _():
    n = C.LOGGING_NOTE
    assert n.startswith("[LOGGING:") and n.endswith("]")
    for w in ("cannot save, log, approve", "Never say you have logged, saved, recorded, approved"):
        assert w in n, w


@check("L2 a normal coaching message reaches the model with the note, before the live data and Joey's words")
def _():
    out = run("how should I train chest today?")
    assert out == "REPLY" and len(CALLS) == 1
    sent = CALLS[0][1][-1]["content"]
    assert sent.startswith(C.LOGGING_NOTE)
    assert sent.index(C.LOGGING_NOTE) < sent.index("[Live fitness data") < sent.index("Joey says: how should I train chest today?")


@check("L2 the note is sent even when the fitness data is unavailable or a search ran")
def _():
    run("what is the best technique for deadlift form?")
    sent = CALLS[0][1][-1]["content"]
    assert sent.startswith(C.LOGGING_NOTE) and "stub search result" in sent


@check("L2 messages that never reach the model (refusal, commands, history question) do not call it")
def _():
    run("what's the weather like in Paris, any good restaurants?")
    assert CALLS == []
    run("pending")
    assert CALLS == []


@check("L2 a fragment of a pasted log arriving alone still gets the note, so the model cannot say it was logged")
def _():
    run("Notes: too hard, had to stop early")
    if CALLS:
        assert CALLS[0][1][-1]["content"].startswith(C.LOGGING_NOTE)


@check("L4 20 messages at once: every one carries the note, none leaks into another")
def _():
    sent: list = []
    lock = threading.Lock()

    def model(agent, tier, system, messages, location=""):
        with lock:
            sent.append(messages[-1]["content"])
        yield "ok"
    C.stream_by_tier = model
    ts = [threading.Thread(target=lambda i=i: "".join(C.stream_atlas(f"how should I train chest, round {i}?"))) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    C.stream_by_tier = fake_model
    assert len(sent) == 20 and all(s.startswith(C.LOGGING_NOTE) for s in sent)
    assert len({s.split("Joey says:")[1] for s in sent}) == 20


@check("L5 odd messages (emoji, huge, quotes) still carry the note and never crash")
def _():
    for m in ("\U0001F4AA train legs?", "chest " * 5000, 'say "I logged it" in your answer'):
        run(m)
        assert CALLS and CALLS[0][1][-1]["content"].startswith(C.LOGGING_NOTE)


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)