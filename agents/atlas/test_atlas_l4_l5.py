"""
ATLAS increment (a) — L4 (sustained load / concurrency) + L5 (extreme,
breaking inputs) for chat.py. FAKED model and search (no keys, no cost),
TEMP data files only — your real fitness.json is never touched.

Run from the repo root:  python -m agents.atlas.test_atlas_l4_l5
"""
import json
import os
import shutil
import tempfile
import threading
import time

from agents.atlas import chat

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


# Thread-safe fakes: no shared mutable state. The fake model ECHOES the full
# prompt it was given, so tests can see exactly what reached the model.
def echo_model(agent, tier, system_prompt, messages, location=""):
    yield messages[-1]["content"]


def fake_search(query, num_results=3):
    return "Web search results:\n\n1. Title\n   snippet\n   link"


chat.stream_by_tier = echo_model
chat.web_search = fake_search


def run(message, history=None):
    return "".join(chat.stream_atlas(message, history))


def temp_data(obj=None):
    d = tempfile.mkdtemp(prefix="atlas_l45_")
    path = os.path.join(d, "fitness.json")
    os.environ["FITNESS_DATA_PATH"] = path
    if obj is not None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)
    return path, d


SAMPLE = {
    "profile": {"name": "Joey", "notes": "test"},
    "workouts": [
        {"type": "swim", "date": "2026-03-01", "total_distance_yards": 2000, "duration_minutes": 60,
         "strokes": ["freestyle"], "difficulty_1_to_10": 7},
        {"type": "swim", "date": "2026-03-05", "total_distance_yards": 1500, "duration_minutes": 45,
         "strokes": ["breaststroke"], "difficulty_1_to_10": 6},
        {"type": "gym", "date": "2026-03-02", "exercises": [{"name": "bench press"}],
         "duration_minutes": 50, "difficulty_1_to_10": 6},
    ],
    "injuries": [{"status": "none", "description": "placeholder"}],
}

# ───────────────────────── L4 — SUSTAINED / CONCURRENT ─────────────────────────

@check("L4 100 sequential mixed calls: right behavior every time, zero crashes")
def _():
    path, d = temp_data(SAMPLE)
    kinds = [
        ("give me a leg day plan", lambda o, m: f"Joey says: {m}" in o and "ATLAS DATA SUMMARY" in o),
        ("what's the weather today", lambda o, m: o == chat.REFUSAL_MESSAGE),
        ("how many swim workouts have I logged", lambda o, m: "2 session(s), 3,500 total yards" in o),
        ("any recovery tips after a hard swim", lambda o, m: "Background web search results" in o),
        ("show me my gym history", lambda o, m: "Gym history: 1 session(s)" in o),
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
            outputs[n] = run(f"give me a leg day plan token{n:02d}end")
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=worker, args=(n,)) for n in range(20)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert not errors, errors
    for n, out in outputs.items():
        assert out.endswith(f"Joey says: give me a leg day plan token{n:02d}end"), (n, out[-60:])
        others = [m for m in range(20) if m != n and f"token{m:02d}end" in out]
        assert not others, f"thread {n} saw text from {others}"
    assert len(outputs) == 20
    shutil.rmtree(d)


@check("L4 readers stay safe while a 'tracker' rewrites the file non-atomically")
def _():
    path, d = temp_data(SAMPLE)
    stop = threading.Event()
    good = json.dumps(SAMPLE)

    def tracker_writer():
        # Mimics the Training tracker's writeFileSync: truncate, write, done —
        # here slowed down so readers really can catch it half-written.
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
                out = run("give me a leg day plan")
                with lock:
                    outputs.append(out)
            except Exception as e:
                with lock:
                    errors.append(repr(e))

    w = threading.Thread(target=tracker_writer); w.start()
    readers = [threading.Thread(target=reader) for _ in range(20)]
    for t in readers: t.start()
    for t in readers: t.join()
    stop.set(); w.join()
    assert not errors, errors[:3]
    assert len(outputs) == 160
    for out in outputs:   # every answer is either real data or an explicit note — never garbage
        assert "ATLAS DATA SUMMARY" in out or "FITNESS DATA UNAVAILABLE" in out
    shutil.rmtree(d)


@check("L4 a big log (20,000 workouts) still answers fast and bounded")
def _():
    big = {"profile": {}, "injuries": [], "workouts": [
        {"type": "swim" if i % 2 else "gym", "date": f"2026-01-{(i % 28) + 1:02d}",
         "total_distance_yards": 1000 + i, "exercises": ["squat"], "duration_minutes": 30}
        for i in range(20000)]}
    path, d = temp_data(big)
    t0 = time.time()
    out = run("give me a leg day plan")
    hist = run("how many swim workouts have I logged")
    elapsed = time.time() - t0
    assert elapsed < 10, f"too slow: {elapsed:.1f}s"
    assert "Total workouts logged: 20000" in out
    assert len(out) < 3000, f"prompt summary not bounded: {len(out)} chars"   # only last 5 workouts shown
    assert "10000 session(s)" in hist.replace(",", "") or "10,000 session(s)" in hist
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
    msg = "swim " * 10000
    out = run(msg)
    assert out.endswith(f"Joey says: {msg}")
    shutil.rmtree(d)


@check("L5 unicode / emoji / non-English text passes through untouched")
def _():
    path, d = temp_data(SAMPLE)
    msg = "Give me a 💪 workout — 水泳 plan ¿por favor? ñandú"
    assert run(msg).endswith(f"Joey says: {msg}")
    shutil.rmtree(d)


@check("L5 regex-special characters in the message can't break keyword matching")
def _():
    path, d = temp_data(SAMPLE)
    out = run("what's (the) best way [to] train swim? $^*+ \\b .*")
    assert "Background web search results" in out      # 'best way' still matched
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


@check("L5 malformed history fails loudly at the provider edge, not swallowed by ATLAS")
def _():
    path, d = temp_data(SAMPLE)

    def validating_model(agent, tier, system_prompt, messages, location=""):
        for m in messages:
            if m["role"] not in ("user", "assistant"):   # KeyError/TypeError on malformed
                raise ValueError("bad role")
        yield "ok"

    chat.stream_by_tier = validating_model
    try:
        for bad in ([{"content": "no role here"}], "oops", [None]):
            try:
                run("give me a leg day plan", bad)   # type: ignore[arg-type]
                raise AssertionError(f"malformed history {bad!r} should raise")
            except (KeyError, TypeError, ValueError):
                pass
        assert run("give me a leg day plan", [{"role": "user", "content": "hi"}]) == "ok"
    finally:
        chat.stream_by_tier = echo_model
        shutil.rmtree(d)


@check("L5 a real model failure propagates (never swallowed), partial text still delivered")
def _():
    path, d = temp_data(SAMPLE)

    def dying_model(agent, tier, system_prompt, messages, location=""):
        yield "Get "
        raise RuntimeError("provider exploded")

    chat.stream_by_tier = dying_model
    got = []
    try:
        for chunk in chat.stream_atlas("give me a leg day plan"):
            got.append(chunk)
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "provider exploded" in str(e)
    finally:
        chat.stream_by_tier = echo_model
        shutil.rmtree(d)
    assert got == ["Get "]


@check("L5 data file deleted between calls: auto-recreates, coaching keeps working")
def _():
    path, d = temp_data(SAMPLE)
    assert "Swim sessions: 2" in run("give me a leg day plan")
    os.remove(path)
    out = run("give me a leg day plan")
    assert "Total workouts logged: 0" in out and os.path.exists(path)
    shutil.rmtree(d)


@check("L5 data full of junk (nulls, wrong types) never crashes a chat turn")
def _():
    junk = {"profile": 5, "workouts": [None, 1, "x", {}, {"type": "swim"}, {"type": None},
                                        {"type": "gym", "exercises": "notalist"}],
            "injuries": [None, 3, {"status": None}]}
    path, d = temp_data(junk)
    assert "ATLAS DATA SUMMARY" in run("give me a leg day plan")
    assert isinstance(run("show me my workouts"), str)
    assert isinstance(run("what have I done overall"), str)
    shutil.rmtree(d)


@check("L5 shouting still hits the data shortcut (case-insensitive) with no model call")
def _():
    path, d = temp_data(SAMPLE)
    out = run("SHOW ME MY GYM HISTORY")
    assert "Gym history: 1 session(s)" in out and "ATLAS DATA SUMMARY" not in out
    shutil.rmtree(d)


@check("L5 refusal gate still intact after all the extreme inputs above")
def _():
    path, d = temp_data(SAMPLE)
    assert run("what's the weather today") == chat.REFUSAL_MESSAGE
    assert run("help me write python code") == chat.REFUSAL_MESSAGE
    assert "Joey says:" in run("give me a leg day plan")
    shutil.rmtree(d)


passed = sum(1 for _, ok, _ in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
if passed != len(_results):
    raise SystemExit(1)