"""
DRIVE increment (a) — L4 (sustained load / concurrency) + L5 (extreme,
breaking inputs) for chat.py. FAKED model and search (no keys, no cost),
TEMP data files only — your real vehicle.json is never touched.

Run from the repo root:  python -m agents.drive.test_drive_l4_l5
"""
import json
import os
import shutil
import tempfile
import threading
import time

from agents.drive import chat

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


def echo_model(agent, tier, system_prompt, messages, location=""):
    yield messages[-1]["content"]


def fake_search(query, num_results=3):
    return "Web search results:\n\n1. Title\n   snippet\n   link"


chat.stream_by_tier = echo_model
chat.web_search = fake_search

# Logging extraction has its OWN tests; switched off here.
chat.extract_and_propose = lambda message: []
chat.prepare_recall_context = lambda message: (None, None)    # the recall check has its own tests


def run(message, history=None):
    return "".join(chat.stream_drive(message, history))


def temp_data(obj=None):
    d = tempfile.mkdtemp(prefix="drive_l45_")
    path = os.path.join(d, "vehicle.json")
    os.environ["VEHICLE_DATA_PATH"] = path
    if obj is not None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)
    return path, d


SAMPLE = {"vehicles": [{
    "active": True, "make": "Honda", "model": "Civic", "year": 2016,
    "vin": "19XFC2F57GE016309", "current_mileage": 48200,
    "maintenance_log": [
        {"service_type": "oil_change", "date": "2026-06-01", "mileage": 45000, "cost": 89.99},
    ],
    "gas_log": [
        {"date": "2026-08-01", "mileage": 47000, "gallons": 11.2, "price_per_gallon": 3.45,
         "total_cost": 38.64},
    ],
    "issues": [{"description": "clicking noise on left turns", "severity": "mild", "status": "open"}],
}]}

# ───────────────────────── L4 — SUSTAINED / CONCURRENT ─────────────────────────

@check("L4 100 sequential mixed calls: right behavior every time, zero crashes")
def _():
    path, d = temp_data(SAMPLE)
    kinds = [
        ("is it time for an oil change", lambda o, m: f"Joey says: {m}" in o and "VEHICLE DATA SUMMARY" in o),
        ("what's the weather today", lambda o, m: o == chat.REFUSAL_MESSAGE),
        ("show me my maintenance history", lambda o, m: "89.99" in o),
        ("is there a recall on my car", lambda o, m: "Background web search results" in o),
        ("show me my gas history", lambda o, m: "1 fill-ups" in o),
    ]
    bad = []
    for i in range(100):
        msg, ok = kinds[i % len(kinds)]
        out = run(msg)
        if not out.strip() or not ok(out, msg):
            bad.append((i, msg, out[:80]))
    assert not bad, bad[:3]
    shutil.rmtree(d)


@check("L4 20 simultaneous calls: zero cross-talk between concurrent conversations")
def _():
    path, d = temp_data(SAMPLE)
    outputs, errors = {}, []

    def worker(n):
        try:
            outputs[n] = run(f"is it time for an oil change token{n:02d}end")
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors, errors
    for n, out in outputs.items():
        assert out.endswith(f"Joey says: is it time for an oil change token{n:02d}end"), (n, out[-70:])
        others = [m for m in range(20) if m != n and f"token{m:02d}end" in out]
        assert not others, f"thread {n} saw text from {others}"
    assert len(outputs) == 20
    shutil.rmtree(d)


@check("L4 readers stay safe while a writer rewrites the file non-atomically")
def _():
    path, d = temp_data(SAMPLE)
    stop = threading.Event()
    good = json.dumps(SAMPLE)

    def bad_writer():
        while not stop.is_set():
            with open(path, "w", encoding="utf-8") as f:
                f.write(good[: len(good) // 2])
                f.flush()
                time.sleep(0.05)
                f.write(good[len(good) // 2:])
            time.sleep(0.02)

    errors, outputs = [], []
    lock = threading.Lock()

    def reader():
        for _ in range(8):
            try:
                out = run("is it time for an oil change")
                with lock:
                    outputs.append(out)
            except Exception as e:
                with lock:
                    errors.append(repr(e))

    w = threading.Thread(target=bad_writer); w.start()
    readers = [threading.Thread(target=reader) for _ in range(20)]
    for t in readers: t.start()
    for t in readers: t.join()
    stop.set(); w.join()
    assert not errors, errors[:3]
    assert len(outputs) == 160
    for out in outputs:
        assert "VEHICLE DATA SUMMARY" in out or "VEHICLE DATA UNAVAILABLE" in out
    shutil.rmtree(d)


@check("L4 a big log (20,000 maintenance entries) still answers fast and bounded")
def _():
    big = {"vehicles": [{
        "active": True, "make": "Honda", "model": "Civic", "year": 2016, "vin": "x",
        "current_mileage": 200000,
        "maintenance_log": [{"service_type": "oil_change", "date": f"2020-{(i % 12) + 1:02d}-01",
                              "mileage": i * 10} for i in range(20000)],
        "gas_log": [{"date": f"2020-{(i % 12) + 1:02d}-01", "gallons": 10, "total_cost": 35}
                    for i in range(20000)],
        "issues": [],
    }]}
    path, d = temp_data(big)
    t0 = time.time()
    out = run("is it time for an oil change")
    hist = run("show me my gas history")
    elapsed = time.time() - t0
    assert elapsed < 10, f"too slow: {elapsed:.1f}s"
    assert "20000 fill-ups" in hist.replace(",", "")
    assert len(out) < 3000, f"prompt summary not bounded: {len(out)} chars"
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 empty message: no crash, a real string comes back")
def _():
    path, d = temp_data(SAMPLE)
    assert isinstance(run(""), str)
    shutil.rmtree(d)


@check("L5 50,000-character message arrives intact, no crash")
def _():
    path, d = temp_data(SAMPLE)
    msg = "car " * 10000
    out = run(msg)
    assert out.endswith(f"Joey says: {msg}")
    shutil.rmtree(d)


@check("L5 unicode / emoji / non-English text passes through untouched")
def _():
    path, d = temp_data(SAMPLE)
    msg = "Is my car 🚗 okay? — 车辆 ¿está bien? ñandú"
    assert run(msg).endswith(f"Joey says: {msg}")
    shutil.rmtree(d)


@check("L5 regex-special characters in the message can't break keyword matching")
def _():
    path, d = temp_data(SAMPLE)
    out = run("which (oil) [is] best? $^*+ \\b .*")
    assert "Background web search results" in out  # 'which' still matched
    shutil.rmtree(d)


@check("L5 None message fails LOUDLY (never silent garbage)")
def _():
    path, d = temp_data(SAMPLE)
    try:
        run(None)   # type: ignore[arg-type]
        raise AssertionError("None should raise")
    except (AttributeError, TypeError):
        pass
    shutil.rmtree(d)


@check("L5 malformed history fails loudly at the provider edge, not swallowed by DRIVE")
def _():
    path, d = temp_data(SAMPLE)

    def validating_model(agent, tier, system_prompt, messages, location=""):
        for m in messages:
            if m["role"] not in ("user", "assistant"):
                raise ValueError("bad role")
        yield "ok"

    chat.stream_by_tier = validating_model
    try:
        for bad in ([{"content": "no role here"}], "oops", [None]):
            try:
                run("is it time for an oil change", bad)   # type: ignore[arg-type]
                raise AssertionError(f"malformed history {bad!r} should raise")
            except (KeyError, TypeError, ValueError):
                pass
        assert run("is it time for an oil change", [{"role": "user", "content": "hi"}]) == "ok"
    finally:
        chat.stream_by_tier = echo_model
        shutil.rmtree(d)


@check("L5 a real model failure propagates (never swallowed), partial text still delivered")
def _():
    path, d = temp_data(SAMPLE)

    def dying_model(agent, tier, system_prompt, messages, location=""):
        yield "Now. "
        raise RuntimeError("provider exploded")

    chat.stream_by_tier = dying_model
    got = []
    try:
        for chunk in chat.stream_drive("is it time for an oil change"):
            got.append(chunk)
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "provider exploded" in str(e)
    finally:
        chat.stream_by_tier = echo_model
        shutil.rmtree(d)
    assert got == ["Now. "]


@check("L5 data file deleted between calls: auto-recreates, coaching keeps working")
def _():
    path, d = temp_data(SAMPLE)
    assert "48,200 miles" in run("is it time for an oil change")
    os.remove(path)
    out = run("is it time for an oil change")
    assert "not yet recorded" in out and os.path.exists(path)
    shutil.rmtree(d)


@check("L5 data full of junk (nulls, wrong types) never crashes a chat turn")
def _():
    junk = {"vehicles": [None, 1, "x", {}, {"active": True},
                          {"active": True, "make": "Honda", "maintenance_log": "notalist",
                           "gas_log": [None, 3, {}], "issues": [None, {"status": None}]}]}
    path, d = temp_data(junk)
    assert "VEHICLE DATA SUMMARY" in run("is it time for an oil change")
    assert isinstance(run("show me my maintenance history"), str)
    assert isinstance(run("what have i logged"), str)
    shutil.rmtree(d)


@check("L5 shouting still hits the data shortcut (case-insensitive) with no model call")
def _():
    path, d = temp_data(SAMPLE)
    out = run("SHOW ME MY GAS HISTORY")
    assert "1 fill-ups" in out and "VEHICLE DATA SUMMARY" not in out
    shutil.rmtree(d)


@check("L5 refusal gate still intact after all the extreme inputs above")
def _():
    path, d = temp_data(SAMPLE)
    assert run("what's the weather today") == chat.REFUSAL_MESSAGE
    assert run("help me write python code") == chat.REFUSAL_MESSAGE
    assert "Joey says:" in run("is it time for an oil change")
    shutil.rmtree(d)


passed = sum(1 for _, ok, _ in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
if passed != len(_results):
    raise SystemExit(1)