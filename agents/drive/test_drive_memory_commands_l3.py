"""
DRIVE (c) Part 3 — L3: "what do you remember?" and "forget ..." against the REAL embeddings (Ollama + nomic-embed-text),
TEMP folders only. It prints the distances behind each forget so the two numbers in drive_memory_commands.py
(FORGET_MAX_DISTANCE, AMBIGUITY_MARGIN) can be checked against real data. Mechanical checks catch the obvious;
READ the output: does each "forget ..." pick the memory you would have meant?

Run from the repo root:  python -m agents.drive.test_drive_memory_commands_l3
"""
import os
import tempfile

os.environ["DRIVE_MEMORY_PATH"] = tempfile.mkdtemp(prefix="drive_cmd_l3_mem_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(tempfile.mkdtemp(prefix="drive_cmd_l3_q_"), "pending_actions.json")
os.environ["VEHICLE_DATA_PATH"] = os.path.join(tempfile.mkdtemp(prefix="drive_cmd_l3_v_"), "vehicle.json")

import json

from agents.drive import drive_actions as A
from agents.drive import drive_memory_commands as C
from shared import drive_memory as dm
from shared import pending_actions as pa

FACTS = {
    "oil": ("preference", "Joey always uses full synthetic 0W-20 oil in his Civic."),
    "trip": ("plan", "Joey is planning a road trip to Colorado in November."),
    "window": ("project_fact", "Joey's left rear window sticks."),
    "keep": ("goal", "Joey plans to keep his Civic until it reaches 150,000 miles."),
    "shop": ("correction", "Joey's dealer is Honda of South Bend, not the one on Main Street."),
    "brakes": ("preference", "Joey only goes to the dealership for brake work."),
}
ids = {}
_passed = 0
_total = 0


def case(title, fn):
    global _passed, _total
    _total += 1
    print("\n" + "=" * 78 + f"\nCASE: {title}\n" + "=" * 78)
    try:
        fn()
        print(">>> MECHANICAL CHECKS: PASS")
        _passed += 1
    except AssertionError as e:
        print(f">>> MECHANICAL CHECKS: FAIL  {e}")
    except Exception as e:
        print(f">>> CRASHED: {type(e).__name__}: {e}")


def queue():
    p = os.environ["PENDING_ACTIONS_PATH"]
    if not os.path.exists(p):
        return []
    with open(p, encoding="utf-8") as f:
        return json.load(f)["actions"]


def setup():
    for key, (cat, text) in FACTS.items():
        r = dm.save_memory(cat, text)
        assert r["status"] == "saved", (key, r)
        ids[r["id"]] = key
    assert dm.memory_count() == len(FACTS)


def listing():
    out = C.handle_memory_command(C.detect_memory_command("what do you remember?"))
    print(out)
    assert out.startswith("Here's what I remember (6):") and all(t in out for _c, t in FACTS.values())


def table_for(target):
    rows = dm.search_memories(target, n_results=6, max_distance=2.0)
    print(f"\n   distances for {target!r}:")
    for r in rows:
        print(f"     {r['distance']:.3f}  {ids[r['id']]:7} {r['text'][:60]}")


CLEAR = [
    ("forget the Colorado trip", "trip"),
    ("forget that I always use 0W-20", "oil"),
    ("forget my dealer", "shop"),
    ("forget the window", "window"),
    ("forget the brake work thing", "brakes"),
]


def clear_targets():
    for message, key in CLEAR:
        target = C.detect_memory_command(message)["target"]  # type: ignore  # type: ignore
        table_for(target)
        out = C.handle_memory_command(C.detect_memory_command(message))
        print(f"   JOEY: {message}\n   -> {out.splitlines()[0][:150]}")
        assert out.startswith("Proposed: forget this memory"), f"{message!r} did not produce a single proposal: {out[:120]}"
        assert FACTS[key][1] in out, f"{message!r} proposed the WRONG memory"
    assert dm.memory_count() == len(FACTS), "something was deleted without approval"


def not_found():
    out = C.handle_memory_command(C.detect_memory_command("forget the turbocharger wastegate"))
    table_for("the turbocharger wastegate")
    print(out)
    assert "couldn't find a memory matching" in out


def vague():
    for message in ("forget the Civic", "forget the oil", "forget the car stuff"):
        target = C.detect_memory_command(message)["target"]  # type: ignore
        table_for(target)
        out = C.handle_memory_command(C.detect_memory_command(message))
        print(f"   JOEY: {message}\n   -> {out[:200]}")
        assert out.startswith(("Proposed: forget this memory", "That could mean more than one memory", "I couldn't find")), out[:100]
    print("(vague targets may propose one, ask which, or find nothing — all are acceptable; READ them: is the choice sensible?)")


def approve_for_real():
    start = len(queue())
    out = C.handle_memory_command(C.detect_memory_command("forget the window"))
    aid = [a for a in queue()[start:]][-1]["id"]
    print(A.approve_and_execute(aid[:8]))
    left = [m["text"] for m in dm.list_memories()]
    assert FACTS["window"][1] not in left and len(left) == len(FACTS) - 1
    again = C.handle_memory_command(C.detect_memory_command("what do you remember?"))
    assert FACTS["window"][1] not in again


def by_id_and_last():
    first = dm.list_memories()[0]
    out = C.handle_memory_command(C.detect_memory_command(f"forget {first['id'][:6]}"))
    print(out.splitlines()[0][:160])
    assert first["text"] in out
    out2 = C.handle_memory_command(C.detect_memory_command("forget that"))
    print(out2.splitlines()[0][:160])
    assert dm.list_memories()[0]["text"] in out2


def forget_all():
    out = C.handle_memory_command(C.detect_memory_command("wipe your memory"))
    print(out.splitlines()[0])
    n = dm.memory_count()
    assert f"forget ALL {n} memories" in out
    aid = queue()[-1]["id"]
    print(A.approve_and_execute(aid))
    assert dm.memory_count() == 0
    assert "haven't been told anything" in C.handle_memory_command(C.detect_memory_command("what do you remember?"))


try:
    case("save six realistic memories with the real embeddings", setup)
    case("'what do you remember?' lists them all", listing)
    case("clear 'forget ...' targets pick exactly the memory you meant (read the distances)", clear_targets)
    case("something DRIVE never stored finds nothing and says where logged data lives", not_found)
    case("vague targets: propose, ask which, or find nothing — never a wrong deletion", vague)
    case("approve one forget for real; it is gone from the list", approve_for_real)
    case("forget by id and 'forget that'", by_id_and_last)
    case("'wipe your memory' with approval empties everything", forget_all)
except RuntimeError as e:
    print(f"\nCould not run: {e}")

print("\n" + "=" * 78)
print(f"L3 MECHANICAL: {_passed}/{_total} passed")
print("Read the distance tables: if a clear target is ambiguous or missed, tune FORGET_MAX_DISTANCE / AMBIGUITY_MARGIN.")
print("=" * 78)