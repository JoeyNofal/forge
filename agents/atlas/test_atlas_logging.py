"""
ATLAS increment (b), Part 1 — L1, L2, L4, L5 tests for atlas_logging.py
(the normalizers + locked writers). No model, no keys, no cost. Uses TEMP
files only: your real fitness.json is never touched.

Run from the repo root:  python -m agents.atlas.test_atlas_logging
(L3 — real end-to-end — comes after extraction is built in Part 3.)
"""
import json
import os
import re
import shutil
import tempfile
import threading
import time

from agents.atlas import atlas_logging as L
from agents.atlas import atlas_tools as t

SRC = os.path.join(t._REPO_ROOT, "agents", "atlas", "atlas_logging.py")
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


def fresh_path():
    d = tempfile.mkdtemp(prefix="atlas_log_test_")
    os.environ["FITNESS_DATA_PATH"] = os.path.join(d, "fitness.json")
    return os.environ["FITNESS_DATA_PATH"], d


def write_raw(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


def read(path):
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def raw_bytes(path):
    with open(path, "rb") as f:
        return f.read()


def raises(fn, exc):
    try:
        fn()
    except exc:
        return True
    return False


def swim(**kw):
    d = {"total_distance_yards": 2000, "duration_minutes": 45, "strokes": ["freestyle"]}
    d.update(kw)
    return d


# ───────────────────────── L1 — STATIC ─────────────────────────

with open(SRC, encoding="utf-8") as _f:
    _src = _f.read()


@check("L1 writes go through the locked helper; no raw open()/json.dump in this file")
def _():
    assert "update_json" in _src
    assert not re.search(r"\bopen\(", _src) and "json.dump" not in _src


@check("L1 no bare 'except:', no secrets, no old-system path, no substring keyword tests")
def _():
    assert not re.search(r"except\s*:", _src)
    assert "NEXUS SYSTEM" not in _src and "API_KEY" not in _src
    assert "contains_keyword" in _src   # word-boundary matching (Lesson #6)


@check("L1 atlas_tools.py is still read-only (all writing lives in atlas_logging.py)")
def _():
    with open(t.__file__, encoding="utf-8") as f:
        tools_src = f.read()
    assert "def log_" not in tools_src and "update_json" not in tools_src


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 swim: strings become numbers, strokes lowercased/split, sets tidied, difficulty clamped")
def _():
    w = L.normalize_swim({"total_distance_yards": "2000", "duration_minutes": "45",
                          "strokes": "Freestyle, BREASTSTROKE", "sets": ["4x100", {"description": "200 easy"}, ""],
                          "difficulty": 15})
    assert w["total_distance_yards"] == 2000 and w["duration_minutes"] == 45
    assert w["strokes"] == ["freestyle", "breaststroke"]
    assert w["sets"] == ["4x100", "200 easy"]
    assert w["difficulty_1_to_10"] == 10
    assert L.normalize_swim(swim(difficulty=0))["difficulty_1_to_10"] is None   # unknown stays unknown, never an invented 5


@check("L2 unstated difficulty/duration/distance are saved as null (never 0 or 5) and the readers say 'unknown'")
def _():
    path, d = fresh_path()
    L.log_gym({"exercises": ["squat"]})
    L.log_swim({"duration_minutes": 30})
    L.log_swim({"total_distance_yards": 500})
    g, s1, s2 = read(path)["workouts"]
    assert g["difficulty_1_to_10"] is None and g["duration_minutes"] is None
    assert s1["total_distance_yards"] is None and s1["duration_minutes"] == 30 and s1["difficulty_1_to_10"] is None
    assert s2["duration_minutes"] is None and s2["total_distance_yards"] == 500
    assert "unknown min" in t.get_gym_history() and "Difficulty: unknown/10" in t.get_gym_history()
    assert "0 min" not in t.get_gym_history()
    msg = L.log_swim({"duration_minutes": 20})
    assert "distance not stated" in msg and "20 min" in msg
    shutil.rmtree(d)


@check("L2 dates: future and garbage dates become today, a real past date is kept")
def _():
    today = time.strftime("%Y-%m-%d")
    assert L.normalize_swim(swim(date="2999-01-01"))["date"] == today
    assert L.normalize_swim(swim(date="last tuesday"))["date"] == today
    assert L.normalize_swim(swim(date=None))["date"] == today
    assert L.normalize_swim(swim(date="2026-01-05"))["date"] == "2026-01-05"


@check("L2 swim rejects: not-a-dict, empty, no distance AND no duration, negative, NaN, absurd")
def _():
    for bad in (None, [], "swam", 5, {}, {"strokes": ["free"]}, swim(total_distance_yards=-5),
                swim(total_distance_yards="nan"), swim(total_distance_yards=10**7), swim(duration_minutes=99999)):
        assert raises(lambda b=bad: L.normalize_swim(b), ValueError), bad
    L.normalize_swim({"duration_minutes": 30})       # duration alone is enough
    L.normalize_swim({"total_distance_yards": 500})  # distance alone is enough


@check("L2 gym: plain-string exercises become objects, junk dropped, unknowns stay None (never 0)")
def _():
    g = L.normalize_gym({"exercises": ["bench press", {"name": "squat", "sets": 3, "reps": "5", "weight_lbs": "x"},
                                       7, None, {"name": ""}, {"name": "row", "sets": -2}]})
    assert [e["name"] for e in g["exercises"]] == ["bench press", "squat", "row"]
    assert g["exercises"][0] == {"name": "bench press", "sets": None, "reps": None, "weight_lbs": None, "notes": ""}
    assert g["exercises"][1]["sets"] == 3 and g["exercises"][1]["reps"] == 5 and g["exercises"][1]["weight_lbs"] is None
    assert g["exercises"][2]["sets"] is None
    for bad in (None, {}, {"exercises": []}, {"exercises": "bench"}, {"exercises": [None, 3]}):
        assert raises(lambda b=bad: L.normalize_gym(b), ValueError), bad


@check("L2 injury: body part lowercased, bad severity -> mild, needs a body part or description")
def _():
    i = L.normalize_injury({"body_part": "Left SHOULDER", "severity": "terrible"})
    assert i["body_part"] == "left shoulder" and i["severity"] == "mild" and i["description"] == "left shoulder"
    assert L.normalize_injury({"description": "sore", "severity": "Severe"})["severity"] == "severe"
    for bad in (None, {}, {"body_part": "  "}, "shoulder"):
        assert raises(lambda b=bad: L.normalize_injury(b), ValueError), bad


@check("L2 saved records have the exact expected keys and the existing readers can read them")
def _():
    path, d = fresh_path()
    L.log_swim(swim(strokes=["im"]))
    L.log_gym({"exercises": [{"name": "bench press", "sets": 3, "reps": 8, "weight_lbs": 135}]})
    L.log_injury({"body_part": "knee", "description": "sore left knee", "severity": "moderate"})
    data = read(path)
    sw, gy = data["workouts"]
    assert sw["type"] == "swim" and gy["type"] == "gym"
    for k in ("id", "logged_at", "date", "difficulty_1_to_10", "form_notes", "weaknesses", "coach_notes"):
        assert k in sw and k in gy, k
    inj = data["injuries"][-1]
    assert inj["status"] == "active" and inj["date_logged"] and inj["id"] and inj["severity"] == "moderate"
    assert "2,000 total yards" in t.get_swim_history()
    assert "bench press" in t.get_gym_history()
    assert "sore left knee" in t.get_injury_history()
    assert "sore left knee" in t.get_data_summary_for_llm()
    shutil.rmtree(d)


@check("L2 logging keeps everything already in the file (profile, tracker-shaped workouts, other keys)")
def _():
    path, d = fresh_path()
    tracker = {"type": "gym", "date": "2026-02-02", "exercises": ["plain string"], "weaknesses": ["a", "b"]}
    write_raw(path, {"profile": {"name": "Joey"}, "workouts": [tracker], "injuries": [], "extra": {"keep": 1}})
    L.log_swim(swim())
    data = read(path)
    assert data["profile"] == {"name": "Joey"} and data["extra"] == {"keep": 1}
    assert data["workouts"][0] == tracker and len(data["workouts"]) == 2
    shutil.rmtree(d)


@check("L2 a missing file is created automatically on the first log")
def _():
    path, d = fresh_path()
    assert not os.path.exists(path)
    L.log_swim(swim())
    assert len(read(path)["workouts"]) == 1
    shutil.rmtree(d)


@check("L2 injury update: 'my shoulder is better now' changes exactly the one matching open injury")
def _():
    path, d = fresh_path()
    L.log_injury({"body_part": "shoulder", "description": "left shoulder pinch"})
    L.log_injury({"body_part": "knee", "description": "sore knee"})
    ok, msg = L.update_injury_status({"body_part": "shoulder", "new_status": "recovering", "notes": "feeling better"})
    assert ok and "active → recovering" in msg, msg
    inj = {i["body_part"]: i for i in read(path)["injuries"] if i.get("body_part")}
    assert inj["shoulder"]["status"] == "recovering" and inj["shoulder"]["status_updated"]
    assert "feeling better" in inj["shoulder"]["notes"]
    assert inj["knee"]["status"] == "active"                       # untouched
    ok, msg = L.update_injury_status({"body_part": "shoulder", "new_status": "resolved"})
    assert ok and "recovering → resolved" in msg
    assert "Status: resolved" in t.get_injury_history()
    shutil.rmtree(d)


@check("L2 injury update never guesses: no match / several matches / already that status / resolved ones change NOTHING")
def _():
    path, d = fresh_path()
    L.log_injury({"body_part": "left shoulder", "description": "left shoulder pinch"})
    L.log_injury({"body_part": "right shoulder", "description": "right shoulder ache"})
    before = raw_bytes(path)
    ok, msg = L.update_injury_status({"body_part": "shoulder", "new_status": "resolved"})
    assert not ok and "More than one" in msg
    ok, msg = L.update_injury_status({"body_part": "wrist", "new_status": "resolved"})
    assert not ok and "No open injury" in msg
    ok, msg = L.update_injury_status({"body_part": "left shoulder", "new_status": "active"})
    assert not ok and "already active" in msg
    assert raw_bytes(path) == before
    L.update_injury_status({"body_part": "left shoulder", "new_status": "resolved"})
    ok, msg = L.update_injury_status({"body_part": "left shoulder", "new_status": "recovering"})
    assert not ok and "No open injury" in msg                      # a resolved injury is not reopened
    shutil.rmtree(d)


@check("L2 injury matching is whole-word ('arm' never matches 'forearm'); the 'none' placeholder is never matched")
def _():
    path, d = fresh_path()
    L.log_injury({"body_part": "forearm", "description": "forearm strain"})
    ok, msg = L.update_injury_status({"body_part": "arm", "new_status": "resolved"})
    assert not ok and "No open injury" in msg
    ok, msg = L.update_injury_status({"body_part": "injuries", "new_status": "resolved"})   # placeholder text
    assert not ok
    assert [i for i in read(path)["injuries"] if i.get("status") == "none"]                 # placeholder intact
    shutil.rmtree(d)


@check("L2 bad injury-update input is rejected (no body part, bad status, not a dict)")
def _():
    for bad in (None, {}, {"body_part": "knee"}, {"body_part": "knee", "new_status": "healed"},
                {"new_status": "resolved"}, "x"):
        assert raises(lambda b=bad: L.normalize_injury_update(b), ValueError), bad


@check("L2 updating when the file doesn't exist yet creates it and reports 'no open injury'")
def _():
    path, d = fresh_path()
    ok, msg = L.update_injury_status({"body_part": "knee", "new_status": "resolved"})
    assert not ok and "No open injury" in msg and os.path.exists(path)
    shutil.rmtree(d)


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 simultaneous swim/gym/injury logs: exactly 20 records, unique ids, valid JSON, zero errors")
def _():
    path, d = fresh_path()
    errors = []

    def go(n):
        try:
            if n % 3 == 0:
                L.log_swim(swim(total_distance_yards=100 + n))
            elif n % 3 == 1:
                L.log_gym({"exercises": [{"name": f"ex{n}", "sets": 3}]})
            else:
                L.log_injury({"body_part": f"part{n}", "description": f"injury {n}"})
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    data = read(path)
    real_inj = [i for i in data["injuries"] if i.get("status") != "none"]
    assert not errors, errors
    assert len(data["workouts"]) + len(real_inj) == 20
    ids = [w["id"] for w in data["workouts"]] + [i["id"] for i in real_inj]
    assert len(set(ids)) == 20
    shutil.rmtree(d)


@check("L4 20 threads all marking the SAME injury resolved: exactly one succeeds, 19 are told 'nothing changed'")
def _():
    path, d = fresh_path()
    L.log_injury({"body_part": "shoulder", "description": "shoulder pinch"})
    results = []
    lock = threading.Lock()

    def go():
        r = L.update_injury_status({"body_part": "shoulder", "new_status": "resolved"})
        with lock:
            results.append(r)

    threads = [threading.Thread(target=go) for _ in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert sum(1 for ok, _ in results if ok) == 1, results
    assert len(results) == 20
    shutil.rmtree(d)


@check("L4 200 sequential logs: all present, file stays valid, stays fast")
def _():
    path, d = fresh_path()
    start = time.time()
    for n in range(200):
        L.log_swim(swim(total_distance_yards=100 + n))
    assert len(read(path)["workouts"]) == 200
    assert time.time() - start < 30, time.time() - start
    shutil.rmtree(d)


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 corrupt JSON: logging fails LOUDLY and the file is left exactly as it was")
def _():
    path, d = fresh_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"workouts": [ {"broken"')
    before = raw_bytes(path)
    assert raises(lambda: L.log_swim(swim()), Exception)
    assert raw_bytes(path) == before
    assert raises(lambda: L.update_injury_status({"body_part": "knee", "new_status": "resolved"}), Exception)
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L5 wrong-shape file (top-level list, or 'workouts' not a list): fails loudly, never overwrites")
def _():
    path, d = fresh_path()
    write_raw(path, [1, 2, 3])
    before = raw_bytes(path)
    assert raises(lambda: L.log_swim(swim()), RuntimeError)
    assert raw_bytes(path) == before
    write_raw(path, {"workouts": "oops", "injuries": []})
    before = raw_bytes(path)
    assert raises(lambda: L.log_swim(swim()), RuntimeError)
    assert raw_bytes(path) == before
    shutil.rmtree(d)


@check("L5 missing 'workouts'/'injuries' keys or null values are created cleanly")
def _():
    path, d = fresh_path()
    write_raw(path, {"profile": {}})
    L.log_swim(swim()); L.log_injury({"body_part": "hip"})
    write_raw(path, {"workouts": None, "injuries": None})
    L.log_gym({"exercises": ["squat"]})
    assert len(read(path)["workouts"]) == 1
    shutil.rmtree(d)


@check("L5 50,000-character text is cut to 1,000; unicode and emoji survive intact")
def _():
    path, d = fresh_path()
    L.log_swim(swim(form_notes="x" * 50000, coach_notes="Schwimmen 泳ぐ 🏊‍♂️ résumé"))
    L.log_injury({"body_part": "épaule 🤕", "description": "y" * 50000})
    data = read(path)
    w = data["workouts"][0]
    assert len(w["form_notes"]) == 1000 and w["coach_notes"] == "Schwimmen 泳ぐ 🏊‍♂️ résumé"
    assert len(data["injuries"][-1]["description"]) == 1000 and data["injuries"][-1]["body_part"] == "épaule 🤕"
    shutil.rmtree(d)


@check("L5 hostile field types (bool, nested dicts, huge lists, regex characters) never crash or corrupt")
def _():
    path, d = fresh_path()
    w = L.normalize_swim({"total_distance_yards": 900, "duration_minutes": False, "strokes": {"a": 1},
                          "sets": ["s"] * 500, "difficulty": [], "form_notes": {"x": 1}, "weaknesses": None})
    assert w["duration_minutes"] is None and w["strokes"] == [] and len(w["sets"]) == 30
    assert isinstance(w["form_notes"], str)
    L.log_injury({"body_part": "knee (left) [ACL]+*?", "description": "regex chars"})
    ok, msg = L.update_injury_status({"body_part": "(left) [ACL]+*?", "new_status": "resolved"})
    assert isinstance(ok, bool)      # no regex explosion either way
    ok, msg = L.update_injury_status({"body_part": "knee", "new_status": "resolved"})
    assert ok or "No open injury" in msg
    shutil.rmtree(d)


@check("L5 the update path handles junk injury entries (non-dicts, missing fields) without crashing")
def _():
    path, d = fresh_path()
    write_raw(path, {"workouts": [], "injuries": [None, "text", 5, {"status": "active"},
                                                  {"description": None, "status": "active"},
                                                  {"body_part": "knee", "description": "knee pain", "status": "active"}]})
    ok, msg = L.update_injury_status({"body_part": "knee", "new_status": "resolved"})
    assert ok, msg
    assert read(path)["injuries"][:5] == [None, "text", 5, {"status": "active"}, {"description": None, "status": "active"}]
    shutil.rmtree(d)


passed = sum(1 for _, ok, _ in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
if passed != len(_results):
    raise SystemExit(1)