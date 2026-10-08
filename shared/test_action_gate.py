"""
ACTION GATE — L1, L2, L4, L5 tests for shared/action_gate.py.
No model, no keys, no cost. TEMP files only: your real pending_actions.json
is never touched. (L3 "real end-to-end" happens when ATLAS and DRIVE are
re-pointed at this gate in Parts B and C and their real flows are re-run.)

Run from the repo root:  python -m shared.test_action_gate
"""
import json
import os
import re
import tempfile
import threading

# Point the queue at a throwaway file BEFORE importing anything that reads it
# (the queue path is read once, at import time).
_QUEUE_DIR = tempfile.mkdtemp(prefix="action_gate_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from shared import pending_actions as pa
from shared.action_gate import ActionGate

QUEUE = pa.PENDING_ACTIONS_PATH
SRC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "action_gate.py")
with open(SRC_PATH, encoding="utf-8") as f:
    SRC = f.read()

_results = []


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


def raises(fn, exc=Exception):
    try:
        fn()
    except exc:
        return True
    return False


# ── a pretend agent: handlers that record every call ──
calls = []


def h_ok(d):
    calls.append(("ok", d))
    return True, f"saved {d.get('n')}"


def h_no(d):
    calls.append(("no", d))
    return False, "refused by handler"


def h_boom(d):
    calls.append(("boom", d))
    raise ValueError("boom")


def h_junk(d):
    calls.append(("junk", d))
    return "just a string"


def describe(t, d):
    return f"{t}: {d}"


def make_gate():
    return ActionGate("testagent", "TESTAGENT", describe,
                      {"ok": h_ok, "no": h_no, "boom": h_boom, "junk": h_junk})


GATE = make_gate()


def reset():
    """Empty queue, empty call log."""
    for p in (QUEUE, QUEUE + ".lock"):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass
    calls.clear()


def queue_actions():
    if not os.path.exists(QUEUE):
        return []
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f)["actions"]


def status_of(action_id):
    return [a for a in queue_actions() if a["id"] == action_id][0]["status"]


def write_queue(actions):
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    with open(QUEUE, "w", encoding="utf-8") as f:
        json.dump({"actions": actions}, f)


def entry(action_id, agent="testagent", type_="ok", details=None, status="pending"):
    return {"id": action_id, "agent": agent, "type": type_,
            "details": {"n": 0} if details is None else details,
            "status": status, "result": None,
            "created_at": "2026-01-01T00:00:00", "resolved_at": None}


def method_source(name):
    m = re.search(rf"^    def {name}\(.*?(?=^    def |\Z)", SRC, re.S | re.M)
    assert m, name
    return m.group(0)


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 parses; shared code imports nothing from agents/")
def _():
    import ast
    ast.parse(SRC)
    assert "from agents" not in SRC and "import agents" not in SRC


@check("L1 no bare 'except:', no secrets, no old paths, no raw open()")
def _():
    assert not re.search(r"except\s*:", SRC)
    assert "NEXUS SYSTEM" not in SRC and "API_KEY" not in SRC
    assert not re.search(r"\bopen\(", SRC)


@check("L1 approval uses the atomic claim/finalize pair; only approve_and_execute runs a handler")
def _():
    body = method_source("approve_and_execute")
    assert "claim_action" in body and "finalize_action" in body
    for other in ("propose", "find_action", "deny_action", "list_pending", "describe"):
        assert "handler(" not in method_source(other), other


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 constructor refuses bad settings")
def _():
    good = {"ok": h_ok}
    assert raises(lambda: ActionGate("", "X", describe, good), ValueError)
    assert raises(lambda: ActionGate("a", "  ", describe, good), ValueError)
    assert raises(lambda: ActionGate("a", "A", "not callable", good), TypeError)
    assert raises(lambda: ActionGate("a", "A", describe, {}), TypeError)
    assert raises(lambda: ActionGate("a", "A", describe, ["ok"]), TypeError)
    assert raises(lambda: ActionGate("a", "A", describe, {"ok": "not callable"}), TypeError)
    assert raises(lambda: ActionGate("a", "A", describe, {"": h_ok}), TypeError)
    assert raises(lambda: ActionGate("a", "A", describe, good, min_id_prefix=0), ValueError)
    assert raises(lambda: ActionGate("a", "A", describe, good, min_id_prefix=True), ValueError)


@check("L2 propose queues a pending action and runs NO handler")
def _():
    reset()
    a = GATE.propose("ok", {"n": 1})
    assert calls == []
    q = queue_actions()
    assert len(q) == 1 and q[0]["id"] == a and q[0]["status"] == "pending"
    assert q[0]["agent"] == "testagent" and q[0]["details"] == {"n": 1}


@check("L2 propose refuses an action type with no handler, and queues nothing")
def _():
    reset()
    assert raises(lambda: GATE.propose("nope", {}), ValueError)
    assert raises(lambda: GATE.propose(["ok"], {}), TypeError)
    assert queue_actions() == []


@check("L2 approve runs the handler exactly once and records 'executed'")
def _():
    reset()
    a = GATE.propose("ok", {"n": 7})
    out = GATE.approve_and_execute(a)
    assert out == "saved 7", out
    assert calls == [("ok", {"n": 7})]
    assert status_of(a) == "executed"
    again = GATE.approve_and_execute(a)
    assert "already executed" in again and len(calls) == 1, again


@check("L2 a handler returning (False, why) is recorded as FAILED and the reason is returned")
def _():
    reset()
    a = GATE.propose("no", {"n": 1})
    out = GATE.approve_and_execute(a)
    assert out == "refused by handler", out
    assert status_of(a) == "failed"


@check("L2 a handler that raises becomes 'Execution failed: ...' and FAILED, never an exception")
def _():
    reset()
    a = GATE.propose("boom", {"n": 1})
    out = GATE.approve_and_execute(a)
    assert out == "Execution failed: ValueError: boom", out
    assert status_of(a) == "failed"


@check("L2 a handler returning junk (not (bool, str)) is FAILED, never dressed up as success")
def _():
    reset()
    a = GATE.propose("junk", {"n": 1})
    out = GATE.approve_and_execute(a)
    assert "invalid result" in out and out.startswith("Execution failed"), out
    assert status_of(a) == "failed"


@check("L2 an unknown type found in the queue fails cleanly and runs nothing")
def _():
    reset()
    write_queue([entry("abcdef123456", type_="nope")])
    out = GATE.approve_and_execute("abcdef123456")
    assert out == "Unknown action type: nope", out
    assert calls == [] and status_of("abcdef123456") == "failed"


@check("L2 ids: full id, unique 6+ character start, too-short start, ambiguous start")
def _():
    reset()
    a = GATE.propose("ok", {"n": 1})
    assert GATE.approve_and_execute(a[:6]) == "saved 1"
    b = GATE.propose("ok", {"n": 2})
    short = GATE.approve_and_execute(b[:5])
    assert short.startswith("No pending action found") and status_of(b) == "pending", short
    reset()
    write_queue([entry("aaaaaa111111"), entry("aaaaaa222222")])
    amb = GATE.approve_and_execute("aaaaaa")
    assert "more than one" in amb and calls == [], amb


@check("L2 another agent's action is never touched, listed, or approved through this gate")
def _():
    reset()
    other_id = pa.create_pending_action("otheragent", "ok", {"n": 9})
    out = GATE.approve_and_execute(other_id)
    assert out == f"Action {other_id} doesn't belong to TESTAGENT.", out
    assert calls == [] and status_of(other_id) == "pending"
    assert GATE.approve_and_execute(other_id[:8]).startswith("No pending action found")
    assert GATE.list_pending() == "Nothing waiting for approval."


@check("L2 deny: handler never runs, cannot be approved afterwards, cannot deny a finished action")
def _():
    reset()
    a = GATE.propose("ok", {"n": 3})
    out = GATE.deny_action(a)
    assert out.startswith("Denied: ok:") and status_of(a) == "denied", out
    assert "already denied" in GATE.approve_and_execute(a) and calls == []
    b = GATE.propose("ok", {"n": 4})
    GATE.approve_and_execute(b)
    assert GATE.deny_action(b) == f"Action {b} was already executed."


@check("L2 list_pending shows only this agent's waiting actions, one per line")
def _():
    reset()
    a = GATE.propose("ok", {"n": 1})
    b = GATE.propose("no", {"n": 2})
    pa.create_pending_action("otheragent", "ok", {"n": 3})
    GATE.approve_and_execute(a)
    lines = GATE.list_pending().splitlines()
    assert len(lines) == 1 and lines[0].startswith(b) and "no:" in lines[0], lines


@check("L2 a describe() that crashes can never break deny or list")
def _():
    reset()

    def bad_describe(t, d):
        raise RuntimeError("describe bug")
    g = ActionGate("testagent", "TESTAGENT", bad_describe, {"ok": h_ok})
    a = g.propose("ok", {"n": 1})
    assert "ok:" in g.list_pending()
    assert g.deny_action(a).startswith("Denied: ok:")


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 simultaneous approvals of the SAME action: the handler runs exactly once")
def _():
    reset()
    a = GATE.propose("ok", {"n": 1})
    outs, lock = [], threading.Lock()
    barrier = threading.Barrier(20)

    def worker():
        barrier.wait()
        r = GATE.approve_and_execute(a)
        with lock:
            outs.append(r)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 1, len(calls)
    assert sum(1 for o in outs if o == "saved 1") == 1
    assert all("already" in o for o in outs if o != "saved 1")
    assert status_of(a) == "executed"


@check("L4 20 DIFFERENT actions approved at once: all 20 run once each, no lost queue updates")
def _():
    reset()
    ids = [GATE.propose("ok", {"n": i}) for i in range(20)]
    outs, lock = {}, threading.Lock()
    barrier = threading.Barrier(20)

    def worker(i):
        barrier.wait()
        r = GATE.approve_and_execute(ids[i])
        with lock:
            outs[i] = r

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(calls) == 20 and sorted(d["n"] for _, d in calls) == list(range(20))
    assert all(outs[i] == f"saved {i}" for i in range(20))
    assert all(a["status"] == "executed" for a in queue_actions()) and len(queue_actions()) == 20


@check("L4 20 simultaneous proposals: all 20 land in the queue, none lost")
def _():
    reset()
    got, lock = [], threading.Lock()
    barrier = threading.Barrier(20)

    def worker(i):
        barrier.wait()
        a = GATE.propose("ok", {"n": i})
        with lock:
            got.append(a)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert len(set(got)) == 20 and len(queue_actions()) == 20


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 corrupt queue file: proposing fails LOUDLY and no handler runs")
def _():
    reset()
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    with open(QUEUE, "w", encoding="utf-8") as f:
        f.write("{not json")
    assert raises(lambda: GATE.propose("ok", {"n": 1}))
    assert raises(lambda: GATE.approve_and_execute("abcdef123456"))
    assert calls == []
    reset()


@check("L5 hand-damaged queue entry (details is None): fails cleanly, recorded as failed")
def _():
    reset()
    write_queue([{"id": "abcdef123456", "agent": "testagent", "type": "ok",
                  "details": None, "status": "pending", "result": None}])
    out = GATE.approve_and_execute("abcdef123456")
    assert out.startswith("Execution failed:"), out
    assert status_of("abcdef123456") == "failed"


@check("L5 empty / None / number / list / whitespace / regex-special / huge ids never crash or approve anything")
def _():
    reset()
    GATE.propose("ok", {"n": 1})
    for bad in ("", "   ", None, 123, [], "a.*b", "[", "\\", "x" * 10000):
        for fn in (GATE.approve_and_execute, GATE.deny_action):
            out = fn(bad)
            assert isinstance(out, str) and "No " in out, (fn.__name__, bad, out)
    assert calls == [] and all(a["status"] == "pending" for a in queue_actions())


@check("L5 50,000-character text and unicode/emoji reach the handler intact")
def _():
    reset()
    payload = {"n": 5, "text": "y" * 50000, "note": "Schwimmen 泳ぐ 🏊 résumé"}
    a = GATE.propose("ok", payload)
    assert GATE.approve_and_execute(a) == "saved 5"
    assert calls[0][1] == payload


@check("L5 a handler that raises a weird exception type is still caught and named")
def _():
    reset()

    def h_key(d):
        return {"a": 1}["missing"]
    g = ActionGate("testagent", "TESTAGENT", describe, {"ok": h_key})
    a = g.propose("ok", {"n": 1})
    out = g.approve_and_execute(a)
    assert out.startswith("Execution failed: KeyError"), out
    assert status_of(a) == "failed"


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)