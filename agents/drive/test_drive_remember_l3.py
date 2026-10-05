"""
DRIVE (c) Part 2 — L3: REAL local model (gemma3:12b via Ollama) picking facts out of Joey's words, REAL
embeddings (nomic-embed-text) recalling them, and a REAL local DRIVE reply. TEMP folders only; no cloud model.

Mechanical checks catch the obvious; READ the output: is every remembered fact exactly what you said, in a good
standalone sentence? Is anything wrongly remembered (a logged event, money)? Anything wrongly missed?

Run from the repo root:  python -m agents.drive.test_drive_remember_l3
"""
import os
import tempfile

os.environ["DRIVE_MEMORY_PATH"] = tempfile.mkdtemp(prefix="drive_remember_l3_mem_")
os.environ["VEHICLE_DATA_PATH"] = os.path.join(tempfile.mkdtemp(prefix="drive_remember_l3_veh_"), "vehicle.json")
os.environ["PENDING_ACTIONS_PATH"] = os.path.join(tempfile.mkdtemp(prefix="drive_remember_l3_q_"), "pending_actions.json")

from agents.drive import chat
from agents.drive import drive_remember as M
from agents.drive import drive_logging as Lg
from shared import drive_memory as dm

Lg.log_mileage({"mileage": 55500})              # creates the temp vehicle file (a 2016 Honda Civic)
_real_stream = chat.stream_by_tier
_passed = 0
_total = 0
seen_context = []


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


def show(message):
    facts = M.extract_memories(message)
    print(f"JOEY: {message}")
    for f in facts:
        print(f"   -> [{f['category']}] {f['fact']}")
    if not facts:
        print("   -> (nothing to remember)")
    return facts


POSITIVE = [
    ("I always use full synthetic 0W-20 oil in my Civic", {"preference"}, "0W-20"),
    ("I'm planning a road trip to Colorado in November", {"plan"}, "Colorado"),
    ("I decided to keep the Civic until it hits 150,000 miles", {"decision", "goal", "plan"}, "150"),
    ("remember that the left rear window sticks", {"project_fact", "preference"}, "window"),
    ("actually my dealer is Honda of South Bend, not the one on Main Street", {"correction", "project_fact"}, "South Bend"),
    ("from now on I only go to the dealership for brake work", {"preference", "decision"}, "brake"),
]
NEGATIVE = [
    "just fueled up 10 gal for $30",
    "my car has 52,000 miles on it",
    "I got an oil change at 56,000 miles for $65",
    "my tire pressure light is on",
    "should I always use synthetic oil?",
    "what does a catalytic converter do?",
    "I only spend $500 on repairs",
]


def positives():
    for message, categories, needle in POSITIVE:
        facts = show(message)
        assert facts, f"nothing remembered for {message!r}"
        assert any(f["category"] in categories and needle.lower() in f["fact"].lower() for f in facts), \
            f"no fact in {sorted(categories)} mentioning {needle!r}"


def negatives():
    for message in NEGATIVE:
        facts = show(message)
        assert facts == [], f"remembered something it should not have: {facts}"


def mixed():
    facts = show("I always use 0W-20 and I just filled up 10 gal for $30")
    assert any("0W-20" in f["fact"] for f in facts), "lost the lasting preference"
    for f in facts:
        text = f["fact"].lower()
        assert "gal" not in text and "$" not in text and "filled" not in text, f"memorized the fill-up: {f}"


def save_all():
    for message, _c, _n in POSITIVE:
        print(f"JOEY: {message}")
        for note in M.remember_from_message(message):
            print(f"   {note}")
    print(f"\n{dm.memory_count()} memories stored")
    assert dm.memory_count() >= len(POSITIVE) - 1


def wrapper(agent, tier, system_prompt, messages, location=""):
    seen_context.append(messages[-1]["content"])
    yield from _real_stream(agent, tier, system_prompt, messages, location)


def chat_uses_memory():
    chat.stream_by_tier = wrapper
    seen_context.clear()
    try:
        out = "".join(chat.stream_drive("what oil should I use for my next oil change?", None, "", "local"))
    finally:
        chat.stream_by_tier = _real_stream
    print(out)
    ctx = seen_context[-1]
    assert "Background memory" in ctx and "0W-20" in ctx, "the oil preference never reached the model"
    assert "Colorado" not in ctx, "an unrelated memory was injected"
    assert "0W-20" in out or "synthetic" in out.lower(), "the reply ignored the remembered preference"


def chat_ignores_unrelated():
    chat.stream_by_tier = wrapper
    seen_context.clear()
    try:
        out = "".join(chat.stream_drive("how does a turbocharger work?", None, "", "local"))
    finally:
        chat.stream_by_tier = _real_stream
    print(out[:500])
    assert "Background memory" not in seen_context[-1], "memories were injected into an unrelated question"


try:
    case("things worth remembering (read each fact: standalone, third person, exactly what you said?)", positives)
    case("things that must NOT be remembered (logged events, questions, money)", negatives)
    case("one message with BOTH a lasting preference and a logged fill-up", mixed)
    case("save them all for real and announce them", save_all)
    case("a real DRIVE reply uses the remembered oil preference", chat_uses_memory)
    case("an unrelated question gets no memory injected", chat_ignores_unrelated)
except RuntimeError as e:
    print(f"\nCould not run: {e}")

print("\n" + "=" * 78)
print(f"L3 MECHANICAL: {_passed}/{_total} passed")
print("Now READ every fact above. Wrong or missed ones mean the prompt or the pre-filter phrases need tuning.")
print("=" * 78)