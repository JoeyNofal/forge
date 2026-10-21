"""
ATLAS rules, Phase 1 item 1.2 - L3: the REAL local model (Ollama) drafts rules from real sentences.

Needs Ollama running with ATLAS's local model. It SAVES NOTHING and touches NO real data: it only calls the
drafting function (atlas_rules.draft_rule) and prints what it understood, then checks a few things in Python.
READ the printed drafts: a green count is not enough, the words must mean what you meant.

Run from the repo root:  python -m agents.atlas.test_atlas_rules_l3
"""
import os
import tempfile

_d = tempfile.mkdtemp(prefix="rules_l3_")
os.environ["TRAINING_RULES_PATH"] = os.path.join(_d, "rules.json")
os.environ["EXERCISE_LIBRARY_PATH"] = os.path.join(_d, "library.json")

from agents.atlas import atlas_rules as W
from agents.atlas import training_rules as R
from shared.model_json import ExtractionError

# (his sentence, a check on the drafted rule or None when a refusal/question is expected)
CASES = [
    ("no explosive moves, doctor's orders",
     lambda r: r["kind"] == "forbid" and {"jump", "clean"} & set(r["words"])),
    ("lateral raises only with the arm angle progression: back to a wall, arms up at 45 degrees from the wall, "
     "5 degrees closer to the wall each workout",
     lambda r: r["kind"] == "ladder" and (r["start"], r["step"], r["end"]) == (45, -5, 0)),
    ("RPE 5 for anything upper body while I ease in",
     lambda r: r["kind"] == "effort_cap" and r["scope"] == "upper_body" and r["rpe_max"] == 5 and r["only_ease_in"] is True),
    ("no curls or chin-ups for now, except leg and hamstring curls",
     lambda r: r["kind"] == "forbid" and "curl" in " ".join(r["words"]) and {"leg", "hamstring"} & set(r["except_words"])),
    ("leave biceps out of the workouts for now",
     lambda r: r["kind"] == "drop_muscle" and r["muscles"] == ["biceps"]),
    ("no overhead pressing until my doctor says so",
     lambda r: r["kind"] == "forbid" and "overhead" in r["words"]),
    ("keep my leg exercises at RPE 7 at most",
     lambda r: r["kind"] == "effort_cap" and r["rpe_max"] == 7 and r["scope"] == "muscles"),
    ("planks should get 5 seconds longer each workout, start at 20 seconds and go up to 60",
     lambda r: r["kind"] == "ladder" and (r["start"], r["step"], r["end"]) == (20, 5, 60)),
    ("put a note on every row: keep my shoulder blades down",
     lambda r: r["kind"] == "note" and "row" in " ".join(r["words"])),
    ("no jumping", lambda r: r["kind"] == "forbid" and "jump" in " ".join(r["words"])),
    ("I want to be careful", None),
    ("make it harder", None),
]

ok_count = 0
for sentence, check in CASES:
    print("=" * 78)
    print("YOU:", sentence)
    try:
        rule = W.draft_rule(sentence)
        print(R.describe_rule(rule))
        good = bool(check(rule)) if check else False
        verdict = "as expected" if good else ("UNEXPECTED: a rule was drafted where a question was expected" if not check else "CHECK THE WORDS ABOVE")
    except (R.RuleError, ExtractionError) as e:
        print("REFUSED:", e)
        good = check is None
        verdict = "as expected (it asked or refused)" if good else "NOT DRAFTED (the model's answer was refused)"
    ok_count += 1 if good else 0
    print("->", verdict)

print("=" * 78)
print(f"{ok_count}/{len(CASES)} drafts matched what the sentence says (nothing was saved). Read each draft above.")