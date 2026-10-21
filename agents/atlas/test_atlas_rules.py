"""
ATLAS rules, Phase 1 item 1.2 - L1, L2, L4, L5 tests for agents/atlas/atlas_rules.py (the rule writer + commands)
and the three rule approvals in atlas_actions.py. The local model is FAKED: the tests script exactly what it
says, good and bad. All data files are TEMP files.

Run from the repo root:  python -m agents.atlas.test_atlas_rules
"""
import json
import os
import re
import tempfile
import threading
from typing import Any

_QUEUE_DIR = tempfile.mkdtemp(prefix="rules_queue_")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(_QUEUE_DIR, "pending_actions.json")

from agents.atlas import atlas_actions as A
from agents.atlas import atlas_rules as W
from agents.atlas import atlas_setup as S
from agents.atlas import chat as C
from agents.atlas import plan_facts as PF
from agents.atlas import programs
from agents.atlas import training_rules as R
from shared import pending_actions as pa

_HERE = os.path.dirname(os.path.abspath(__file__))
QUEUE = pa.PENDING_ACTIONS_PATH
_results: list = []
CHAT_CALLS: list = []


def fake_chat_model(agent, tier, system, messages, location=""):
    CHAT_CALLS.append(messages)
    yield "CHAT TEXT"


C.stream_by_tier = fake_chat_model
C.extract_and_propose = lambda message: []
C.web_search = lambda q: "stub search result"


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


with open(os.path.join(_HERE, "atlas_rules.py"), encoding="utf-8") as f:
    SRC = f.read()


def fresh():
    d = tempfile.mkdtemp(prefix="rules_test_")
    os.environ["TRAINING_RULES_PATH"] = os.path.join(d, "rules.json")
    os.environ["EXERCISE_LIBRARY_PATH"] = os.path.join(d, "library.json")
    os.environ["TRAINING_PROFILE_PATH"] = os.path.join(d, "profile.json")
    os.environ["ATLAS_SETUP_STATE_PATH"] = os.path.join(d, "setup_state.json")
    os.environ["FITNESS_DATA_PATH"] = os.path.join(d, "fitness.json")
    if os.path.exists(QUEUE):
        os.remove(QUEUE)
    CHAT_CALLS.clear()
    W.complete_ollama_json = FAKE_OFF
    return d


def FAKE_OFF(system, user, timeout=0):          # a model that must not be called
    raise AssertionError("the model must not be called here")


class Model:
    """Stands in for complete_ollama_json: scripted replies (text, dict, or Exception), thread-safe call log."""
    def __init__(self, *replies):
        self.replies = list(replies)
        self.calls: list = []
        self.lock = threading.Lock()

    def __call__(self, system, user, timeout=0):
        with self.lock:
            self.calls.append((system, user))
            r = self.replies.pop(0) if self.replies else self.replies_default()
        if isinstance(r, Exception):
            raise r
        return r if isinstance(r, str) else json.dumps(r)

    def replies_default(self):
        return {"kind": "forbid", "words": ["overhead"], "reason": "no overhead for now"}


def use(model):
    W.complete_ollama_json = model
    return model


def pending() -> list:
    return pa.list_pending_actions("atlas")


def approve_id(text) -> str:
    m = re.search(r"approve ([0-9a-f]{8})", text)
    assert m is not None, text
    return m.group(1)


def say(msg) -> str:
    out = W.handle_message(msg)
    assert out is not None, f"rules ignored {msg!r}"
    return out


def run(msg) -> str:
    return "".join(C.stream_atlas(msg))


FORBID = {"kind": "forbid", "words": ["overhead", "military"], "except_words": [], "reason": "no overhead pressing for now"}
LADDER_SENTENCE = "lateral raises start at 45 degrees from the wall and go 5 degrees closer each workout"
LADDER = {"kind": "ladder", "words": ["lateral raise", "lateral raises"], "label": "arm angle from the wall", "unit": "degrees",
          "start": 45, "step": -5, "end": 0}


# ---------------------------------------------------------------- L1 static
@check("L1 the drafting uses the LOCAL model only, writes nothing itself, and has no secrets or hardcoded paths")
def _():
    assert "complete_ollama_json" in SRC
    for banned in ("stream_by_tier", "genai", "anthropic", "requests", "urllib", "open(", "json.dump", "sk-", "AIza", "D:\\", "C:\\", "NEXUS SYSTEM"):
        assert banned not in SRC, banned


@check("L1 the model is sent ONLY his sentence (never profile, health notes or logs) and a fixed system prompt")
def _():
    fresh()
    m = use(Model(FORBID))
    say("add rule no overhead pressing for now")
    assert len(m.calls) == 1 and m.calls[0][0] == W.SYSTEM_PROMPT and m.calls[0][1] == "no overhead pressing for now"
    assert "profile" not in W.SYSTEM_PROMPT.lower() and "injur" not in W.SYSTEM_PROMPT.lower()


@check("L1 every starter rule is a valid rule, and together they keep the behaviour the temporary hardcoded lists had")
def _():
    rules = [R.normalize_rule(s, keep_id=False) for s in W.STARTER_RULES]
    assert [r["kind"] for r in rules] == ["forbid", "ladder", "effort_cap", "forbid", "drop_muscle"]
    flags = programs.limit_flags({"limitations": ["tear in the labrum of the right shoulder under the biceps tendon"]})
    for n in ("Jump squat", "Power clean", "Box jumps", "Burpees", "Kettlebell swing", "Wall throws", "Medicine ball slam", "Plyometric push-up"):
        assert PF.exclusion_reason(n, flags) and R.forbid_reason(n, rules), n
    for n in ("Barbell curl", "Hammer curls", "Chin-ups", "Chin up", "Preacher curl"):
        assert PF.exclusion_reason(n, flags) and R.forbid_reason(n, rules), n
    for n in ("Leg curl", "Hamstring curl", "Goblet squat", "Bench press", "Seated row"):
        assert PF.exclusion_reason(n, flags) == "" and R.forbid_reason(n, rules) == "", n
    lateral = R.ladder_for("Dumbbell lateral raise", rules)
    assert R.dropped_muscles(rules) == ["biceps"] and lateral is not None and lateral["value"] == 45
    assert R.effort_cap_for("chest", rules, True) == 5 and R.effort_cap_for("chest", rules, False) is None


# ---------------------------------------------------------------- L2 commands
@check("L2 commands: only a message that is JUST the command counts")
def _():
    m = W.match_command
    for t in ("rules", "show rules", "My Rules", "list my rules", "see training rules", "Rules?"):
        assert m(t) == ("show", None), t
    for t in ("rules setup", "setup rules", "Atlas rules setup."):
        assert m(t) == ("setup", None), t
    assert m("add rule no overhead pressing") == ("add", "no overhead pressing") and m("ADD RULE x y z.") == ("add", "x y z")
    assert m("remove rule abcd1234") == ("remove", "abcd1234")
    assert m("set angle abcd1234 40") == ("angle", ("abcd1234", 40)) and m("set angle abcd1234 -5") == ("angle", ("abcd1234", -5))
    for no in ("rules of thumb", "I want to add a rule", "add rule", "add rule ", "remove rule", "set angle abcd", "set angle abcd1234",
               "show me the rules please", "what are my rules", "rules setup now", "approve abcd1234", "", "x" * 50, "set angle abcd1234 4x"):
        assert m(no) is None, no[:40]
    assert raises(lambda: W.match_command(None), TypeError)      # pyright: ignore[reportArgumentType]


@check("L2 'rules' shows the list; none yet says how to start; unreadable entries are mentioned; a damaged file is a plain message")
def _():
    d = fresh()
    assert "no rules yet" in say("rules") and "rules setup" in say("rules")
    R.add_rule(R.normalize_rule({"kind": "forbid", "text": "no jumps", "words": ["jump"]}))
    out = say("rules")
    assert out.startswith("Your rules (1):") and "jump" in out
    with open(os.environ["TRAINING_RULES_PATH"], "w", encoding="utf-8") as f:
        json.dump({"version": 1, "rules": [{"kind": "mystery"}, R.normalize_rule({"kind": "forbid", "text": "x", "words": ["jump"]})]}, f)
    assert "could not be read" in say("rules")
    with open(os.environ["TRAINING_RULES_PATH"], "w", encoding="utf-8") as f:
        f.write("{broken")
    assert "can't read or write your rules" in say("rules") and "damaged" in say("rules")


@check("L2 add rule: a draft is only a PROPOSAL showing exactly what it does; nothing is saved until approved")
def _():
    fresh()
    m = use(Model(FORBID))
    out = say("add rule no overhead pressing for now")
    assert out.startswith("Here is what I understood") and "Never plan an exercise whose name contains: overhead, military" in out
    assert "Your words: \"no overhead pressing for now\"" in out and "approve" in out and len(m.calls) == 1
    assert len(pending()) == 1 and pending()[0]["type"] == "add_rule" and R.load_rules() == []
    assert not os.path.exists(os.environ["TRAINING_RULES_PATH"])
    saved = A.approve_and_execute(approve_id(out))
    assert "Rule saved" in saved
    rules = R.load_rules()
    assert len(rules) == 1 and rules[0]["text"] == "no overhead pressing for now" and rules[0]["words"] == ["overhead", "military"]


@check("L2 deny throws the draft away; the same draft saved twice is refused the second time (nothing doubled)")
def _():
    fresh()
    use(Model(FORBID, FORBID, FORBID, FORBID))
    first = say("add rule no overhead pressing")
    A.deny_action(approve_id(first))
    assert R.load_rules() == []
    a, b = say("add rule no overhead pressing"), say("add rule no overhead pressing please")
    assert "Rule saved" in A.approve_and_execute(approve_id(a))
    out = A.approve_and_execute(approve_id(b))
    assert "already have this rule" in out and len(R.load_rules()) == 1
    again = say("add rule no overhead pressing at all")
    assert "already have a rule that means the same" in again and "approve" not in again


@check("L2 the words stored are HIS; the model's own 'text', id, created_at and 'active: false' are ignored")
def _():
    fresh()
    use(Model(dict(FORBID, text="THE MODEL'S WORDS", id="evil0000", created_at="1999", active=False, junk=5)))
    out = say("add rule  no overhead \x00 pressing\n for now ")
    A.approve_and_execute(approve_id(out))
    r = R.load_rules()[0]
    assert r["text"] == "no overhead pressing for now" and r["id"] != "evil0000" and r["active"] is True and "junk" not in r
    assert r["created_at"] != "1999" and R.forbid_reason("Overhead press", R.load_rules())


@check("L2 a 'never plan' proposal says which of YOUR library exercises it would block")
def _():
    fresh()
    from agents.atlas import exercise_library as lib
    for name in ("Overhead press", "Goblet squat", "Military press"):
        ok, _msg = lib.add_entry({"name": name, "steps": ["a", "b", "c"], "primary_muscles": ["shoulders"], "equipment": [], "aliases": []})
        assert ok, _msg
    use(Model(FORBID))
    out = say("add rule no overhead pressing")
    assert "This would block 2 exercise(s) in your library: Overhead press, Military press" in out
    use(Model({"kind": "drop_muscle", "muscles": ["biceps"], "reason": "x"}))
    assert "would block" not in say("add rule leave biceps out")


@check("L2 a ladder draft: numbers written as text are accepted, the arm-angle example from his own words works")
def _():
    fresh()
    use(Model(dict(LADDER, start="45", step="-5", end="0")))
    out = say("add rule " + LADDER_SENTENCE)
    assert "start 45 degrees" in out and "step -5 degrees" in out and "until 0 degrees" in out
    A.approve_and_execute(approve_id(out))
    got = R.ladder_for("Dumbbell lateral raise", R.load_rules())
    assert got and got["value"] == 45 and got["step"] == -5 and got["end"] == 0


@check("L2 the model cannot invent numbers: every nonzero number must be in his sentence (0 is allowed)")
def _():
    fresh()
    use(Model({"kind": "effort_cap", "scope": "upper_body", "rpe_max": 7, "only_ease_in": True}))
    out = say("add rule keep the upper body at RPE 5 while I ease in")
    assert "I couldn't turn that into a rule" in out and "number 7" in out and "Nothing was saved" in out and pending() == []
    use(Model({"kind": "effort_cap", "scope": "upper_body", "rpe_max": 5, "only_ease_in": True}))
    ok = say("add rule keep the upper body at RPE 5 while I ease in")
    assert "no higher than RPE 5 for all upper-body exercises, only during the ease-in" in ok
    use(Model(dict(LADDER, start=30)))
    assert "number 30" in say("add rule " + LADDER_SENTENCE)
    use(Model(dict(LADDER, step=5)))
    assert "toward the end" in say("add rule " + LADDER_SENTENCE)
    use(Model(dict(LADDER, start=45, step=-5, end=0)))
    assert "Here is what I understood" in say("add rule " + LADDER_SENTENCE)


@check("L2 the model says 'unclear': his question is shown plainly and nothing is proposed")
def _():
    fresh()
    use(Model({"kind": "unclear", "question": "which exercises do you mean?"}))
    out = say("add rule be careful")
    assert "I could not tell what rule you mean: which exercises do you mean?" in out and pending() == []
    use(Model({"kind": "unclear"}))
    assert "I could not tell what rule you mean" in say("add rule hmm")


@check("L2 a model that fails, answers badly or draws an invalid rule gives a plain message and saves nothing")
def _():
    fresh()
    bad = [RuntimeError("connection refused"), "not json at all", "", "[1,2]", {"kind": "delete_everything"}, {"kind": "forbid"},
           {"kind": "forbid", "words": "overhead"}, {"kind": "forbid", "words": ["overhead 2"]}, {"kind": "note", "words": ["row"]},
           {"kind": "ladder", "words": ["raise"], "label": "x", "start": 1, "step": 0, "end": 5}, {"kind": "drop_muscle", "muscles": ["wings"]},
           {"kind": "effort_cap", "scope": "legs", "rpe_max": 5}, None, 5, {"kind": ["forbid"]}]
    for reply in bad:
        use(Model(reply))
        out = say("add rule something with 5 in it")
        assert out.startswith("I couldn't turn that into a rule") and "Nothing was saved" in out, (reply, out[:80])
    assert pending() == [] and R.load_rules() == []
    use(Model(RuntimeError("connection refused")))
    assert "rules setup" in say("add rule no overhead")


@check("L2 a sentence over 300 characters is answered (not chatted about) and the model is not called")
def _():
    fresh()
    m = use(Model())
    out = say("add rule " + "no overhead pressing " * 20)
    assert "characters" in out and "300" in out and "Split it" in out and m.calls == [] and pending() == []


@check("L2 remove rule: a proposal that shows the rule; approve removes it; deny keeps it; unknown and ambiguous ids are plain messages")
def _():
    fresh()
    a = R.add_rule({"kind": "forbid", "text": "no jumps", "words": ["jump"]})
    b = R.add_rule({"kind": "note", "text": "rows", "words": ["row"], "note": "careful"})
    out = say(f"remove rule {a['id']}")
    assert out.startswith("Proposed: remove rule") and "no jumps" in out and len(R.load_rules()) == 2
    A.deny_action(approve_id(out))
    assert len(R.load_rules()) == 2
    assert "Rule removed" in A.approve_and_execute(approve_id(say(f"remove rule {a['id'][:5]}")))
    assert [r["id"] for r in R.load_rules()] == [b["id"]]
    for ident in ("zzzz9999", "abc", "a"):
        out = say(f"remove rule {ident}")
        assert "couldn't do that" in out and "Nothing was changed" in out
    assert "Rule removed" in A.approve_and_execute(approve_id(say(f"remove rule {b['id']}")))
    assert R.load_rules() == []


@check("L2 set angle: proposes, approve sets it, out-of-range numbers and non-ladders are refused up front")
def _():
    fresh()
    lad = R.add_rule(dict(LADDER, text=LADDER_SENTENCE))
    other = R.add_rule({"kind": "forbid", "text": "no jumps", "words": ["jump"]})
    out = say(f"set angle {lad['id']} 20")
    assert "set the arm angle from the wall of rule" in out and "to 20" in out and R.load_rules()[0]["current"] == 45
    assert "Set: arm angle from the wall is now 20 degrees" in A.approve_and_execute(approve_id(out))
    assert R.get_rule(lad["id"])["current"] == 20
    for ident, n in ((lad["id"], 50), (lad["id"], -5), (other["id"], 10), ("zzzz9999", 10)):
        out = say(f"set angle {ident} {n}")
        assert "couldn't do that" in out and "Nothing was changed" in out, (ident, n)
    assert R.get_rule(lad["id"])["current"] == 20


@check("L2 rules setup: five proposals from what the doctor said; approve the ones you want; nothing is saved before")
def _():
    fresh()
    out = say("rules setup")
    assert out.startswith("Starter rules") and len(pending()) == 5 and R.load_rules() == []
    ids = re.findall(r"approve ([0-9a-f]{8})", out)
    assert len(ids) == 5
    for i, action_id in enumerate(ids):
        if i == 4:
            A.deny_action(action_id)                  # he declines the biceps one
        else:
            assert "Rule saved" in A.approve_and_execute(action_id)
    rules = R.load_rules()
    assert [r["kind"] for r in rules] == ["forbid", "ladder", "effort_cap", "forbid"] and R.dropped_muscles(rules) == []
    assert R.forbid_reason("Jump squat", rules) and R.forbid_reason("Barbell curl", rules) and R.forbid_reason("Leg curl", rules) == ""
    again = say("rules setup")
    assert "(4 you already have, so I left them out.)" in again
    assert len(re.findall(r"approve ([0-9a-f]{8})", again)) == 1


@check("L2 rules setup when you already have everything: says so, proposes nothing")
def _():
    fresh()
    for action_id in re.findall(r"approve ([0-9a-f]{8})", say("rules setup")):
        A.approve_and_execute(action_id)
    n = len(pending())
    assert "already have every rule" in say("rules setup")
    assert len(pending()) == n and len(R.load_rules()) == 5


# ---------------------------------------------------------------- L2 in the real chat
@check("L2 in the chat: rule commands are answered by rules code (the chat model is never called); other messages still chat")
def _():
    fresh()
    use(Model(FORBID))
    assert "no rules yet" in run("rules") and CHAT_CALLS == []
    out = run("add rule no overhead pressing for now")
    assert "Here is what I understood" in out and CHAT_CALLS == []
    assert "Rule saved" in run("approve " + approve_id(out))
    assert "Your rules (1)" in run("show rules") and CHAT_CALLS == []
    assert run("what are good rules of thumb for squats") == "CHAT TEXT" and len(CHAT_CALLS) == 1
    assert "characters" in run("add rule " + "x" * 400) and len(CHAT_CALLS) == 1


@check("L2 rules commands work during the setup interview (they are not swallowed as an answer), and the interview carries on")
def _():
    fresh()
    S.handle_message("atlas setup")
    assert "no rules yet" in run("rules")
    assert S.handle_message("Build muscle") is not None


# ---------------------------------------------------------------- L4
@check("L4 20 threads drafting different rules at once: 20 proposals, nothing saved, no cross-talk")
def _():
    fresh()

    def reply_for(system, user, timeout=0):
        return json.dumps({"kind": "forbid", "words": [user.split()[-1]], "reason": "r"})

    W.complete_ollama_json = reply_for
    outs, errs = [], []

    def work(i):
        try:
            outs.append((i, say(f"add rule never plan thing{chr(97 + i)}word")))
        except Exception as e:
            errs.append(repr(e))
    ts = [threading.Thread(target=work, args=(i,)) for i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert not errs and len(outs) == 20 and len(pending()) == 20 and R.load_rules() == []
    assert all(f"thing{chr(97 + i)}word" in out for i, out in outs)


@check("L4 20 threads approving the SAME draft at once: exactly one rule is saved")
def _():
    fresh()
    use(Model(FORBID))
    action_id = approve_id(say("add rule no overhead pressing"))
    results = []
    ts = [threading.Thread(target=lambda: results.append(A.approve_and_execute(action_id))) for _i in range(20)]
    [t.start() for t in ts]
    [t.join() for t in ts]
    assert len(R.load_rules()) == 1 and sum("Rule saved" in r for r in results) == 1


@check("L4 50 sequential drafts of one sentence: every one is a proposal, none saved, the file never appears")
def _():
    fresh()
    use(Model(*[FORBID] * 50))
    for _i in range(50):
        assert "Here is what I understood" in say("add rule no overhead pressing")
    assert len(pending()) == 50 and not os.path.exists(os.environ["TRAINING_RULES_PATH"])


# ---------------------------------------------------------------- L5
@check("L5 hostile model output of every kind: a plain message or a valid proposal, never a crash, nothing saved by drafting")
def _():
    fresh()
    big_words = {"kind": "forbid", "words": [chr(97 + i // 26) + chr(97 + i % 26) + "x" for i in range(500)]}
    nested_json = '{"kind": "forbid", "words": ' + "[" * 30000 + "]" * 30000 + "}"
    hostile = ["x" * 100000, "[" * 100000, json.dumps(big_words), '{"kind": "forbid", "words": ["' + "a" * 100000 + '"]}',
               json.dumps({"kind": "forbid", "words": ["jump"], "reason": "r" * 100000}), "\x00\x01\x02", "{" * 5000,
               nested_json, json.dumps({"kind": "effort_cap", "scope": "upper_body", "rpe_max": 10 ** 40}),
               json.dumps({"kind": "ladder", "words": ["raise"], "label": "x", "start": 10 ** 20, "step": -1, "end": 0})]
    for h in hostile:
        use(Model(h))
        out = say("add rule keep it safe, 5 is my number")
        assert out.startswith("I couldn't turn that into a rule") or out.startswith("Here is what I understood"), (h[:30], out[:60])
    assert R.load_rules() == []


@check("L5 unicode, emoji and punctuation-only sentences are handled; the stored words are cleaned")
def _():
    fresh()
    use(Model(FORBID, FORBID, FORBID))
    assert "Here is what I understood" in say("add rule \U0001F4AA no overhead pressing \u00e9\u00e8 for now")
    punct = say("add rule !!!")
    assert "Here is what I understood" in punct or "couldn't" in punct
    assert W._clean_sentence(" a\x00b\n\tc ") == "a b c" and W._clean_sentence(None) == "" and W._clean_sentence(5) == ""


@check("L5 the approvals refuse bad details up front or at approval; they never write a broken rule")
def _():
    fresh()
    assert raises(lambda: A.propose_add_rule({"kind": "forbid"}), R.RuleError)
    assert raises(lambda: A.propose_add_rule(None), R.RuleError)
    assert raises(lambda: A.propose_remove_rule("nope1234"), R.RuleError)
    assert raises(lambda: A.propose_set_ladder("nope1234", 5), R.RuleError)
    lad = R.add_rule(dict(LADDER, text=LADDER_SENTENCE))
    for v in (True, "5", 2.5, 99, None):
        assert raises(lambda x=v: A.propose_set_ladder(lad["id"], x), R.RuleError), v
    assert pending() == []
    assert isinstance(A.describe("add_rule", {}), str) and isinstance(A.describe("set_ladder", {"x": 1}), str) and isinstance(A.describe("remove_rule", None), str)       # pyright: ignore[reportArgumentType]


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)