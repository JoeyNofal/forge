"""
ATLAS chat exercise commands - L3 (REAL Gemini, free cloud) through ATLAS's actual chat:
draft exercise, approve, show exercise, reviewed, exercise library. TEMP files only, so
your real exercise library and approval queue are never touched. Costs nothing.
You READ the output; the mechanical checks only catch obvious slips.

Run from the repo root:  python -m agents.atlas.test_atlas_chat_library_l3
"""
import os
import re
import tempfile

_qd = tempfile.mkdtemp(prefix="chat_library_l3_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_qd, "pending_actions.json")
os.environ["EXERCISE_LIBRARY_PATH"] = os.path.join(tempfile.mkdtemp(prefix="chat_library_l3_data_"), "exercise_library.json")

from agents.atlas import chat

passes = fails = 0


def mark(ok, label):
    global passes, fails
    passes += bool(ok)
    fails += not ok
    print(("   PASS  " if ok else "   FAIL  ") + label)


def say(msg):
    print("\n" + "-" * 78 + f"\nYOU: {msg}\n" + "-" * 78)
    out = "".join(chat.stream_atlas(msg))
    print(out)
    return out


out = say("exercise library")
mark(out.startswith("The exercise library is empty"), "starts empty")

out = say("show exercise Windmill arms")
mark("is not in the exercise library" in out, "says it is not there yet")

out = say("draft exercise Windmill arms")
found = re.search(r"approve ([0-9a-f]{8})", out)
mark(found is not None, "a draft proposal with an approve line")
mark("NOT yet reviewed" in out and "Steps:" in out, "shows the full how-to and the AI-drafted label")
short = found.group(1) if found else "00000000"

out = say("show exercise Windmill arms")
mark("is not in the exercise library" in out, "still not saved before approval")

out = say(f"approve {short}")
mark(out.startswith("Exercise added"), "approve adds it")

out = say("show exercise windmill ARMS")
mark(out.startswith("Windmill arms (AI-drafted"), "show finds it, any capitalisation")

out = say("draft exercise Windmill arms")
mark(out.startswith("That exercise is already in the library"), "drafting it again does not call the model")

out = say("reviewed Windmill arms")
found = re.search(r"approve ([0-9a-f]{8})", out)
mark(found is not None, "a 'mark reviewed' proposal")
if found:
    out = say(f"approve {found.group(1)}")
    mark(out.startswith("Marked as reviewed"), "approve marks it reviewed")

out = say("draft exercise Goblet squat")
found = re.search(r"approve ([0-9a-f]{8})", out)
if found:
    say(f"approve {found.group(1)}")

out = say("exercise library")
mark("Windmill arms (reviewed)" in out and "Goblet squat (AI-drafted)" in out, "the list shows both, with their status")

out = say("draft exercise Banana flurb")
mark("I couldn't draft that" in out and "Nothing was saved" in out, "a made-up name is refused politely")

print(f"\n{passes} passed, {fails} failed (mechanical checks only; read every reply above)")
raise SystemExit(0 if fails == 0 else 1)