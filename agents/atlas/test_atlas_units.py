"""
ATLAS UNITS FIX — L1, L2, L4, L5 tests. The fix: the model reports a weight or
distance EXACTLY as Joey said it (plus a unit only if he wrote one); PYTHON does
any conversion; a missing unit is taken as pounds/yards and flagged
"(unit assumed)" on the proposal (never saved). Fixes the real L3 finding where
"at 50" became 110.23 lbs because the model assumed kg and multiplied itself.

The local model is FAKED (no Ollama, no keys, no cost). TEMP files only.

Run from the repo root:  python -m agents.atlas.test_atlas_units
"""
import json
import os
import shutil
import tempfile
import threading

_QUEUE_DIR = tempfile.mkdtemp(prefix="atlas_units_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.atlas import atlas_actions as A
from agents.atlas import atlas_extract as X
from agents.atlas import atlas_logging as L
from agents.atlas import atlas_tools as t
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
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


def fresh():
    d = tempfile.mkdtemp(prefix="atlas_units_test_")
    os.environ["FITNESS_DATA_PATH"] = os.path.join(d, "fitness.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    return os.environ["FITNESS_DATA_PATH"], d


def queue_actions():
    if not os.path.exists(QUEUE):
        return []
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f)["actions"]


def read_json(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def gym(**kw):
    """One-exercise gym report; kw goes on the exercise."""
    return {"exercises": [dict({"name": "press", "sets": 3, "reps": 10}, **kw)]}


def lbs(g):
    return g["exercises"][0]["weight_lbs"]


def swim(**kw):
    return dict({"duration_minutes": 30}, **kw)


def read_src(name):
    with open(os.path.join(t._REPO_ROOT, "agents", "atlas", name), encoding="utf-8") as f:
        return f.read()


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 the prompts no longer ask the model to convert or do arithmetic; they ask for the number as stated plus a unit only if written")
def _():
    p = X.WORKOUT_PROMPT
    assert "1 kg = 2.205" not in p and "1 m = 1.094" not in p and "weight_lbs" not in p
    assert '"weight_unit"' in p and '"distance_unit"' in p and "NEVER convert" in p
    assert '"exercises": [{"name": "bench press"' in p and "OBJECTS" in p


@check("L1 unit arithmetic lives ONLY in atlas_logging.py (Python), never in the extraction module")
def _():
    log_src, ex_src = read_src("atlas_logging.py"), read_src("atlas_extract.py")
    assert "2.20462" in log_src and "1.09361" in log_src
    assert "2.20462" not in ex_src and "1.09361" not in ex_src and "* 2.2" not in ex_src


# ───────────────────────── L2 — SMOKE: GYM WEIGHTS ─────────────────────────

@check("L2 no unit stated: taken as pounds and flagged (the exact 'at 50' bug: never 110.23)")
def _():
    g = L.normalize_gym(gym(weight=50))
    assert lbs(g) == 50 and g["units_assumed"] == ["press"], g
    g2 = L.normalize_gym(gym(weight="50", weight_unit=""))
    assert lbs(g2) == 50 and g2["units_assumed"] == ["press"]


@check("L2 pounds stated (any spelling): kept as-is, NOT flagged")
def _():
    for unit in ("lbs", "LB", " Pounds ", "lb"):
        g = L.normalize_gym(gym(weight=50, weight_unit=unit))
        assert lbs(g) == 50 and "units_assumed" not in g, unit
    assert lbs(L.normalize_gym(gym(weight=22.5, weight_unit="lbs"))) == 22.5


@check("L2 kg stated: PYTHON converts (50 kg -> 110.23, 100 kilos -> 220.46), NOT flagged")
def _():
    g = L.normalize_gym(gym(weight=50, weight_unit="kg"))
    assert lbs(g) == 110.23 and "units_assumed" not in g, g
    assert lbs(L.normalize_gym(gym(weight=100, weight_unit="Kilos"))) == 220.46


@check("L2 the older weight_lbs key (already pounds) still works unflagged; the new key wins if both appear")
def _():
    g = L.normalize_gym(gym(weight_lbs=135))
    assert lbs(g) == 135 and "units_assumed" not in g
    g2 = L.normalize_gym(gym(weight=50, weight_unit="kg", weight_lbs=999))
    assert lbs(g2) == 110.23


@check("L2 no weight / bodyweight 0 stays unknown or 0, never flagged, never invented")
def _():
    for kw in ({}, {"weight": None}, {"weight": ""}, {"weight": None, "weight_unit": "kg"}):
        g = L.normalize_gym(gym(**kw))
        assert lbs(g) is None and "units_assumed" not in g, kw
    g0 = L.normalize_gym(gym(weight=0))
    assert lbs(g0) == 0 and "units_assumed" not in g0


@check("L2 an unknown unit word ('stone') counts as 'no unit stated': pounds, flagged")
def _():
    g = L.normalize_gym(gym(weight=10, weight_unit="stone"))
    assert lbs(g) == 10 and g["units_assumed"] == ["press"]


@check("L2 two exercises: only the unitless one is flagged")
def _():
    g = L.normalize_gym({"exercises": [
        {"name": "bench", "weight": 135, "weight_unit": "lbs"},
        {"name": "curl", "weight": 30},
        {"name": "squat"},
    ]})
    assert g["units_assumed"] == ["curl"]
    assert [e["weight_lbs"] for e in g["exercises"]] == [135, 30, None]


@check("L2 a converted weight that is out of range becomes unknown, not a huge number")
def _():
    g = L.normalize_gym(gym(weight=3000, weight_unit="kg"))    # 6,613 lbs > the 5,000 cap
    assert lbs(g) is None and "units_assumed" not in g


# ───────────────────────── L2 — SMOKE: SWIM DISTANCES ─────────────────────────

@check("L2 swim: meters are converted by PYTHON; yards kept; no unit -> yards, flagged")
def _():
    m = L.normalize_swim(swim(total_distance=1500, distance_unit="meters"))
    assert m["total_distance_yards"] == round(1500 * 1.09361, 2) and 1640 < m["total_distance_yards"] < 1641
    assert "units_assumed" not in m
    assert L.normalize_swim(swim(total_distance=1000, distance_unit="m"))["total_distance_yards"] == round(1000 * 1.09361, 2)
    y = L.normalize_swim(swim(total_distance=1500, distance_unit="Yards"))
    assert y["total_distance_yards"] == 1500 and "units_assumed" not in y
    u = L.normalize_swim(swim(total_distance=1500))
    assert u["total_distance_yards"] == 1500 and u["units_assumed"] == ["distance"], u


@check("L2 swim: the older total_distance_yards key works unflagged and wins if both appear; duration-only is fine")
def _():
    s = L.normalize_swim(swim(total_distance_yards=2000, total_distance=5))
    assert s["total_distance_yards"] == 2000 and "units_assumed" not in s
    d = L.normalize_swim({"duration_minutes": 30})
    assert d["total_distance_yards"] is None and "units_assumed" not in d


@check("L2 swim: out-of-range distances are refused (negative, huge, huge once converted)")
def _():
    assert raises(lambda: L.normalize_swim(swim(total_distance=-5)), ValueError)
    assert raises(lambda: L.normalize_swim(swim(total_distance=10**8)), ValueError)
    assert raises(lambda: L.normalize_swim(swim(total_distance=95000, distance_unit="meters")), ValueError)


# ───────────────────────── L2 — SMOKE: WHAT JOEY SEES ─────────────────────────

@check("L2 the proposal shows the weights, and '(unit assumed)' only on the unitless one")
def _():
    path, d = fresh()
    _, msg = A.propose_gym({"exercises": [
        {"name": "bench", "weight": 135, "weight_unit": "lbs"},
        {"name": "curl", "weight": 30},
    ]})
    assert "2 exercise(s) (bench, curl)" in msg
    assert "bench 135 lbs" in msg and "curl 30 lbs (unit assumed)" in msg
    assert "bench 135 lbs (unit assumed)" not in msg
    shutil.rmtree(d)


@check("L2 a kg weight shows the converted pounds; no weights means no 'weights:' text at all")
def _():
    path, d = fresh()
    _, msg = A.propose_gym(gym(weight=50, weight_unit="kg"))
    assert "press 110.23 lbs" in msg and "unit assumed" not in msg
    _, none_msg = A.propose_gym({"exercises": ["squat"]})
    assert "weights:" not in none_msg and "1 exercise(s) (squat)" in none_msg
    shutil.rmtree(d)


@check("L2 swim proposals: '1500 yards (unit assumed)' when unitless; clean when a unit was stated")
def _():
    path, d = fresh()
    _, a = A.propose_swim(swim(total_distance=1500))
    assert "1500 yards (unit assumed)" in a
    _, b = A.propose_swim(swim(total_distance=1500, distance_unit="meters"))
    assert "1640" in b and "unit assumed" not in b
    _, c = A.propose_swim({"total_distance_yards": 2000, "duration_minutes": 45})
    assert "2000 yards," in c and "unit assumed" not in c
    shutil.rmtree(d)


@check("L2 approval saves the pounds value and NEVER saves the 'units_assumed' note (gym and swim; via the gate and directly)")
def _():
    path, d = fresh()
    aid, _ = A.propose_gym(gym(weight=50))
    assert queue_actions()[0]["details"]["units_assumed"] == ["press"]      # on the proposal
    assert "logged" in A.approve_and_execute(aid)
    sid, _ = A.propose_swim(swim(total_distance=1500))
    assert "logged" in A.approve_and_execute(sid).lower()
    L.log_gym(gym(weight=60))                                              # direct call, no gate
    L.log_swim(swim(total_distance=500))
    workouts = read_json(path)["workouts"]
    assert len(workouts) == 4 and all("units_assumed" not in w for w in workouts), workouts
    assert workouts[0]["exercises"][0]["weight_lbs"] == 50
    assert workouts[1]["total_distance_yards"] == 1500 and workouts[2]["exercises"][0]["weight_lbs"] == 60
    shutil.rmtree(d)


# ───────────────────────── L2 — END TO END WITH A FAKED MODEL ─────────────────────────

MSG = "I did chest today. Bench press 3 sets of 8 at 135 lbs, and incline dumbbell press 3x10 at 50."


def fake_model(payload):
    X.complete_ollama_json = lambda system_prompt, user_text: json.dumps(payload)


@check("L2 end to end: the model says 50 with no unit -> queued as 50 lbs, flagged; it can no longer smuggle in 110.23")
def _():
    path, d = fresh()
    fake_model({"kind": "gym", "date": "", "exercises": [
        {"name": "bench press", "sets": 3, "reps": 8, "weight": 135, "weight_unit": "lbs"},
        {"name": "incline dumbbell press", "sets": 3, "reps": 10, "weight": 50, "weight_unit": ""},
    ]})
    notes = X.extract_and_propose(MSG)
    ex = queue_actions()[0]["details"]["exercises"]
    assert [e["weight_lbs"] for e in ex] == [135, 50], ex
    assert "incline dumbbell press 50 lbs (unit assumed)" in notes[0] and "bench press 135 lbs" in notes[0]
    shutil.rmtree(d)


@check("L2 end to end: the model reports kg -> Python converts exactly once, shown plainly")
def _():
    path, d = fresh()
    fake_model({"kind": "gym", "exercises": [{"name": "row", "sets": 3, "reps": 10, "weight": 50, "weight_unit": "kg"}]})
    notes = X.extract_and_propose("I did back today, rows 3x10 at 50 kg")
    assert queue_actions()[0]["details"]["exercises"][0]["weight_lbs"] == 110.23
    assert "row 110.23 lbs" in notes[0] and "unit assumed" not in notes[0]
    shutil.rmtree(d)


@check("L2 end to end: swim in meters -> converted by Python on the proposal")
def _():
    path, d = fresh()
    fake_model({"kind": "swim", "total_distance": 1500, "distance_unit": "meters", "duration_minutes": 30})
    notes = X.extract_and_propose("I swam 1500 meters in 30 minutes this morning")
    assert queue_actions()[0]["details"]["total_distance_yards"] == round(1500 * 1.09361, 2)
    assert "unit assumed" not in notes[0]
    shutil.rmtree(d)


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 threads x 50 conversions at once: every result exactly right, no cross-talk")
def _():
    bad, lock = [], threading.Lock()

    def worker(i):
        for n in range(50):
            w = i + 1 + n
            unitless = L.normalize_gym(gym(weight=w))
            kg = L.normalize_gym(gym(weight=w, weight_unit="kg"))
            ok = (lbs(unitless) == w and unitless.get("units_assumed") == ["press"]
                  and lbs(kg) == round(w * 2.20462, 2) and "units_assumed" not in kg)
            if not ok:
                with lock:
                    bad.append((i, n))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert bad == [], bad[:3]


@check("L4 20 simultaneous proposals with unitless weights: all 20 queued, every one flagged and intact")
def _():
    path, d = fresh()
    results, lock = [], threading.Lock()

    def worker(i):
        aid, msg = A.propose_gym(gym(weight=i + 1))
        with lock:
            results.append((aid, msg))

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(20)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    q = queue_actions()
    assert len(q) == 20 and len(set(a["id"] for a in q)) == 20
    assert all(a["details"]["units_assumed"] == ["press"] for a in q)
    assert sorted(a["details"]["exercises"][0]["weight_lbs"] for a in q) == list(range(1, 21))
    assert all("(unit assumed)" in m for _, m in results)
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 junk weights never crash, never invent a number, never flag: words, nan, inf, negatives, huge, booleans, lists, dicts")
def _():
    for w in ("heavy", "nan", "inf", "-inf", "1e999", -5, 10**9, True, False, [], {}, [135], {"a": 1}, "50 lbs"):
        g = L.normalize_gym(gym(weight=w))
        assert lbs(g) is None and "units_assumed" not in g, (w, g)


@check("L5 junk unit words never crash: None, numbers, lists, dicts, 50,000 characters, unicode")
def _():
    for u in (None, 123, ["kg"], {"a": 1}, "x" * 50000, "ｋｇ", "килограмм", "🏋️"):
        g = L.normalize_gym(gym(weight=50, weight_unit=u))
        assert lbs(g) is not None, u
    assert lbs(L.normalize_gym(gym(weight=50, weight_unit="x" * 50000))) == 50


@check("L5 junk swim distances never crash or invent a number; NaN / infinity are refused loudly (same as the older key)")
def _():
    for v in ("far", [], True, {}, None, ""):
        s = L.normalize_swim(swim(total_distance=v))
        assert s["total_distance_yards"] is None and "units_assumed" not in s, v
    for v in ("nan", "inf", float("nan"), float("inf")):
        assert raises(lambda: L.normalize_swim(swim(total_distance=v)), ValueError), v
    assert raises(lambda: L.normalize_swim({"total_distance": "far"}), ValueError)      # nothing usable at all


@check("L5 500 exercises of mixed junk: capped at 30, no crash, flags only name kept exercises")
def _():
    exs = [{"name": f"e{i}", "weight": i, "weight_unit": ("kg" if i % 2 else "")} for i in range(500)]
    g = L.normalize_gym({"exercises": exs})
    assert len(g["exercises"]) == 30
    kept = {e["name"] for e in g["exercises"]}
    assert set(g["units_assumed"]) <= kept
    assert all(("units_assumed" in g and e["name"] in g["units_assumed"]) == (i % 2 == 0 and i != 0)
               for i, e in enumerate(g["exercises"]))


@check("L5 describe never crashes on hand-damaged details (units_assumed or weights of the wrong type)")
def _():
    base = {"date": "2026-01-01", "duration_minutes": None, "difficulty_1_to_10": None}
    for d_ in (dict(base, exercises=[{"name": "x", "weight_lbs": 5}], units_assumed="x"),
               dict(base, exercises=[{"name": "x", "weight_lbs": 5}], units_assumed=[1, None]),
               dict(base, exercises=["x"], units_assumed=["x"]),
               dict(base, exercises=[{"weight_lbs": 5}]),
               dict(base, exercises=5), dict(base, exercises=None)):
        assert isinstance(A.describe("log_gym", d_), str)
    assert isinstance(A.describe("log_swim", {"total_distance_yards": 5, "duration_minutes": 1,
                                              "difficulty_1_to_10": None, "date": "x", "units_assumed": 5}), str)


# ───────────────────────── THE MODEL-INVENTED-UNIT GUARD ─────────────────────────

def one_gym(message, weight, unit):
    path, d = fresh()
    fake_model({"kind": "gym", "exercises": [{"name": "squat", "sets": 5, "reps": 5, "weight": weight, "weight_unit": unit}]})
    notes = X.extract_and_propose(message)
    details = queue_actions()[0]["details"]
    shutil.rmtree(d)
    return details, notes[0]


def one_swim(message, distance, unit):
    path, d = fresh()
    fake_model({"kind": "swim", "total_distance": distance, "distance_unit": unit, "duration_minutes": 30})
    notes = X.extract_and_propose(message)
    details = queue_actions()[0]["details"]
    shutil.rmtree(d)
    return details, notes[0]


@check("L2 the real L3 finding: Joey gave NO unit, the model copied 'lbs' from the example -> still flagged '(unit assumed)'")
def _():
    details, note = one_gym("I did legs today, squat 5x5 at 225", 225, "lbs")
    assert details["exercises"][0]["weight_lbs"] == 225 and details["units_assumed"] == ["squat"]
    assert "squat 225 lbs (unit assumed)" in note


@check("L2 the dangerous mirror case: Joey gave NO unit, the model guessed 'kg' -> NOT converted (never 496.04)")
def _():
    details, note = one_gym("I did legs today, squat 5x5 at 225", 225, "kg")
    assert details["exercises"][0]["weight_lbs"] == 225 and details["units_assumed"] == ["squat"], details
    assert "unit assumed" in note


@check("L2 Joey DID write the unit: the model's 'kg' is trusted and converted; attached '100kg' and '135lbs' count too")
def _():
    d1, n1 = one_gym("I did legs today, squat 5x5 at 100 kg", 100, "kg")
    assert d1["exercises"][0]["weight_lbs"] == 220.46 and "units_assumed" not in d1 and "unit assumed" not in n1
    d2, _ = one_gym("I did legs today, squat 5x5 at 100kg", 100, "kg")
    assert d2["exercises"][0]["weight_lbs"] == 220.46 and "units_assumed" not in d2
    d3, _ = one_gym("I did legs today, squat 5x5 at 135lbs", 135, "lbs")
    assert d3["exercises"][0]["weight_lbs"] == 135 and "units_assumed" not in d3
    d4, _ = one_gym("I did legs today, squat 5x5 at 135 pounds", 135, "pounds")
    assert "units_assumed" not in d4


@check("L2 swim: a guessed 'meters' is ignored when Joey wrote none ('30 minutes' and \"I'm\" never count as meters)")
def _():
    d, note = one_swim("I swam 1500 in 30 minutes this morning, I'm tired", 1500, "meters")
    assert d["total_distance_yards"] == 1500 and d["units_assumed"] == ["distance"], d
    assert "1500 yards (unit assumed)" in note


@check("L2 swim: '1500m' and '1500 meters' are real meters and ARE converted; a wrong guess of 'meters' for stated yards is ignored")
def _():
    expected = round(1500 * 1.09361, 2)
    for msg in ("I swam 1500m in 30 minutes this morning", "I swam 1500 meters in 30 minutes this morning"):
        d, note = one_swim(msg, 1500, "meters")
        assert d["total_distance_yards"] == expected and "units_assumed" not in d, msg
    d2, _ = one_swim("I swam 1500 yards in 30 minutes this morning", 1500, "meters")
    assert d2["total_distance_yards"] == 1500       # not converted; (flagged only because the model's unit was dropped)


@check("L2 unit_family recognises the unit words and nothing else")
def _():
    assert L.unit_family(" KG ") == "kg" and L.unit_family("Pounds") == "lbs"
    assert L.unit_family("yds") == "yards" and L.unit_family("M") == "meters"
    for junk in ("stone", "", None, 123, {}, "x" * 50000):
        assert L.unit_family(junk) == "", junk


@check("L5 the guard never crashes on junk shapes: exercises not a list, non-dict items, numeric/None units, unknown kind")
def _():
    for data in ({"kind": "gym", "exercises": None}, {"kind": "gym", "exercises": "squat"},
                 {"kind": "gym", "exercises": [None, 5, "x", {"weight_unit": 5}, {"weight_unit": None}]},
                 {"kind": "swim", "distance_unit": 123}, {"kind": "swim"}, {"kind": "other"}, {}):
        X._enforce_stated_units(data, "I did legs today at 225")
    assert X._enforce_stated_units({"kind": "gym", "exercises": []}, "") is None


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)