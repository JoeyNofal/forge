"""
CIPHER onto the shared ActionGate — L1, L2, L4, L5 tests for the behaviours that are new:
short ids, deny only touches CIPHER's own actions, a failing command is recorded as
FAILED with its exit code, list_pending, and the wiring itself. (The older CIPHER
action suites keep proving everything that must NOT change.)

REAL file writes and REAL harmless commands, always against throwaway TEMP paths. No model, no keys.

Run from the repo root:  python -m agents.cipher.test_cipher_gate
"""
import json
import os
import re
import shutil
import subprocess
import tempfile
import threading

_QUEUE_DIR = tempfile.mkdtemp(prefix="cipher_gate_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")
TEST_DIR = tempfile.mkdtemp(prefix="cipher_gate_files_")

from agents.cipher import cipher_tools as C
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
SRC_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "cipher_tools.py")
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


def reset():
    for p in (QUEUE, QUEUE + ".lock"):
        if os.path.exists(p):
            try:
                os.remove(p)
            except OSError:
                pass


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


def entry(action_id, type_="create_file", details=None, status="pending", agent="cipher"):
    return {"id": action_id, "agent": agent, "type": type_, "details": details,
            "status": status, "result": None,
            "created_at": "2026-01-01T00:00:00", "resolved_at": None}


def function_source(name):
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", SRC, re.S | re.M)
    assert m, name
    return m.group(0)


def tpath(name):
    return os.path.join(TEST_DIR, name)


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 CIPHER no longer carries its own claim/finalize/queue logic: it only uses the shared gate")
def _():
    import ast
    ast.parse(SRC)
    for banned in ("claim_action", "finalize_action", "create_pending_action", "get_pending_action", "resolve_action"):
        assert banned not in SRC, banned
    assert "ActionGate" in SRC and "_gate.approve_and_execute" in function_source("approve_and_execute")
    assert not re.search(r"except\s*:", SRC) and "NEXUS SYSTEM" not in SRC and "API_KEY" not in SRC


@check("L1 only the _run_* handlers call the real file/command actions; proposing, approving and denying never do")
def _():
    names = re.findall(r"^def (\w+)\(", SRC, re.M)
    file_callers = [n for n in names if n != "_real_create_file" and "_real_create_file(" in function_source(n)]
    cmd_callers = [n for n in names if n != "_real_run_command" and "_real_run_command(" in function_source(n)]
    assert file_callers == ["_run_create_file"], file_callers
    assert cmd_callers == ["_run_command"], cmd_callers
    for n in ("propose_create_file", "propose_run_command", "approve_and_execute", "deny_action", "list_pending"):
        assert "_real_" not in function_source(n), n


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 proposal wording is unchanged and proposing does NOTHING real")
def _():
    reset()
    p = tpath("proposed_only.txt")
    aid, desc = C.propose_create_file(p, "hello")
    assert desc == f"create {p}" and not os.path.exists(p) and status_of(aid) == "pending"
    cid, cdesc = C.propose_run_command("echo nothing_yet")
    assert cdesc == "run: echo nothing_yet" and status_of(cid) == "pending"


@check("L2 approve creates the real file; a second approval does nothing")
def _():
    reset()
    p = tpath("made.txt")
    aid, _ = C.propose_create_file(p, "real content")
    out = C.approve_and_execute(aid)
    assert out == f"Created {p} (12 chars)." and open(p, encoding="utf-8").read() == "real content"
    assert status_of(aid) == "executed"
    assert "already executed" in C.approve_and_execute(aid)


@check("L2 a unique start of the id (6+ characters) works; too short does not")
def _():
    reset()
    p = tpath("short_id.txt")
    aid, _ = C.propose_create_file(p, "x")
    assert C.approve_and_execute(aid[:5]).startswith("No pending action found") and not os.path.exists(p)
    assert C.approve_and_execute(aid[:6]).startswith("Created") and os.path.exists(p)


@check("L2 a successful command is 'executed' and shows its output; empty output has the old wording")
def _():
    reset()
    aid, _ = C.propose_run_command("echo hello_gate_test")
    assert "hello_gate_test" in C.approve_and_execute(aid) and status_of(aid) == "executed"
    eid, _ = C.propose_run_command('python -c "pass"')
    assert C.approve_and_execute(eid) == "(command exited 0, no output)" and status_of(eid) == "executed"


@check("L2 REAL BUG FIXED: a command that fails (non-zero exit) is recorded as FAILED, with its exit code")
def _():
    reset()
    aid, _ = C.propose_run_command('python -c "import sys; sys.exit(3)"')
    out = C.approve_and_execute(aid)
    assert out.startswith("Command failed (exit code 3)"), out
    assert status_of(aid) == "failed"
    bid, _ = C.propose_run_command("this_is_not_a_real_command_xyz123")
    out2 = C.approve_and_execute(bid)
    assert out2.startswith("Command failed (exit code"), out2
    assert status_of(bid) == "failed"


@check("L2 REAL BUG FIXED: deny only touches CIPHER's own actions (it used to deny anyone's)")
def _():
    reset()
    foreign = pa.create_pending_action("drive", "log_mileage", {"mileage": 5})
    out = C.deny_action(foreign)
    assert out == f"Action {foreign} doesn't belong to CIPHER.", out
    assert status_of(foreign) == "pending"
    p = tpath("never_denied_file.txt")
    aid, _ = C.propose_create_file(p, "should never exist")
    out2 = C.deny_action(aid)
    assert out2.startswith("Denied: create_file (") and status_of(aid) == "denied" and not os.path.exists(p)
    assert "already denied" in C.approve_and_execute(aid) and not os.path.exists(p)


@check("L2 list_pending shows only CIPHER's waiting actions")
def _():
    reset()
    assert C.list_pending() == "Nothing waiting for approval."
    a, _ = C.propose_create_file(tpath("listed.txt"), "x")
    b, _ = C.propose_run_command("echo listed")
    pa.create_pending_action("drive", "log_mileage", {"mileage": 5})
    C.approve_and_execute(a)
    lines = C.list_pending().splitlines()
    assert len(lines) == 1 and lines[0].startswith(b) and "run_command" in lines[0], lines


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 threads approve the SAME real command at once: it runs exactly once")
def _():
    reset()
    marker = tpath("race_counter.txt")
    aid, _ = C.propose_run_command(f'python -c "open(r\'{marker}\', \'a\').write(\'x\')"')
    results, lock = [], threading.Lock()
    barrier = threading.Barrier(20)

    def worker():
        barrier.wait()
        r = C.approve_and_execute(aid)
        with lock:
            results.append(r)

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert open(marker, encoding="utf-8").read() == "x", "the command ran more than once"
    assert sum(1 for r in results if "already" in r) == 19 and status_of(aid) == "executed"


@check("L4 20 different file creations at once: all 20 files created, each with its own content")
def _():
    reset()
    ids = [C.propose_create_file(tpath(f"many_{i}.txt"), f"content {i}")[0] for i in range(20)]
    barrier = threading.Barrier(20)

    def worker(i):
        barrier.wait()
        C.approve_and_execute(ids[i])

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert all(open(tpath(f"many_{i}.txt"), encoding="utf-8").read() == f"content {i}" for i in range(20))
    assert all(a["status"] == "executed" for a in queue_actions())


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 hand-damaged queue entries fail cleanly and do nothing: missing keys, details None, unknown type")
def _():
    reset()
    write_queue([entry("aaaaaa111111", details={}), entry("bbbbbb222222", details=None),
                 entry("cccccc333333", type_="format_disk", details={"x": 1}),
                 entry("dddddd444444", type_="run_command", details={})])
    for aid in ("aaaaaa111111", "bbbbbb222222", "dddddd444444"):
        out = C.approve_and_execute(aid)
        assert out.startswith("Execution failed:") and status_of(aid) == "failed", (aid, out)
    out = C.approve_and_execute("cccccc333333")
    assert out == "Unknown action type: format_disk" and status_of("cccccc333333") == "failed"


@check("L5 junk ids (empty, None, number, list, regex-special, huge) never crash or approve/deny anything")
def _():
    reset()
    C.propose_create_file(tpath("junk_id_target.txt"), "x")
    for bad in ("", "   ", None, 123, [], "a.*b", "[", "\\", "x" * 10000):
        for fn in (C.approve_and_execute, C.deny_action):
            out = fn(bad)  # pyright: ignore[reportArgumentType]
            assert isinstance(out, str) and "No " in out, (fn.__name__, bad, out)
    assert not os.path.exists(tpath("junk_id_target.txt")) and all(a["status"] == "pending" for a in queue_actions())


@check("L5 50,000 characters, unicode and emoji survive a real file create intact")
def _():
    reset()
    content = "émojis 🎉 日本語 " + "z" * 50000
    p = tpath("big_unicode.txt")
    aid, _ = C.propose_create_file(p, content)
    assert C.approve_and_execute(aid).startswith("Created")
    assert open(p, encoding="utf-8").read() == content


@check("L5 a real timeout still raises from _real_run_command (never hangs)")
def _():
    try:
        C._real_run_command('python -c "import time; time.sleep(3)"', timeout=1)
    except subprocess.TimeoutExpired:
        return
    raise AssertionError("no timeout was raised")


@check("L5 a corrupt queue file: proposing fails LOUDLY and nothing real happens")
def _():
    reset()
    os.makedirs(os.path.dirname(QUEUE), exist_ok=True)
    with open(QUEUE, "w", encoding="utf-8") as f:
        f.write("{not json")
    p = tpath("corrupt_queue_file.txt")
    try:
        C.propose_create_file(p, "x")
    except Exception:
        pass
    else:
        raise AssertionError("did not fail loudly")
    assert not os.path.exists(p)
    reset()


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
shutil.rmtree(TEST_DIR, ignore_errors=True)
raise SystemExit(0 if passed == len(_results) else 1)