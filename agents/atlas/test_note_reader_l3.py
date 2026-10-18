"""
ATLAS note reader - L3: the REAL local model (Ollama) reads real-sounding notes.
Needs Ollama running with the local model. Nothing is saved anywhere (temp files only).

Run from the repo root:  python -m agents.atlas.test_note_reader_l3
READ the printed readings yourself: the checks below only cover notes with an obvious meaning.
"""
import os
import tempfile

_DIR = tempfile.mkdtemp(prefix="atlas_note_reader_l3_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_DIR, "pending_actions.json")
os.environ["FITNESS_DATA_PATH"] = os.path.join(_DIR, "fitness.json")

from agents.atlas import atlas_actions as A
from agents.atlas import note_reader as N
from shared.model_json import ExtractionError

# (note, what an obvious reading must be, or None = just print it for me to read)
NOTES = [
    ("too hard", "struggled"),
    ("i couldn't continue", "struggled"),
    ("had to stop after 2 sets", "struggled"),
    ("form broke down on the last reps", "struggled"),
    ("way too heavy today", "struggled"),
    ("no struggle", "fine"),
    ("didn't struggle at all", "fine"),
    ("wasn't too heavy", "fine"),
    ("felt great, easy", "fine"),
    ("felt strong", "fine"),
    ("machine was taken so I used the cable version", "fine"),
    ("dropped the weight for the last set", None),
    ("shoulder clicked on rep 6", None),
    ("couldn't continue because my shoulder hurt", None),
    ("was tired from work", None),
    ("hmm", None),
    ("could have done more", None),
    ("i skipped the last set because i didn't feel like it", None),
    ("hard but I finished all my reps", None),
    ("light weight, boring", None),
]

passed = failed = 0


def report(name, ok, detail=""):
    global passed, failed
    passed, failed = (passed + 1, failed) if ok else (passed, failed + 1)
    print(("PASS  " if ok else "FAIL  ") + name + (f"  -> {detail}" if detail and not ok else ""))


print("== reading each note on its own (one model call per note, like a single-note workout) ==")
rows = []
try:
    for note, want in NOTES:
        got = N.read_notes([note])[0]
        rows.append((note, want, got))
        print(f"  {got:9} | {note}")
except ExtractionError as e:
    print(f"FAIL  the local model could not be used: {e}")
    raise SystemExit(1)

for note, want, got in rows:
    if want is not None:
        report(f"obvious note '{note}' -> {want}", got == want, f"got {got}")
    report(f"'{note}' gave one of the three allowed readings", got in N.READINGS, f"got {got}")

print("\n== all notes in ONE call (how a real workout is read) ==")
batch = [n for n, _ in NOTES]
together = N.read_notes(batch)
for note, got in zip(batch, together):
    print(f"  {got:9} | {note}")
report("same length and order as the notes", len(together) == len(batch))
agree = sum(1 for (n, w, g), t in zip(rows, together) if g == t)
report(f"one-call readings agree with one-at-a-time on at least 80% ({agree}/{len(batch)})", agree >= 0.8 * len(batch), f"{agree}/{len(batch)}")
for (note, want), got in zip(NOTES, together):
    if want is not None:
        report(f"[batch] obvious note '{note}' -> {want}", got == want, f"got {got}")

print("\n== a whole pasted workout through the real proposal path ==")
text = "\n".join([
    "FORGE WORKOUT LOG v1", "Title: Reader test", "Date: 2026-10-01", "Unit: lbs", "", "## Chest",
    "Exercise: Bench press", "Prescribed: 3x8 | weight: 135 lbs | target RPE: 8",
    "Set 1: 8 reps | 135 lbs", "Set 2: 8 reps | 135 lbs", "RPE: 7", "Notes: too hard, i couldn't continue",
    "Exercise: Incline press", "Prescribed: 3x10 | weight: 50 lbs | target RPE: 7",
    "Set 1: 10 reps | 50 lbs", "Set 2: 10 reps | 50 lbs", "Set 3: 10 reps | 50 lbs", "RPE: 7", "Notes: felt great",
    "Exercise: Cable fly", "Prescribed: 3x12 | weight: 20 lbs | target RPE: 7",
    "Set 1: 12 reps | 20 lbs", "Set 2: 12 reps | 20 lbs", "Set 3: 12 reps | 20 lbs", "RPE: 7"])
aid, msg = A.propose_workout_block(text, note_reader=N.apply_note_readings)
print(msg)
w = A.get_pending_workout(aid) if aid else None
report("a proposal was made", bool(aid) and w is not None)
if w:
    ex = {e["name"]: e for e in w["exercises"]}
    report("Bench press flagged as a struggle", ex["Bench press"].get("struggled") is True)
    report("Incline press NOT flagged", "struggled" not in ex["Incline press"])
    report("Cable fly (no note) NOT flagged and never sent to the model", "struggled" not in ex["Cable fly"])
    report("the proposal text shows the flagged note", "Struggle noted: Bench press" in msg)

print(f"\n{passed}/{passed + failed} passed")
raise SystemExit(0 if failed == 0 else 1)