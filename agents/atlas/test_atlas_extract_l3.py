"""
ATLAS increment (b), Part 3 — L3: REAL end-to-end with your REAL local model
(Ollama must be running with gemma3:12b). No cloud calls, no cost. TEMP data
and queue files only — your real fitness.json / pending_actions.json are
never touched.

For every case it prints what ATLAS would show you, plus the exact data that
was queued. Mechanical checks catch the obvious; YOU read the output for the
rest (are the numbers exactly what you said? anything invented?).

Run from the repo root:  python -m agents.atlas.test_atlas_extract_l3
"""
import json
import os
import tempfile
import time
from datetime import datetime, timedelta

_QUEUE_DIR = tempfile.mkdtemp(prefix="atlas_extract_l3_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")
_DATA_DIR = tempfile.mkdtemp(prefix="atlas_extract_l3_data_")
os.environ["FITNESS_DATA_PATH"] = os.path.join(_DATA_DIR, "fitness.json")

from agents.atlas import atlas_extract as X
from agents.atlas import atlas_logging as log
from agents.atlas import chat
from shared import pending_actions as pa

QUEUE = pa.PENDING_ACTIONS_PATH
FITNESS = os.environ["FITNESS_DATA_PATH"]
_passed = 0
_total = 0


def queue():
    if not os.path.exists(QUEUE):
        return []
    with open(QUEUE, encoding="utf-8") as f:
        return json.load(f)["actions"]


def reset_queue():
    if os.path.exists(QUEUE):
        os.remove(QUEUE)


def case(title, message, expect, seed_injury=False):
    """expect(actions, notes) -> None, or raises AssertionError."""
    global _passed, _total
    _total += 1
    print("\n" + "=" * 78 + f"\nCASE: {title}\nJOEY: {message}\n" + "=" * 78)
    reset_queue()
    start = time.time()
    try:
        notes = X.extract_and_propose(message)
    except Exception as e:
        print(f">>> CRASHED: {e!r}")
        return
    actions = queue()
    print("--- ATLAS would add ---")
    print("\n\n".join(notes) if notes else "(nothing — no proposal)")
    for a in actions:
        print(f"--- queued: {a['type']} ---\n{json.dumps(a['details'], ensure_ascii=False, indent=1)}")
    try:
        expect(actions, notes)
        print(f">>> MECHANICAL CHECKS: PASS  ({time.time() - start:.1f}s)")
        _passed += 1
    except AssertionError as e:
        print(f">>> MECHANICAL CHECKS: FAIL  {e}")


def only_type(actions, t):
    assert [a["type"] for a in actions] == [t], f"expected exactly one {t}, got {[a['type'] for a in actions]}"
    return actions[0]["details"]


# ── 1. a normal gym report, all numbers stated ──
def c1(actions, notes):
    d = only_type(actions, "log_gym")
    bench = [e for e in d["exercises"] if "bench" in e["name"].lower()]
    assert bench, "no bench press in exercises"
    b = bench[0]
    assert b["sets"] == 3 and b["reps"] == 8 and b["weight_lbs"] == 135, f"numbers wrong: {b}"
    assert d["difficulty_1_to_10"] is None and d["duration_minutes"] is None, "invented a difficulty/duration"
    assert not os.path.exists(FITNESS) or log_count() == 0, "something was SAVED without approval"


def log_count():
    with open(FITNESS, encoding="utf-8") as f:
        return len(json.load(f).get("workouts", []))


case("gym report with every number stated", "I did chest today. Bench press 3 sets of 8 at 135 lbs, and incline dumbbell press 3x10 at 50.", c1)


# ── 2. gym report with NO numbers: must not invent any ──
def c2(actions, notes):
    if not actions:
        return          # declining or asking for details is fine
    d = only_type(actions, "log_gym")
    for e in d["exercises"]:
        assert e["sets"] is None and e["reps"] is None and e["weight_lbs"] is None, f"INVENTED numbers: {e}"


case("gym report with no numbers: nothing invented", "I did legs today, squats and lunges", c2)


# ── 3. injury report ──
def c3(actions, notes):
    d = only_type(actions, "log_injury")
    assert "shoulder" in (d["body_part"] + " " + d["description"]).lower(), d


case("new injury report", "my left shoulder hurts when I press overhead", c3)


# ── 4. update: better -> recovering ──
def seed():
    log.log_injury({"body_part": "left shoulder", "description": "left shoulder pinch when pressing"})


def c4(actions, notes):
    d = only_type(actions, "update_injury")
    assert "shoulder" in d["body_part"].lower() and d["new_status"] in ("recovering", "resolved"), d
    assert d["new_status"] == "recovering", f"'better' should be recovering, got {d['new_status']}"


seed()
case("'my shoulder is better now' -> recovering", "my shoulder is better now", c4)


# ── 5. update: gone -> resolved ──
def c5(actions, notes):
    d = only_type(actions, "update_injury")
    assert d["new_status"] == "resolved", f"'doesn't hurt anymore' should be resolved, got {d['new_status']}"


case("'my shoulder doesn't hurt anymore' -> resolved", "my shoulder doesn't hurt anymore, it's completely healed", c5)


# ── 6. update with nothing to update ──
def c6(actions, notes):
    assert actions == [] and notes and "No open injury" in notes[0], notes


case("update for an injury that was never logged: says so, proposes nothing", "my knee is better now", c6)


# ── 7. hypothetical / question: must NOT propose ──
def c7(actions, notes):
    assert actions == [], f"proposed something for a question: {[a['type'] for a in actions]}"


case("a question about hypothetical pain", "if my shoulder hurt after benching, would that be a problem?", c7)
case("advice request, not a report", "should I lift legs tomorrow or rest?", c7)
case("planning statement", "I'm going to the gym tomorrow to do chest", c7)


# ── 8. relative date ──
def c8(actions, notes):
    d = only_type(actions, "log_gym")
    yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    assert d["date"] == yesterday, f"date {d['date']} != yesterday {yesterday}"


case("'yesterday' becomes the right date", "yesterday I lifted: squat 5x5 at 225", c8)


# ── 9. mixed message ──
def c9(actions, notes):
    types = sorted(a["type"] for a in actions)
    assert types == ["log_gym", "log_injury"], types
    gym = [a for a in actions if a["type"] == "log_gym"][0]["details"]
    assert gym["weaknesses"] == "" and gym["form_notes"] == "" and gym["coach_notes"] == "", \
        f"injury leaked into workout notes: {gym['weaknesses']!r}"


case("workout AND injury in one message -> two separate proposals",
     "I did back today, deadlift 3x5 at 275, but my lower back is sore", c9)


# ── 10. swim (kept available) ──
def c10(actions, notes):
    d = only_type(actions, "log_swim")
    assert d["total_distance_yards"] == 1500, d


case("swim report", "I swam 1500 yards freestyle in 30 minutes this morning", c10)

# ── 11. the whole chat path, real extraction, faked coaching reply (no cloud cost) ──
_total += 1
print("\n" + "=" * 78 + "\nCASE: full chat path (coaching reply faked, extraction REAL)\n" + "=" * 78)
reset_queue()
chat.stream_by_tier = lambda agent, tier, system, messages, location="": iter(["Good. ", "Keep pushing."])
out = "".join(chat.stream_atlas("I did chest today, bench 3x8 at 135"))
print(out)
try:
    assert out.startswith("Good. Keep pushing.\n\nProposed: log gym workout") and "id:" in out
    assert len(queue()) == 1 and queue()[0]["status"] == "pending"
    print(">>> MECHANICAL CHECKS: PASS")
    _passed += 1
except AssertionError:
    print(">>> MECHANICAL CHECKS: FAIL")

# ── 12. approving for real (temp files) and reading back ──
_total += 1
print("\n" + "=" * 78 + "\nCASE: approve the proposal for real (temp file) and read it back\n" + "=" * 78)
from agents.atlas import atlas_actions, atlas_tools
aid = queue()[0]["id"]
print(atlas_actions.approve_and_execute(aid[:8]))
print(atlas_tools.get_gym_history())
try:
    assert "bench press" in atlas_tools.get_gym_history().lower()
    print(">>> MECHANICAL CHECKS: PASS")
    _passed += 1
except AssertionError:
    print(">>> MECHANICAL CHECKS: FAIL")

print("\n" + "=" * 78)
print(f"L3 MECHANICAL: {_passed}/{_total} passed")
print("Now READ every case above: exactly the numbers you said? nothing invented? sensible notes?")
print("=" * 78)