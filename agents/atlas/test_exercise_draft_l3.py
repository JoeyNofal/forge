"""
ATLAS exercise drafting - L3 (REAL Gemini, free cloud). Drafts a how-to for a handful of
exercises and prints each so YOU can read it. Costs nothing, writes nothing.
The mechanical checks catch obvious slips; the reading is the real test.

Run from the repo root:  python -m agents.atlas.test_exercise_draft_l3
"""
import re

from agents.atlas import exercise_draft as D
from agents.atlas import exercise_library as L

REAL = ["Incline DB press", "Windmill arms", "Goblet squat", "Cat-cow stretch", "Bulgarian split squat", "Pull-ups"]
NONSENSE = ["Banana flurb", "Quantum glute zapper"]
passes = fails = 0


def mark(ok, label):
    global passes, fails
    passes += bool(ok)
    fails += not ok
    print(("   PASS  " if ok else "   FAIL  ") + label)


for name in REAL:
    print("\n" + "=" * 78 + f"\nREAL EXERCISE: {name}\n" + "=" * 78)
    try:
        entry = D.draft_exercise(name)
    except D.DraftError as e:
        print(f"DraftError: {e}")
        mark(False, "a real exercise should have been drafted")
        continue
    print(L.format_entry(entry))
    print(f"\nOther names: {', '.join(entry['aliases']) or '(none)'}")
    mark(entry["name"] == name, "saved under the name you typed")
    mark(entry["status"] == "ai_drafted", "AI-drafted")
    mark(len(entry["steps"]) >= 3, f"at least 3 steps ({len(entry['steps'])})")
    mark(len(entry["primary_muscles"]) >= 1, "has a primary muscle")
    mark(not any(re.match(r"\d+[.)]", s) for s in entry["steps"]), "no leftover numbering inside steps")
    mark(not re.search(r"diagnos|\bcure\b|calories|burn \d", " ".join(entry["steps"] + entry["common_mistakes"]), re.I),
         "no medical or calorie claims")

for name in NONSENSE:
    print("\n" + "=" * 78 + f"\nMADE-UP NAME: {name}\n" + "=" * 78)
    try:
        entry = D.draft_exercise(name)
        print(L.format_entry(entry))
        mark(False, "a made-up name should have been refused")
    except D.DraftError as e:
        print(f"DraftError: {e}")
        mark(True, "a made-up name is refused")

print(f"\n{passes} passed, {fails} failed (mechanical checks only; READ every draft above)")
raise SystemExit(0 if fails == 0 else 1)