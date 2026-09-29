"""
ATLAS increment (a), Part 1 — L1 (static) + L2 (smoke) tests for
prompt.py and atlas_tools.py. Uses TEMP files only: your real
fitness.json (and the FORGE data folder) are never touched.

Run from the repo root:  python -m agents.atlas.test_atlas_tools
"""
import json
import os
import re
import shutil
import tempfile
import threading

from agents.atlas import atlas_tools as t
from agents.atlas.prompt import ATLAS_PROMPT

REPO_ROOT = t._REPO_ROOT
TOOLS_SRC = os.path.join(REPO_ROOT, "agents", "atlas", "atlas_tools.py")

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
    """A brand-new temp data file path (file itself does NOT exist yet)."""
    d = tempfile.mkdtemp(prefix="atlas_test_")
    os.environ["FITNESS_DATA_PATH"] = os.path.join(d, "fitness.json")
    return os.environ["FITNESS_DATA_PATH"], d


def write_raw(path, obj):
    with open(path, "w", encoding="utf-8") as f:
        json.dump(obj, f)


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 prompt matches the old reference exactly (2,786 chars)")
def _():
    ref = os.path.join(REPO_ROOT, "reference", "agent_prompts.json")
    with open(ref, encoding="utf-8") as f:
        assert ATLAS_PROMPT == json.load(f)["atlas"]
    assert len(ATLAS_PROMPT) == 2786


@check("L1 no hardcoded old-system path or secret in atlas_tools.py")
def _():
    with open(TOOLS_SRC, encoding="utf-8") as f:
        src = f.read()
    assert not re.search(r"D:\\\\Projects\\\\NEXUS SYSTEM\\\\data", src)
    assert not re.search(r"(api[_-]?key|sk-ant|AIza)\s*=\s*['\"]", src, re.I)


@check("L1 every open() call passes encoding= (Windows cp1252 lesson)")
def _():
    with open(TOOLS_SRC, encoding="utf-8") as f:
        for n, line in enumerate(f, 1):
            if re.search(r"\bopen\(", line) and not line.strip().startswith("#"):
                assert "encoding=" in line, f"line {n}: {line.strip()}"


@check("L1 no bare 'except:' and no write-tools built yet")
def _():
    with open(TOOLS_SRC, encoding="utf-8") as f:
        src = f.read()
    assert not re.search(r"except\s*:", src)
    for name in ("def log_swim_workout", "def log_gym_workout", "def log_injury"):
        assert name not in src, f"{name} belongs to increment (b)"


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 default path is FORGE-only, never the old NEXUS SYSTEM file")
def _():
    os.environ.pop("FITNESS_DATA_PATH", None)
    p = t.get_data_path()
    assert "NEXUS SYSTEM" not in p
    assert p.endswith(os.path.join("data", "fitness.json"))


@check("L2 auto-create: missing file is created with valid starting structure")
def _():
    path, d = fresh_path()
    assert not os.path.exists(path)
    data = t.load_fitness_data()
    assert os.path.exists(path)
    for key in ("profile", "workouts", "body_metrics", "injuries", "plans"):
        assert key in data
    assert data["workouts"] == []
    assert not os.path.exists(path + ".tmp")
    shutil.rmtree(d)


@check("L2 empty data: every reader returns its clean 'nothing yet' message")
def _():
    path, d = fresh_path()
    assert t.get_recent_workouts() == "No workouts logged yet."
    assert t.get_swim_history() == "No swim workouts logged yet."
    assert t.get_gym_history() == "No gym workouts logged yet."
    assert t.get_injury_history() == "No injuries on record."
    assert "Total workouts logged: 0" in t.get_data_summary_for_llm()
    shutil.rmtree(d)


@check("L2 mixed real-world shapes (old ATLAS + Training tracker) never crash")
def _():
    path, d = fresh_path()
    write_raw(path, {
        "profile": {"name": "Joey", "notes": "test"},
        "workouts": [
            # old-ATLAS swim: weaknesses is a STRING
            {"id": "u1", "type": "swim", "date": "2026-03-01", "total_distance_yards": 2000,
             "duration_minutes": 60, "strokes": ["freestyle"], "sets": [{"description": "x", "distance_yards": 400}],
             "difficulty_1_to_10": 7, "weaknesses": "kick timing"},
            # tracker swim: weaknesses is a LIST, null duration
            {"id": "swim_1", "type": "swim", "date": "2026-03-05", "total_distance_yards": 1500,
             "duration_minutes": None, "strokes": ["breaststroke", "im"], "sets": [{"distance_yards": 100, "stroke": "free"}],
             "difficulty_1_to_10": 5, "weaknesses": ["pullout", "breathing"]},
            # swim with null distance
            {"id": "swim_2", "type": "swim", "date": "2026-03-06", "total_distance_yards": None},
            # gym with proper dict exercises
            {"id": "g1", "type": "gym", "date": "2026-03-02",
             "exercises": [{"name": "bench press", "sets": 3, "reps": 8, "weight_lbs": 135}],
             "duration_minutes": 50, "difficulty_1_to_10": 6},
            # gym with PLAIN-STRING exercises (the exact old Lesson #5 crash)
            {"id": "g2", "type": "gym", "date": "2026-03-03", "exercises": ["squat", "deadlift"], "duration_minutes": 40},
            # gym with junk inside exercises
            {"id": "g3", "type": "gym", "date": "2026-03-04", "exercises": [None, 5, {"nope": 1}, {"name": "row"}]},
            # MISSING date entirely (old code raised KeyError)
            {"id": "s3", "type": "swim", "total_distance_yards": 500},
            # unknown type
            {"id": "x", "type": "yoga", "date": "2026-03-07"},
            # not a dict at all
            "garbage", 42, None,
        ],
        "injuries": [
            {"description": "No injuries currently on file.", "status": "none"},
            {"date_logged": "2026-02-10T09:00:00", "description": "left shoulder strain", "status": "active"},
            {"status": "recovering"},          # missing description + date
            "junk",
        ],
    })
    recent = t.get_recent_workouts(20)
    assert "YOGA workout" in recent and "no date" in recent
    swim = t.get_swim_history()
    # 2000 + 1500 + 500 = 4000 yards over 4 swim entries (null counts as 0)
    assert "4 session(s), 4,000 total yards" in swim, swim
    assert "pullout, breathing" in swim and "['pullout'" not in swim
    assert "kick timing" in swim
    gym = t.get_gym_history()
    assert "squat, deadlift" in gym and "bench press" in gym and "row" in gym
    assert "3 session(s)" in gym
    inj = t.get_injury_history()
    assert "left shoulder strain" in inj and "2026-02-10" in inj
    assert "No injuries currently on file" not in inj
    summ = t.get_data_summary_for_llm()
    assert "Total workouts logged: 8" in summ and "Swim sessions: 4" in summ and "Gym sessions: 3" in summ
    shutil.rmtree(d)


@check("L2 missing top-level keys / wrong-typed keys don't crash readers")
def _():
    path, d = fresh_path()
    write_raw(path, {})
    assert t.get_recent_workouts() == "No workouts logged yet."
    assert t.get_injury_history() == "No injuries on record."
    assert "Total workouts logged: 0" in t.get_data_summary_for_llm()
    write_raw(path, {"workouts": "oops", "injuries": 7, "profile": ["x"]})
    assert "Total workouts logged: 0" in t.get_data_summary_for_llm()
    shutil.rmtree(d)


@check("L2 corrupt JSON fails LOUDLY with a specific error (not silently)")
def _():
    path, d = fresh_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"workouts": [')
    try:
        t.load_fitness_data()
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "malformed" in str(e)
    shutil.rmtree(d)


@check("L2 top-level JSON list fails loudly (wrong shape)")
def _():
    path, d = fresh_path()
    write_raw(path, [1, 2, 3])
    try:
        t.load_fitness_data()
        raise AssertionError("should have raised")
    except RuntimeError as e:
        assert "wrong shape" in str(e)
    shutil.rmtree(d)


@check("L2 mid-write read: file fixed during the retry window loads fine")
def _():
    path, d = fresh_path()
    with open(path, "w", encoding="utf-8") as f:
        f.write('{"workouts": [')

    def fix_soon():
        import time
        time.sleep(0.1)
        write_raw(path, {"workouts": [], "injuries": [], "profile": {}})
    th = threading.Thread(target=fix_soon)
    th.start()
    data = t.load_fitness_data()   # first read fails, retry (after 0.3s) succeeds
    th.join()
    assert data["workouts"] == []
    shutil.rmtree(d)


@check("L2 20 threads hitting a brand-new file at once: one clean file, zero errors")
def _():
    path, d = fresh_path()
    errors, created = [], []

    def worker():
        try:
            created.append(t.initialize_fitness_data())
            t.load_fitness_data()
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=worker) for _ in range(20)]
    for th in threads: th.start()
    for th in threads: th.join()
    assert not errors, errors
    assert created.count(True) == 1, created
    with open(path, encoding="utf-8") as f:
        assert json.load(f)["workouts"] == []
    assert not os.path.exists(path + ".tmp")
    shutil.rmtree(d)


@check("L2 reading never modifies an existing file (live-data safety)")
def _():
    path, d = fresh_path()
    write_raw(path, {"workouts": [{"type": "swim", "date": "2026-01-01", "total_distance_yards": 1000}]})
    with open(path, "rb") as f:
        before = f.read()
    t.get_recent_workouts(); t.get_swim_history(); t.get_gym_history()
    t.get_injury_history(); t.get_data_summary_for_llm()
    with open(path, "rb") as f:
        assert f.read() == before
    shutil.rmtree(d)


passed = sum(1 for _, ok, _ in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
if passed != len(_results):
    raise SystemExit(1)