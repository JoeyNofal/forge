"""
ATLAS rules, Phase 1 item 1.1 - L1, L2, L4, L5 tests for agents/atlas/training_rules.py (the rules store + engine).
Pure Python: no model, no network, no keys. The rules file is always a TEMP file.

Run from the repo root:  python -m agents.atlas.test_training_rules
"""
import copy
import json
import os
import tempfile
import threading
import time
from typing import Any

from agents.atlas import training_rules as R

_HERE = os.path.dirname(os.path.abspath(__file__))
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


def raises(fn, exc: Any = Exception):
    try:
        fn()
    except exc:
        return True
    return False


with open(os.path.join(_HERE, "training_rules.py"), encoding="utf-8") as f:
    SRC = f.read()


def with_temp(fn):
    """Runs fn(path) with the rules file pointed at a fresh TEMP path."""
    path = os.path.join(tempfile.mkdtemp(), "rules.json")
    old = os.environ.get("TRAINING_RULES_PATH")
    os.environ["TRAINING_RULES_PATH"] = path
    try:
        return fn(path)
    finally:
        if old is None:
            os.environ.pop("TRAINING_RULES_PATH", None)
        else:
            os.environ["TRAINING_RULES_PATH"] = old


EXPLOSIVE: dict[str, Any] = {"kind": "forbid", "text": "no explosive moves, doctor's orders",
                             "words": ["jump", "jumps", "jumping", "clean", "cleans", "snatch", "throw", "throws", "slam", "burpee",
                                       "burpees", "plyometric", "kettlebell swing"], "reason": "doctor's orders: no explosive moves"}
CURLS: dict[str, Any] = {"kind": "forbid", "text": "no curls except leg curls", "words": ["curl", "curls"],
                         "except_words": ["leg", "hamstring"], "reason": "curls are off for now"}
LADDER: dict[str, Any] = {"kind": "ladder", "text": "lateral raises: 45 degrees from the wall, 5 less each workout",
                          "words": ["lateral raise", "lateral raises", "side raise"], "label": "arm angle from the wall",
                          "unit": "degrees", "start": 45, "step": -5, "end": 0}
EASE: dict[str, Any] = {"kind": "effort_cap", "text": "RPE 5 for the upper body while easing in", "scope": "upper_body",
                        "rpe_max": 5, "only_ease_in": True}
PTNOTE: dict[str, Any] = {"kind": "note", "text": "rows and pulling: check with my PT", "words": ["row", "rows", "pulldown"],
                          "note": "Check with your physical therapist first."}
DROP: dict[str, Any] = {"kind": "drop_muscle", "text": "leave biceps out", "muscles": ["biceps"]}


def norm(raw):
    return R.normalize_rule(raw)


def bad(raw, needle=""):
    try:
        R.normalize_rule(raw)
    except R.RuleError as e:
        assert needle in str(e), (needle, str(e))
        return True
    return False


# ---------------------------------------------------------------- L1 static
@check("L1 no model, network or secrets; writes only through the locked update_json; word matching via keyword_gate")
def _():
    for banned in ("model_client", "requests", "anthropic", "ollama", "genai", "urllib", "socket", "sk-", "AIza", "D:\\", "C:\\",
                   "NEXUS SYSTEM", "random", "json.dump", "open("):
        assert banned not in SRC, banned
    assert "update_json" in SRC and "contains_keyword" in SRC and "TRAINING_RULES_PATH" in SRC


@check("L1 the default file is in the data folder (kept out of git) and the five kinds are the documented ones")
def _():
    assert R.DEFAULT_RULES_PATH.replace("\\", "/").endswith("/data/training_rules.json")
    assert R.KINDS == ("forbid", "note", "effort_cap", "ladder", "drop_muscle")


# ---------------------------------------------------------------- L2 normalize
@check("L2 every kind normalizes; unknown keys are dropped; ids are made when missing and kept when present")
def _():
    for raw in (EXPLOSIVE, CURLS, LADDER, EASE, PTNOTE, DROP):
        r = norm(dict(raw, evil="x", id="keepme1"))
        assert r["id"] == "keepme1" and r["kind"] == raw["kind"] and "evil" not in r and r["active"] is True
        assert norm(raw)["id"] and len(norm(raw)["id"]) == 8
        assert R.normalize_rule(dict(raw, id="keepme1"), keep_id=False)["id"] != "keepme1"
    ladder = norm(LADDER)
    assert (ladder["start"], ladder["step"], ladder["end"], ladder["current"], ladder["done"]) == (45, -5, 0, 45, False)
    assert norm(EASE)["muscles"] == [] and norm(CURLS)["except_words"] == ["leg", "hamstring"]
    assert norm(dict(DROP, reason=""))["reason"] == "left out by one of your rules"


@check("L2 words are cleaned: case, punctuation, spaces, repeats; text is one clean line")
def _():
    r = norm(dict(EXPLOSIVE, words=["Jump", " JUMP ", "Kettlebell-Swing", "plyo!"], text="  no\x00 explosive\n\tmoves  "))
    assert r["words"] == ["jump", "kettlebell swing", "plyo"] and r["text"] == "no explosive moves"


@check("L2 bad words are refused with a plain reason: none, not a list, numbers, too short, too long, too many, too many words")
def _():
    assert bad(dict(EXPLOSIVE, words=[]), "at least one")
    assert bad(dict(EXPLOSIVE, words=["", "  ", None, 5]), "at least one")
    assert bad(dict(EXPLOSIVE, words="jump"), "list")
    assert bad(dict(EXPLOSIVE, words=None), "list")
    assert bad(dict(EXPLOSIVE, words=["jump 2"]), "number")
    assert bad(dict(EXPLOSIVE, words=["ab"]), "not a usable word")
    assert bad(dict(EXPLOSIVE, words=["x" * 31]), "not a usable word")
    assert bad(dict(EXPLOSIVE, words=["one two three four"]), "not a usable word")
    assert bad(dict(EXPLOSIVE, words=[chr(97 + i // 26) + chr(97 + i % 26) + "x" for i in range(25)]), "too many")
    assert bad(dict(CURLS, words=["curl"], except_words=["curl"]), "both")


@check("L2 bad rules are refused: kind, text, note, effort, muscles, ladder, drop_muscle, wrong types")
def _():
    for junk in (None, "x", 5, [], 3.5, True):
        assert bad(junk, "object")
    assert bad(dict(EXPLOSIVE, kind="bogus"), "unknown kind") and bad({"text": "x"}, "unknown kind")
    assert bad(dict(EXPLOSIVE, text=""), "words you used") and bad(dict(EXPLOSIVE, text=None), "words you used")
    assert bad(dict(PTNOTE, note=""), "needs the note")
    assert bad(dict(EASE, scope="legs"), "scope") and bad(dict(EASE, scope=None), "scope")
    for rpe in (0, 11, -1, True, "5", 5.5, None, 10 ** 30):
        assert bad(dict(EASE, rpe_max=rpe)), rpe
    assert bad(dict(EASE, only_ease_in="yes"), "true or false")
    assert bad(dict(EASE, scope="muscles", muscles=[]), "at least one muscle")
    assert bad(dict(EASE, scope="muscles", muscles=["wings"]), "not a muscle")
    assert bad(dict(EASE, scope="muscles", muscles="chest"), "list")
    assert norm(dict(EASE, scope="muscles", muscles=["Chest", "chest", "Rear Delts"]))["muscles"] == ["chest", "rear delts"]
    assert bad(dict(LADDER, label=""), "label")
    assert bad(dict(LADDER, step=0), "zero")
    assert bad(dict(LADDER, step=5), "toward the end")
    assert bad(dict(LADDER, start=10, end=10), "toward the end")
    assert bad(dict(LADDER, current=46), "between")
    assert bad(dict(LADDER, current=-1), "between")
    for v in (True, 4.5, "45", 10 ** 30):
        assert bad(dict(LADDER, start=v)), v
    assert bad(dict(LADDER, done="no"), "true or false")
    assert bad(dict(DROP, muscles=[]), "at least one muscle") and bad(dict(DROP, muscles=["wings"]), "not a muscle")


@check("L2 an 'active' value that is not true/false is treated as ON (the safe side)")
def _():
    assert norm(dict(EXPLOSIVE, active="no"))["active"] is True and norm(dict(EXPLOSIVE, active=False))["active"] is False


# ---------------------------------------------------------------- L2 the store
@check("L2 a missing file means no rules and is NOT created by reading")
def _():
    def run(path):
        assert R.load_rules() == [] and R.load_rules_report() == ([], 0) and not os.path.exists(path)
        assert "no rules yet" in R.list_rules_text(R.load_rules())
    with_temp(run)


@check("L2 add saves one rule and returns it; load gives it back; the file is the documented shape")
def _():
    def run(path):
        r = R.add_rule(EXPLOSIVE)
        assert r["id"] and r["created_at"] and R.load_rules() == [r]
        data = json.load(open(path, encoding="utf-8"))
        assert data["version"] == 1 and len(data["rules"]) == 1 and data["rules"][0]["id"] == r["id"]
    with_temp(run)


@check("L2 a duplicate (same kind and same words in any order) is refused; a different rule is accepted; a bad rule writes nothing")
def _():
    def run(path):
        R.add_rule(EXPLOSIVE)
        before = open(path, "rb").read()
        assert raises(lambda: R.add_rule(dict(EXPLOSIVE, words=list(reversed(EXPLOSIVE["words"])), text="same again")), R.RuleError)
        assert raises(lambda: R.add_rule(dict(EXPLOSIVE, words=[])), R.RuleError)
        assert open(path, "rb").read() == before
        R.add_rule(CURLS)
        assert len(R.load_rules()) == 2
        paused = R.add_rule(dict(LADDER, active=False))
        assert R.add_rule(LADDER)["id"] != paused["id"]
    with_temp(run)


@check("L2 entries this version cannot read are skipped when reading, counted, and KEPT when writing")
def _():
    def run(path):
        valid = norm(EXPLOSIVE)
        json.dump({"version": 1, "rules": [None, 5, {"kind": "mystery"}, "text", valid]}, open(path, "w", encoding="utf-8"))
        assert R.load_rules_report() == ([valid], 4)
        R.add_rule(CURLS)
        saved = json.load(open(path, encoding="utf-8"))["rules"]
        assert len(saved) == 6 and saved[:4] == [None, 5, {"kind": "mystery"}, "text"]
    with_temp(run)


@check("L2 remove: by full id, by a unique start (4+ characters); too short, ambiguous, unknown and empty are refused")
def _():
    def run(path):
        json.dump({"version": 1, "rules": [dict(norm(EXPLOSIVE), id="abcd1111"), dict(norm(CURLS), id="abcd2222"),
                                           dict(norm(DROP), id="zz991234")]}, open(path, "w", encoding="utf-8"))
        assert R.remove_rule("zz99")["id"] == "zz991234"
        for ident in ("abc", "abcd", "nope", "", None, 5):
            assert raises(lambda i=ident: R.remove_rule(i), R.RuleError), ident
        assert R.remove_rule("abcd1111")["kind"] == "forbid" and [r["id"] for r in R.load_rules()] == ["abcd2222"]
        assert R.remove_rule("ABCD2222")["id"] == "abcd2222" and R.load_rules() == []
    with_temp(run)


@check("L2 an unreadable entry can still be removed by its id")
def _():
    def run(path):
        json.dump({"version": 1, "rules": [{"id": "broken01", "kind": "mystery"}]}, open(path, "w", encoding="utf-8"))
        assert R.remove_rule("broken01")["kind"] == "unreadable" and json.load(open(path, encoding="utf-8"))["rules"] == []
    with_temp(run)


@check("L2 at most 50 rules; the 51st is refused and the file stays at 50")
def _():
    def run(path):
        for i in range(50):
            R.add_rule(dict(DROP, text=f"rule {i}", muscles=["biceps"], reason=f"r{i}") if i == 0 else
                       dict(PTNOTE, text=f"note {i}", words=[chr(97 + i // 26) + chr(97 + i % 26) + "xx"], note=f"n{i}"))
        assert len(R.load_rules()) == 50
        assert raises(lambda: R.add_rule(CURLS), R.RuleError) and len(R.load_rules()) == 50
    with_temp(run)


# ---------------------------------------------------------------- ladder
@check("L2 ladder table: 45 down to 0 in 9 comfortable workouts; a comfortable workout AT 0 finishes it; a finished ladder does not move")
def _():
    r = norm(LADDER)
    seen = []
    for _i in range(12):
        nxt, done = R.next_ladder_value(r, False)
        seen.append((r["current"], nxt, done))
        r["current"], r["done"] = nxt, done
        if done:
            break
    assert [s[0] for s in seen] == [45, 40, 35, 30, 25, 20, 15, 10, 5, 0] and seen[-1] == (0, 0, True) and seen[-2] == (5, 0, False)


@check("L2 ladder pain: back one step, never past the start; pain at the end un-finishes nothing by itself; positive ladders work")
def _():
    r = norm(dict(LADDER, current=30))
    assert R.next_ladder_value(r, True) == (35, False)
    assert R.next_ladder_value(dict(r, current=45), True) == (45, False)
    assert R.next_ladder_value(dict(r, current=0), True) == (5, False)
    up = norm({"kind": "ladder", "text": "hold longer", "words": ["plank"], "label": "hold", "unit": "sec", "start": 10, "step": 5, "end": 25})
    assert R.next_ladder_value(up, False) == (15, False) and R.next_ladder_value(dict(up, current=25), False) == (25, True)
    assert R.next_ladder_value(dict(up, current=15), True) == (10, False) and R.next_ladder_value(dict(up, current=10), True) == (10, False)
    odd = norm({"kind": "ladder", "text": "x", "words": ["plank"], "label": "hold", "start": 0, "step": 7, "end": 10})
    assert R.next_ladder_value(dict(odd, current=7), False) == (10, False)     # clamps to the end


@check("L2 apply_ladder_result writes the move; set_ladder_value validates and un-finishes; non-ladders refused")
def _():
    def run(path):
        lad, other = R.add_rule(LADDER), R.add_rule(EXPLOSIVE)
        assert R.apply_ladder_result(lad["id"], False)["after"] == 40
        got = R.apply_ladder_result(lad["id"][:5], True)
        assert (got["before"], got["after"], got["done"]) == (40, 45, False)
        assert R.set_ladder_value(lad["id"], 5)["current"] == 5
        for v in (-5, 50, True, 2.5, "5", None):
            assert raises(lambda x=v: R.set_ladder_value(lad["id"], x), R.RuleError), v
        R.set_ladder_value(lad["id"], 0)
        assert R.apply_ladder_result(lad["id"], False)["done"] is True
        frozen = R.apply_ladder_result(lad["id"], False)
        assert (frozen["before"], frozen["after"], frozen["done"]) == (0, 0, True)
        assert R.set_ladder_value(lad["id"], 10)["done"] is False
        assert raises(lambda: R.apply_ladder_result(other["id"], False), R.RuleError) and raises(lambda: R.set_ladder_value(other["id"], 1), R.RuleError)
        assert raises(lambda: R.apply_ladder_result("nope1234", False), R.RuleError)
    with_temp(run)


# ---------------------------------------------------------------- enforcing
RULES = [norm(x) for x in (EXPLOSIVE, CURLS, LADDER, EASE, PTNOTE, DROP)]


@check("L2 forbid: explosive names are blocked with the rule's reason; ordinary names and look-alike words are not (whole words)")
def _():
    for n in ("Jump squat", "Box JUMPS", "Power clean", "Clean and press", "Kettlebell swing", "Burpees", "Wall throws", "Plyometric push-up", "Jumping jacks"):
        assert R.forbid_reason(n, RULES) == "doctor's orders: no explosive moves", n
    for n in ("Goblet squat", "Cleaner stance deadlift", "Jumbo shrug", "Bench press", "Swing-free lunge", "Dead bug"):
        assert R.forbid_reason(n, RULES) == "", n



@check("L2 forbid exceptions: leg and hamstring curls pass, every other curl is blocked")
def _():
    for n in ("Barbell curl", "Hammer Curls", "Preacher curl", "Wrist curl"):
        assert R.forbid_reason(n, RULES) == "curls are off for now", n
    for n in ("Leg curl", "Lying hamstring curl", "Seated LEG CURLS"):
        assert R.forbid_reason(n, RULES) == "", n



@check("L2 a paused rule does nothing; junk in the rules list is ignored; no rules means nothing is blocked")
def _():
    paused = [dict(r, active=False) for r in RULES]
    assert R.forbid_reason("Jump squat", paused) == "" and R.notes_for("Barbell row", paused) == []
    assert R.effort_cap_for("chest", paused, True) is None and R.ladder_for("Lateral raise", paused) is None and R.dropped_muscles(paused) == []
    for junk in (None, "x", 5, {}, [None, 5, "x", {}, {"kind": "forbid"}, {"kind": "forbid", "active": True}]):
        assert R.forbid_reason("Jump squat", junk) == "" and R.notes_for("row", junk) == [] and R.ladder_for("lateral raise", junk) is None
        assert R.effort_cap_for("chest", junk, True) is None and R.dropped_muscles(junk) == []


@check("L2 notes: matching notes are returned once each; no match gives nothing")
def _():
    assert R.notes_for("Barbell row", RULES) == ["Check with your physical therapist first."]
    assert R.notes_for("Lat Pulldown", RULES) == ["Check with your physical therapist first."]
    assert R.notes_for("Squat", RULES) == [] and R.notes_for(None, RULES) == []
    twice = RULES + [norm(dict(PTNOTE, words=["rows"], text="again"))]
    assert R.notes_for("Seated rows", twice) == ["Check with your physical therapist first."]


@check("L2 effort cap: upper-body muscles only; 'only during the ease-in' respected; the lowest cap wins; legs and unknown are untouched")
def _():
    for m in R.UPPER_BODY_MUSCLES:
        assert R.effort_cap_for(m, RULES, True) == 5 and R.effort_cap_for(m, RULES, False) is None, m
    for m in ("quads", "glutes", "core", "Other", "", None):
        assert R.effort_cap_for(m, RULES, True) is None, m
    muscles = norm({"kind": "effort_cap", "text": "legs easy", "scope": "muscles", "muscles": ["quads", "chest"], "rpe_max": 4})
    assert R.effort_cap_for("quads", RULES + [muscles], False) == 4 and R.effort_cap_for("Chest", RULES + [muscles], True) == 4


@check("L2 ladder_for: the current value for matching names; None once finished; has_ladder stays true; no match gives None")
def _():
    got = R.ladder_for("Dumbbell Lateral Raise", RULES)
    assert got and got["value"] == 45 and got["label"] == "arm angle from the wall" and got["unit"] == "degrees" and got["step"] == -5
    assert R.ladder_for("Side raise", RULES) and R.ladder_for("Front raise", RULES) is None and R.ladder_for("Leg raise", RULES) is None
    done = [dict(r, done=True, current=0) if r["kind"] == "ladder" else r for r in RULES]
    assert R.ladder_for("Lateral raise", done) is None and R.has_ladder("Lateral raise", done) and not R.has_ladder("Squat", done)


@check("L2 dropped muscles are the union over active rules")
def _():
    assert R.dropped_muscles(RULES) == ["biceps"]
    more = RULES + [norm(dict(DROP, muscles=["Forearms", "biceps"], text="more"))]
    assert R.dropped_muscles(more) == ["biceps", "forearms"]


@check("L2 describe_rule shows exactly what a rule does; list_rules_text numbers them and marks paused ones; junk is harmless")
def _():
    text = {r["kind"]: R.describe_rule(r) for r in RULES}
    assert "jump" in R.describe_rule(RULES[0]) and "Never plan" in R.describe_rule(RULES[0])
    assert "arm angle from the wall" in R.describe_rule(RULES[2]) and "start 45 degrees" in R.describe_rule(RULES[2]) and "-5" in R.describe_rule(RULES[2])
    assert "RPE 5" in text["effort_cap"] and "only during the ease-in" in text["effort_cap"]
    assert "Check with your physical therapist" in text["note"] and "biceps" in text["drop_muscle"]
    assert "unless it also contains: leg, hamstring" in R.describe_rule(RULES[1])
    listing = R.list_rules_text(RULES[:2] + [dict(RULES[2], active=False)])
    assert listing.startswith("1. [") and "\n3. [" in listing and "(paused)" in listing
    for junk in (None, 5, "x", {}, {"kind": "ladder", "step": None}):
        assert isinstance(R.describe_rule(junk), str)
    assert R.list_rules_text(None) == "You have no rules yet."


@check("L2 check_ladder_value accepts only whole numbers between the start and the end")
def _():
    lad = norm(LADDER)
    assert R.check_ladder_value(lad, 20) == 20 and R.check_ladder_value(lad, 0) == 0 and R.check_ladder_value(lad, 45) == 45
    for v in (46, -1, True, 2.5, "20", None, 10 ** 30):
        assert raises(lambda x=v: R.check_ladder_value(lad, x), R.RuleError), v


@check("L2 get_rule reads one rule by id or unique start (never writes); duplicate_of finds an identical active rule")
def _():
    def run(path):
        a = R.add_rule(EXPLOSIVE)
        before = open(path, "rb").read()
        assert R.get_rule(a["id"]) == a and R.get_rule(a["id"][:4]) == a and open(path, "rb").read() == before
        for ident in ("zzzz", "", None, "ab"):
            assert raises(lambda i=ident: R.get_rule(i), R.RuleError), ident
        same = R.duplicate_of(norm(dict(EXPLOSIVE, words=list(reversed(EXPLOSIVE["words"])), text="again")), R.load_rules())
        assert same is not None and same["id"] == a["id"]
        assert R.duplicate_of(norm(CURLS), R.load_rules()) is None
        assert R.duplicate_of(norm(EXPLOSIVE), [dict(a, active=False)]) is None
        for junk in (None, "x", 5, {}):
            assert R.duplicate_of(junk, R.load_rules()) is None and R.duplicate_of(norm(EXPLOSIVE), junk) is None
    with_temp(run)


@check("L2 singular and plural forms match each other (curl/curls, jump/jumps, chin up/chin ups); 'press' is not cut to 'pres'")
def _():
    assert {"curl", "curls"} <= set(R._variants(("curl",))) and "curl" in R._variants(("curls",))
    assert {"press", "presses"} <= set(R._variants(("press",))) and "pres" not in R._variants(("press",))
    assert {"chin up", "chin ups"} <= set(R._variants(("chin up",))) and "chin up" in R._variants(("chin ups",))
    assert {"box", "boxes"} <= set(R._variants(("box",))) and {"jumps", "jump"} <= set(R._variants(("jumps",)))
    assert R._variants(("abs",))[0] == "abs" and "ab" not in R._variants(("abs",))        # too short to shorten
    one_form = [norm({"kind": "forbid", "text": "no curls or chin-ups", "words": ["curl", "chin up"], "except_words": ["leg"]})]
    for n in ("Hammer curls", "Barbell curl", "Chin-Ups", "Chin up", "Wide chin ups"):
        assert R.forbid_reason(n, one_form), n
    for n in ("Leg curls", "Leg curl", "Squat", "Curly bar", "Chinese food"):
        assert R.forbid_reason(n, one_form) == "", n
    other = [norm({"kind": "forbid", "text": "no jumps", "words": ["jumps", "plyometrics"]})]
    for n in ("Jump squat", "Box jump", "Plyometric push-up"):
        assert R.forbid_reason(n, other), n
    assert R.notes_for("Seated rows", [norm({"kind": "note", "text": "x", "words": ["row"], "note": "n"})]) == ["n"]
    assert R.ladder_for("Dumbbell lateral raises", [norm({"kind": "ladder", "text": "x", "words": ["lateral raise"], "label": "a",
                                                          "start": 45, "step": -5, "end": 0})]) is not None


@check("L2 -ing forms match both ways (jump/jumping, raise/raising, run/running, slam/slamming, row/rowing); real real-model case 'no jumping'")
def _():
    for a, b in (("jump", "jumping"), ("jumping", "jump"), ("raise", "raising"), ("raising", "raise"), ("run", "running"),
                 ("running", "run"), ("slam", "slamming"), ("row", "rowing"), ("rowing", "row"), ("lunge", "lunging"), ("curl", "curling")):
        assert b in R._variants((a,)), (a, b)
    jumping = [norm({"kind": "forbid", "text": "no jumping", "words": ["jumping"]})]
    plain_jump = [norm({"kind": "forbid", "text": "no jump", "words": ["jump"]})]
    for n in ("Jump squat", "Jump rope", "Box jumps", "Jumping jacks", "Jump lunge"):
        assert R.forbid_reason(n, jumping) and R.forbid_reason(n, plain_jump), n
    for n in ("Jumbo shrug", "Squat", "Bench press", "Goblet squat", "Cleaner stance deadlift"):
        assert R.forbid_reason(n, jumping) == "" and R.forbid_reason(n, plain_jump) == "", n
    assert R.forbid_reason("Rowing machine", [norm({"kind": "forbid", "text": "x", "words": ["row"]})])    # documented: the safe direction over-blocks a little
    assert R.forbid_reason("Praise the bar", [norm({"kind": "forbid", "text": "x", "words": ["raise"]})]) == ""


@check("L2 a 'never plan' rule is CHECKED against its own examples: examples must be blocked, allowed examples must stay allowed")
def _():
    ok = norm({"kind": "forbid", "text": "no explosive moves", "words": ["jump", "clean", "slam"], "except_words": [],
               "examples": ["Jump squat", "Power clean", "Box jumps", "jump squat", "  "], "allowed_examples": ["Goblet squat"]})
    assert ok["examples"] == ["Jump squat", "Power clean", "Box jumps"] and ok["allowed_examples"] == ["Goblet squat"]
    assert bad({"kind": "forbid", "text": "x", "words": ["explosive"], "examples": ["Jump squat"]}, "would not block 'Jump squat'")
    assert bad({"kind": "forbid", "text": "x", "words": ["curl"], "examples": ["Leg curl"], "except_words": ["leg"]}, "would not block 'Leg curl'")
    assert bad({"kind": "forbid", "text": "x", "words": ["curl"], "allowed_examples": ["Barbell curl"]}, "would block 'Barbell curl'")
    assert norm({"kind": "forbid", "text": "x", "words": ["curl"], "except_words": ["leg"], "allowed_examples": ["Leg curl"],
                 "examples": ["Hammer curls"]})["allowed_examples"] == ["Leg curl"]
    assert bad({"kind": "forbid", "text": "x", "words": ["curl"], "examples": "Barbell curl"}, "list")
    many = norm({"kind": "forbid", "text": "x", "words": ["curl"], "examples": [f"curl {chr(97 + i)}" for i in range(15)]})
    assert len(many["examples"]) == R.MAX_EXAMPLES
    assert len(norm({"kind": "forbid", "text": "x", "words": ["curl"], "examples": ["curl " + "y" * 200]})["examples"][0]) == R.MAX_EXAMPLE_CHARS
    assert norm(EXPLOSIVE)["examples"] == [] and norm(CURLS)["allowed_examples"] == []            # rules without examples stay valid
    text = R.describe_rule(ok)
    assert "Blocks, for example: Jump squat, Power clean, Box jumps" in text and "Still allowed: Goblet squat" in text
    assert "Blocks, for example" not in R.describe_rule(norm(EXPLOSIVE))
    assert isinstance(R.describe_rule({"kind": "forbid", "examples": 5, "allowed_examples": [None, 3], "words": ["x"]}), str)


# ---------------------------------------------------------------- loud failures
@check("L5 a damaged or wrong-shaped file fails LOUDLY on every read and write and is never overwritten")
def _():
    def run(path):
        for content in ("{not json", "[1, 2]", '"text"', '{"rules": 5}', '{"rules": {"a": 1}}'):
            open(path, "w", encoding="utf-8").write(content)
            for fn in (R.load_rules, R.load_rules_report, lambda: R.add_rule(EXPLOSIVE), lambda: R.remove_rule("abcd1234"),
                       lambda: R.apply_ladder_result("abcd1234", False), lambda: R.set_ladder_value("abcd1234", 5)):
                assert raises(fn, (RuntimeError, R.RuleError)), (content, fn)
            assert open(path, encoding="utf-8").read() == content
        open(path, "w", encoding="utf-8").write("{not json")
        assert raises(R.load_rules, RuntimeError) and raises(lambda: R.add_rule(EXPLOSIVE), RuntimeError)
    with_temp(run)


# ---------------------------------------------------------------- L4
@check("L4 20 threads adding different rules at once: all 20 are saved, ids unique, nothing lost")
def _():
    def run(path):
        errs = []

        def work(i):
            try:
                R.add_rule(dict(PTNOTE, text=f"rule {i}", words=[chr(97 + i) + "wxy"], note=f"note {i}"))
            except Exception as e:
                errs.append(repr(e))
        ts = [threading.Thread(target=work, args=(i,)) for i in range(20)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        rules = R.load_rules()
        assert not errs and len(rules) == 20 and len({r["id"] for r in rules}) == 20, errs
    with_temp(run)


@check("L4 20 threads all adding the SAME rule: exactly one is saved, 19 are refused")
def _():
    def run(path):
        out = []

        def work():
            try:
                R.add_rule(EXPLOSIVE)
                out.append("saved")
            except R.RuleError:
                out.append("refused")
        ts = [threading.Thread(target=work) for _i in range(20)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        assert out.count("saved") == 1 and out.count("refused") == 19 and len(R.load_rules()) == 1
    with_temp(run)


@check("L4 20 threads moving the same ladder: every step counted, it ends at 0 and finished")
def _():
    def run(path):
        lad = R.add_rule(LADDER)
        errs = []

        def work():
            try:
                R.apply_ladder_result(lad["id"], False)
            except Exception as e:
                errs.append(repr(e))
        ts = [threading.Thread(target=work) for _i in range(20)]
        [t.start() for t in ts]
        [t.join() for t in ts]
        final = R.load_rules()[0]
        assert not errs and final["current"] == 0 and final["done"] is True
    with_temp(run)


@check("L4 100 add/remove cycles leave the file valid and empty")
def _():
    def run(path):
        for i in range(100):
            r = R.add_rule(dict(PTNOTE, text=f"cycle {i}", words=["pullup"], note=f"n{i}"))
            R.remove_rule(r["id"])
        assert R.load_rules() == [] and json.load(open(path, encoding="utf-8"))["rules"] == []
    with_temp(run)


# ---------------------------------------------------------------- L5
@check("L5 enormous or hostile input: huge text and lists, absurd numbers, emoji, control characters, deep nesting")
def _():
    big = norm(dict(EXPLOSIVE, text="x" * 50000, reason="y" * 5000))
    assert len(big["text"]) == R.MAX_TEXT and len(big["reason"]) == R.MAX_REASON
    thousand = [chr(97 + i // 676) + chr(97 + (i // 26) % 26) + chr(97 + i % 26) for i in range(1000)]
    assert bad(dict(EXPLOSIVE, words=["jump"] * 5 + thousand), "too many")
    assert bad(dict(EXPLOSIVE, words=["\U0001F4AA"]), "at least one")
    assert bad(dict(LADDER, step=10 ** 400))
    nested: Any = []
    for _i in range(50000):
        nested = [nested]
    assert bad(dict(EXPLOSIVE, words=nested), "at least one")
    assert norm(dict(EXPLOSIVE, words=["jump", "\x00\x01"]))["words"] == ["jump"]
    assert norm(dict(EXPLOSIVE, words=["jump", "\u0441\u043f\u0440\u044b\u0436\u043e\u043a"]))["words"] == ["jump"]


@check("L5 a file with 10,000 junk entries loads fast and reports them; matching stays fast with the maximum rules")
def _():
    def run(path):
        json.dump({"version": 1, "rules": [{"kind": "x"}] * 10000 + [norm(EXPLOSIVE)]}, open(path, "w", encoding="utf-8"))
        t = time.time()
        rules, skipped = R.load_rules_report()
        assert len(rules) == 1 and skipped == 10000 and time.time() - t < 10
        many = [norm(dict(PTNOTE, text=f"n{i}", words=[chr(97 + i // 26) + chr(97 + i % 26) + "xx"], note=f"n{i}")) for i in range(50)]
        t = time.time()
        for _i in range(2000):
            R.forbid_reason("Barbell back squat", many + RULES)
            R.notes_for("Barbell back squat", many + RULES)
        assert time.time() - t < 10
    with_temp(run)


@check("L5 enforcing functions never change the rules they are given")
def _():
    before = copy.deepcopy(RULES)
    R.forbid_reason("Jump squat", RULES)
    R.notes_for("row", RULES)
    R.effort_cap_for("chest", RULES, True)
    R.ladder_for("lateral raise", RULES)
    R.dropped_muscles(RULES)
    R.describe_rule(RULES[2])
    R.list_rules_text(RULES)
    assert RULES == before


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)