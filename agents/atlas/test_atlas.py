"""
ATLAS increment (a), Part 2 — L1 (static) + L2 (smoke) tests for chat.py.
The model and web search are FAKED (no API keys, no cost), and the data
file is always a TEMP file — your real fitness.json is never touched.

Run from the repo root:  python -m agents.atlas.test_atlas
"""
import json
import os
import re
import shutil
import tempfile

from agents.atlas import chat
from agents.atlas import atlas_tools
from agents.atlas.prompt import ATLAS_PROMPT, ATLAS_SYSTEM_PROMPT
from shared import agent_topics
from shared.web_search import WEB_SEARCH_FAILED_PREFIX

REPO_ROOT = atlas_tools._REPO_ROOT
CHAT_SRC = os.path.join(REPO_ROOT, "agents", "atlas", "chat.py")

_results = []
model_calls = []
search_calls = []
search_reply = ["Web search results:\n\n1. Title\n   snippet\n   link"]


def fake_stream_by_tier(agent, tier, system_prompt, messages, location=""):
    model_calls.append({"agent": agent, "tier": tier, "system": system_prompt,
                        "messages": list(messages), "location": location})
    yield "Get "
    yield "moving."


def fake_web_search(query, num_results=3):
    search_calls.append(query)
    return search_reply[0]


chat.stream_by_tier = fake_stream_by_tier
chat.web_search = fake_web_search


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


def reset():
    model_calls.clear()
    search_calls.clear()
    search_reply[0] = "Web search results:\n\n1. Title\n   snippet\n   link"


def run(message, history=None, tier=None, location=""):
    return "".join(chat.stream_atlas(message, history, location, tier))


def temp_data(obj=None, raw=None):
    d = tempfile.mkdtemp(prefix="atlas_chat_test_")
    path = os.path.join(d, "fitness.json")
    os.environ["FITNESS_DATA_PATH"] = path
    if raw is not None:
        with open(path, "w", encoding="utf-8") as f:
            f.write(raw)
    elif obj is not None:
        with open(path, "w", encoding="utf-8") as f:
            json.dump(obj, f)
    return path, d


SAMPLE = {
    "profile": {"name": "Joey", "notes": "test"},
    "workouts": [
        {"type": "swim", "date": "2026-03-01", "total_distance_yards": 2000, "duration_minutes": 60,
         "strokes": ["freestyle"], "difficulty_1_to_10": 7},
        {"type": "swim", "date": "2026-03-05", "total_distance_yards": 1500, "duration_minutes": 45,
         "strokes": ["breaststroke"], "difficulty_1_to_10": 6},
        {"type": "gym", "date": "2026-03-02", "exercises": [{"name": "bench press"}],
         "duration_minutes": 50, "difficulty_1_to_10": 6},
    ],
    "injuries": [{"status": "none", "description": "placeholder"}],
}

# ───────────────────────── L1 — STATIC ─────────────────────────

with open(CHAT_SRC, encoding="utf-8") as _f:
    SRC = _f.read()


@check("L1 chat.py routes ONLY through stream_by_tier (Lesson #1/#11)")
def _():
    for direct in ("stream_gemini(", "stream_ollama(", "stream_claude("):
        assert direct not in SRC, direct
    assert 'stream_by_tier("atlas"' in SRC


@check("L1 no substring keyword matching, no bare except, no secrets in chat.py")
def _():
    assert ".lower()" not in SRC          # matching lives in contains_keyword only
    assert not re.search(r"except\s*:", SRC)
    assert not re.search(r"(api[_-]?key|sk-ant|AIza)\s*=\s*['\"]", SRC, re.I)
    assert "model_tier" in SRC and "ollama" not in SRC.lower().replace("stream_by_tier", "")


@check("L1 every ATLAS keyword list exists and is non-empty")
def _():
    for name in ("ATLAS_NON_TOPIC", "ATLAS_INTENT", "ATLAS_SEARCH_TRIGGERS", "ATLAS_HISTORY_PHRASES",
                 "ATLAS_HISTORY_QUANTITY", "ATLAS_HISTORY_SUBJECTS", "ATLAS_ADVICE_SIGNALS",
                 "ATLAS_REPORT_PHRASES", "ATLAS_SWIM_WORDS", "ATLAS_GYM_WORDS", "ATLAS_INJURY_WORDS"):
        assert getattr(agent_topics, name), name


@check("L1 ATLAS has no memory or logging yet (increments b/c not built)")
def _():
    assert "save_memory" not in SRC and "search_memory" not in SRC
    assert "log_swim_workout" not in SRC and "MEMORY_SAVE" not in SRC


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 off-topic messages get the Goggins refusal, no model call, no search")
def _():
    reset(); path, d = temp_data(SAMPLE)
    for msg in ["what's the weather today", "help me write python code",
                "give me a recipe for dinner", "how do I fix my car"]:
        assert run(msg) == chat.REFUSAL_MESSAGE, msg
    assert not model_calls and not search_calls
    assert chat.REFUSAL_MESSAGE == "That's not my lane — hit up NEXUS."
    shutil.rmtree(d)


@check("L2 old substring bugs stay fixed: real fitness questions are NOT refused")
def _():
    reset(); path, d = temp_data(SAMPLE)
    good = ["what's a good workout program for swimmers",
            "I want to decode my heart rate zones",
            "should I do cardio before lifting",
            "how much money should I spend on a gym membership",
            "workout plan for someone recovering from a car accident"]
    for msg in good:
        assert run(msg) == "Get moving.", msg
    assert len(model_calls) == len(good)
    shutil.rmtree(d)


@check("L2 model gets ATLAS prompt, agent name, live data summary, and the message")
def _():
    reset(); path, d = temp_data(SAMPLE)
    out = run("give me a leg day plan")
    assert out == "Get moving."
    c = model_calls[0]
    assert c["agent"] == "atlas" and c["system"] == ATLAS_SYSTEM_PROMPT
    assert c["system"].startswith(ATLAS_PROMPT)
    assert "Never write a mode name" in c["system"]
    last = c["messages"][-1]
    assert last["role"] == "user"
    assert "ATLAS DATA SUMMARY" in last["content"] and "Swim sessions: 2" in last["content"]
    assert "Gym sessions: 1" in last["content"]
    assert last["content"].endswith("Joey says: give me a leg day plan")
    assert not search_calls
    shutil.rmtree(d)


@check("L2 history is kept in order and the caller's list is never mutated")
def _():
    reset(); path, d = temp_data(SAMPLE)
    hist = [{"role": "user", "content": "hi"}, {"role": "assistant", "content": "yo"}]
    run("give me a leg day plan", history=hist)
    sent = model_calls[0]["messages"]
    assert len(sent) == 3 and sent[0] == hist[0] and sent[1] == hist[1]
    assert len(hist) == 2
    shutil.rmtree(d)


@check("L2 tier and location pass through unchanged (None = ATLAS's live default)")
def _():
    reset(); path, d = temp_data(SAMPLE)
    run("give me a leg day plan")
    run("give me a leg day plan", tier="local")
    run("give me a leg day plan", tier="paid_cloud", location="South Bend")
    assert [c["tier"] for c in model_calls] == [None, "local", "paid_cloud"]
    assert model_calls[2]["location"] == "South Bend"
    shutil.rmtree(d)


@check("L2 is_history_question table: real history asks vs coaching/report messages")
def _():
    yes = ["how many swim workouts have I logged", "how many yards did I swim in total",
           "show me my gym history", "what's my injury history", "give me my all-time totals",
           "what have I done so far"]
    no = ["how much should I bench", "how many sets for bicep curls", "should I swim tomorrow",
          "what's a good breaststroke drill", "I just swam 2000 yards, how many total do I have",
          "how many workouts should I do a week", "how do I structure my workouts"]
    for m in yes:
        assert chat.is_history_question(m), f"should be history: {m}"
    for m in no:
        assert not chat.is_history_question(m), f"should NOT be history: {m}"


@check("L2 history questions are answered from the data with NO model call")
def _():
    reset(); path, d = temp_data(SAMPLE)
    swim = run("how many swim workouts have I logged")
    assert "2 session(s), 3,500 total yards" in swim
    gym = run("show me my gym history")
    assert "Gym history: 1 session(s)" in gym and "bench press" in gym
    inj = run("list my injuries")
    assert inj == "No injuries on record."
    allv = run("what have I done overall")
    assert "Last 3 workout(s)" in allv and "Swim history" in allv and "Gym history" in allv
    assert not model_calls
    shutil.rmtree(d)


@check("L2 unreadable data: coaching still works with an explicit note; history says why")
def _():
    reset(); path, d = temp_data(raw='{"workouts": [')
    assert run("give me a leg day plan") == "Get moving."
    assert "FITNESS DATA UNAVAILABLE" in model_calls[0]["messages"][-1]["content"]
    assert "malformed" in model_calls[0]["messages"][-1]["content"]
    n = len(model_calls)
    out = run("show me my workouts")
    assert "can't read your fitness data" in out and "malformed" in out
    assert len(model_calls) == n          # history path made no model call
    shutil.rmtree(d)


@check("L2 web search: only on research questions, plain query, labeled as background")
def _():
    reset(); path, d = temp_data(SAMPLE)
    run("give me a leg day plan")
    assert not search_calls
    run("what's the best way to improve breaststroke technique", location="South Bend")
    assert search_calls == ["what's the best way to improve breaststroke technique"]
    content = model_calls[-1]["messages"][-1]["content"]
    assert "Background web search results" in content and "may be outdated" in content
    assert model_calls[-1]["location"] == "South Bend"
    shutil.rmtree(d)


@check("L2 a FAILED search is passed through as a failure, never dressed up as results")
def _():
    reset(); path, d = temp_data(SAMPLE)
    search_reply[0] = f"{WEB_SEARCH_FAILED_PREFIX} The search itself failed."
    run("any recovery tips after a hard swim")
    content = model_calls[-1]["messages"][-1]["content"]
    assert WEB_SEARCH_FAILED_PREFIX in content
    assert "Background web search results" not in content
    shutil.rmtree(d)


@check("L2 streamed chunks arrive intact and in order")
def _():
    reset(); path, d = temp_data(SAMPLE)
    assert list(chat.stream_atlas("give me a leg day plan")) == ["Get ", "moving."]
    shutil.rmtree(d)


passed = sum(1 for _, ok, _ in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
if passed != len(_results):
    raise SystemExit(1)