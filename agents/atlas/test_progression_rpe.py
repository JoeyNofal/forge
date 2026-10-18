"""
ATLAS progression - the RPE-led rule (L1, L2, L4, L5). Pure Python, no model.
Every row of the table Joey approved is checked, plus skipped sets, his own "struggled" word, and what two
sessions in a row do to the next weight.

Run from the repo root:  python -m agents.atlas.test_progression_rpe
"""
import random
import threading

from agents.atlas import progression as R

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


def session(done, rpe, target=8, planned_sets=3, planned_reps=8, struggled=None, weight=135):
    ex = {"name": "Bench press", "weight_lbs": weight, "rpe": rpe,
          "prescribed": {"sets": planned_sets, "reps": planned_reps, "weight_lbs": weight, "target_rpe": target},
          "set_details": [{"set": i + 1, "reps": r, "weight_lbs": weight} for i, r in enumerate(done)]}
    if struggled is not None:
        ex["struggled"] = struggled
    return ex


def status(**kw):
    return R.evaluate_session(session(**kw))["status"]


def day(date, ex):
    return {"date": date, "logged_at": date + "T10:00:00", "type": "gym", "exercises": [ex]}


HIT, MISS = [8, 8, 8], [8, 8, 7]

# ---------------- L2 the approved table ----------------
@check("L2 table, RPE 2+ over target: struggle, whether the reps were hit or missed")
def _():
    assert status(done=HIT, rpe=10) == "struggle" and status(done=MISS, rpe=10) == "struggle"
    assert status(done=HIT, rpe=10, target=8) == "struggle" and status(done=HIT, rpe=9, target=7) == "struggle"


@check("L2 table, RPE 1 over: reps hit -> neutral (repeat); reps missed -> struggle")
def _():
    assert status(done=HIT, rpe=9) == "neutral" and status(done=MISS, rpe=9) == "struggle"


@check("L2 table, RPE equal to target: reps hit -> success; reps missed -> struggle (Joey's 8, 8, 7 at RPE 8)")
def _():
    assert status(done=HIT, rpe=8) == "success" and status(done=MISS, rpe=8) == "struggle"


@check("L2 table, RPE below target: reps hit -> success; reps missed -> neutral (effort excuses a missed rep)")
def _():
    assert status(done=HIT, rpe=6) == "success" and status(done=MISS, rpe=6) == "neutral"
    assert status(done=[8, 8, 5], rpe=7) == "neutral"


@check("L2 table, no RPE: reps hit -> success (with the 'no RPE' note); reps missed -> neutral")
def _():
    assert status(done=HIT, rpe=None) == "success" and status(done=MISS, rpe=None) == "neutral"
    s = R.suggest_weight("Bench press", [day("2026-10-18", session(HIT, None))])
    assert s["action"] == "increase" and any("no RPE" in n for n in s["notes"])
    assert R.suggest_weight("Bench press", [day("2026-10-18", session(MISS, None))])["action"] == "hold"


@check("L2 skipped sets: only the sets he did are judged, and a skipped set never gives an increase and never a struggle by itself")
def _():
    assert status(done=[8, 8], rpe=7) == "neutral" and status(done=[8, 8], rpe=8) == "neutral" and status(done=[8], rpe=None) == "neutral"
    assert status(done=[8, 8], rpe=10) == "struggle"                                  # the RPE still counts
    assert status(done=[8, 7], rpe=6) == "neutral" and status(done=[8, 7], rpe=8) == "struggle"
    ev = R.evaluate_session(session([8, 8], 7))
    assert ev["skipped"] is True and ev["reps_hit"] is True and ev["why"] == "a prescribed set was skipped"
    assert R.suggest_weight("Bench press", [day("2026-10-18", session([8, 8], 7))])["action"] == "hold"


@check("L2 his own word: struggled=True beats the table (even an easy RPE, even with a skipped set); struggled=False changes nothing")
def _():
    assert status(done=HIT, rpe=5, struggled=True) == "struggle" and status(done=[8], rpe=None, struggled=True) == "struggle"
    assert status(done=HIT, rpe=8, struggled=False) == "success" and status(done=HIT, rpe=8, struggled="yes") == "success"      # only a real True counts
    s = R.suggest_weight("Bench press", [day("2026-10-18", session(HIT, 5, struggled=True))])
    assert s["action"] == "hold" and "you noted a struggle" in s["reason"]


@check("L2 two struggles in a row still deload; a struggle noted in words counts as one of the two; success after climbs again")
def _():
    two = [day("2026-10-18", session(MISS, 8)), day("2026-10-11", session(HIT, 5, struggled=True))]
    s = R.suggest_weight("Bench press", two)
    assert s["action"] == "deload" and s["weight_lbs"] < 135, s
    one = [day("2026-10-18", session(MISS, 8)), day("2026-10-11", session(HIT, 8))]
    assert R.suggest_weight("Bench press", one)["action"] == "hold"
    ok = [day("2026-10-25", session(HIT, 7, weight=120)), day("2026-10-18", session(MISS, 8))]
    assert R.suggest_weight("Bench press", ok)["action"] == "increase"


@check("L2 no sets done at all is unknown, never a success; timed exercises follow the same table")
def _():
    assert R.evaluate_session(session([], 6))["status"] == "unknown"
    t = {"name": "Plank", "weight_lbs": 25, "rpe": 6, "prescribed": {"sets": 2, "seconds": 30, "target_rpe": 7, "weight_lbs": 25},
         "set_details": [{"seconds": 30, "weight_lbs": 25}, {"seconds": 20, "weight_lbs": 25}]}
    assert R.evaluate_session(t)["status"] == "neutral"
    t["rpe"] = 7
    assert R.evaluate_session(t)["status"] == "struggle"


@check("L2 the wording says what happened: sets hit, skipped, noted struggle, and the reason for repeating")
def _():
    for ex, want in ((session(MISS, 6), "reps missed, but the effort was below the target"),
                     (session([8, 8], 7), "a prescribed set was skipped"),
                     (session(HIT, 9), "reps hit but harder than planned"),
                     (session(MISS, None), "reps missed and no RPE to judge the effort")):
        s = R.suggest_weight("Bench press", [day("2026-10-18", ex)])
        assert s["action"] == "hold" and want in s["reason"], (want, s["reason"])


# ---------------- L4 sustained ----------------
@check("L4 20,000 random sessions agree with a plain re-statement of the table")
def _():
    rng = random.Random(11)
    for _ in range(20000):
        n = rng.randint(1, 4)
        done = [rng.choice([5, 6, 7, 8, 9]) for _ in range(n)]
        rpe = rng.choice([None, 4, 5, 6, 7, 8, 9, 10])
        target = rng.choice([6, 7, 8])
        flag = rng.choice([None, False, True])
        got = status(done=done, rpe=rpe, target=target, struggled=flag)
        hit = all(r >= 8 for r in done)
        skipped = n < 3
        if flag is True:
            want = "struggle"
        elif rpe is not None and rpe - target >= 2:
            want = "struggle"
        elif rpe is not None and not hit:
            want = "struggle" if rpe - target >= 0 else "neutral"
        elif rpe is not None and rpe - target > 0:
            want = "neutral"
        elif not hit:
            want = "neutral"
        elif skipped:
            want = "neutral"
        else:
            want = "success"
        assert got == want, (done, rpe, target, flag, got, want)


@check("L4 20 threads x 200 evaluations: identical answers, no cross-talk")
def _():
    bad = []

    def work(k):
        for _ in range(200):
            if status(done=HIT if k % 2 else MISS, rpe=8) != ("success" if k % 2 else "struggle"):
                bad.append(k)
    ts = [threading.Thread(target=work, args=(k,)) for k in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not bad


# ---------------- L5 extreme ----------------
@check("L5 hostile sessions: a clean answer, never a crash and never 'success' from nothing")
def _():
    rng = random.Random(5)
    junk = [None, 5, "x", [], {}, float("nan"), float("inf"), -3, 10 ** 400, True, [1], {"a": 1}]
    for _ in range(3000):
        ex = {"weight_lbs": rng.choice(junk + [135]), "rpe": rng.choice(junk + [8]), "struggled": rng.choice(junk + [True, False]),
              "prescribed": rng.choice(junk + [{"sets": rng.choice(junk + [3]), "reps": rng.choice(junk + [8]), "target_rpe": rng.choice(junk + [8])}]),
              "set_details": rng.choice(junk + [[rng.choice(junk + [{"reps": rng.choice(junk + [8])}]) for _ in range(rng.randint(0, 4))]])}
        ev = R.evaluate_session(ex)
        assert ev["status"] in ("success", "neutral", "struggle", "unknown"), ev
        if ev["status"] == "success":
            assert ev["sets_done"] >= 1 and ev["reps_hit"] is True
    assert R.evaluate_session(None)["status"] == "unknown" and R.evaluate_session("x")["status"] == "unknown"


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)