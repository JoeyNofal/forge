"""
ATLAS workout coaching - L3 (REAL models): the real ATLAS coaching reply to a pasted
workout, on the local model and on free cloud (Gemini). TEMP files only. Costs nothing.
The mechanical checks catch obvious slips; YOU still read every reply.

Run from the repo root:  python -m agents.atlas.test_workout_coach_l3
"""
import os
import re
import tempfile

_qd = tempfile.mkdtemp(prefix="coach_l3_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_qd, "pending_actions.json")
os.environ["FITNESS_DATA_PATH"] = os.path.join(tempfile.mkdtemp(prefix="coach_l3_data_"), "fitness.json")

from agents.atlas import chat
from agents.atlas import atlas_actions as A
from agents.atlas import workout_coach as WC


def ex(name, presc, sets, rpe="", notes=""):
    return [f"Exercise: {name}", f"Prescribed: {presc}", *sets, f"RPE: {rpe}", f"Notes: {notes}"]


def blk(*sections, title="T"):
    lines = ["FORGE WORKOUT LOG v1", f"Title: {title}", "Date: 2026-10-01", "Unit: lbs"]
    for header, exercises in sections:
        lines.append(f"## {header}")
        for e in exercises:
            lines += e
    return "\n".join(lines)


SCENARIOS = {
    "A: your scenario (reps short, shoulder click)": blk(
        ("Warmup", [ex("Windmill arms", "1x20 per arm | weight: bodyweight | rest: 30 sec | target RPE: 5", ["Set 1: 20 reps | bodyweight"], "5", "my shoulders click")]),
        ("Upper chest", [ex("Incline DB press", "2x10 | weight: 10 lbs | rest: 2 min | target RPE: 7", ["Set 1: 10 reps | 10 lbs", "Set 2: 8 reps | 10 lbs"], "8", "")]),
        title="Chest workout"),
    "B: skipped + much harder + heavier than prescribed": blk(
        ("Main", [ex("Bench press", "3x8 | weight: 135 lbs | target RPE: 7", ["Set 1: 8 reps | 145 lbs", "Set 2: 8 reps | 145 lbs", "Set 3: 6 reps | 145 lbs"], "9", ""),
                  ex("Cable fly", "3x12 | weight: 30 lbs | target RPE: 7", ["Set 1: |"], "", "")]),
        title="Push day"),
    "C: clean session, nothing to ask": blk(
        ("Main", [ex("Goblet squat", "3x10 | weight: 40 lbs | target RPE: 7", ["Set 1: 10 reps | 40 lbs", "Set 2: 10 reps | 40 lbs", "Set 3: 10 reps | 40 lbs"], "7", "felt good")]),
        title="Leg day"),
}

passes = fails = 0


def mark(ok, label):
    global passes, fails
    passes += bool(ok)
    fails += not ok
    print(("   PASS  " if ok else "   FAIL  ") + label)


for tier in ("local", "free_cloud"):
    for name, text in SCENARIOS.items():
        if os.path.exists(os.environ["PENDING_ACTIONS_PATH"]):
            os.remove(os.environ["PENDING_ACTIONS_PATH"])
        print("\n" + "=" * 78 + f"\n{tier.upper()}  |  {name}\n" + "=" * 78)
        out = "".join(chat.stream_atlas(text, None, "", tier))
        marker = "throw it away."
        assert marker in out, out
        head, coaching = out.split(marker, 1)
        coaching = coaching.strip()
        print(head + marker + "\n\n--- COACHING (read this) ---\n" + coaching + "\n")

        found = re.search(r"approve ([0-9a-f]{8})", head)
        assert found is not None, head
        short = found.group(1)
        clean = A.get_pending_workout(short)
        built = WC.build_coach_facts(clean)
        flags = built["flags"]
        allowed = set(re.findall(r"\d+(?:\.\d+)?", "\n".join(built["lines"] + flags))) | {"1", "2", "3"}
        stray = [n for n in re.findall(r"\d+(?:\.\d+)?", coaching) if n not in allowed]
        mark(coaching != "", "the model said something")
        mark(not re.search(r"\b(?:i've|i have|has been|have been|was|is)\s+(?:saved|logged)\b", coaching, re.I), "never claims it is saved or logged")
        mark(coaching.count("?") <= 2, f"at most two questions ({coaching.count('?')} found)")
        if not flags:
            mark(coaching.count("?") == 0, "no flags -> no questions")
        mark(not stray, f"no numbers that are not in the facts (stray: {stray})")
        mark(not re.search(r"\b[A-Z]{3,} MODE\b", coaching), "no internal mode names printed")
        mark(len(coaching.split()) <= 220, f"short ({len(coaching.split())} words)")
        mark(A.get_pending_workout(short) is not None, "the workout is still only a proposal (nothing saved)")

print(f"\n{passes} passed, {fails} failed (mechanical checks only; read every reply above)")
raise SystemExit(0 if fails == 0 else 1)