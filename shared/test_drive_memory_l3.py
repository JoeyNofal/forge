"""
DRIVE (c) Part 1 — L3: the REAL local embeddings (Ollama must be running with `nomic-embed-text`).
Free, local, temp folder only. It prints a DISTANCE TABLE so the two cutoff numbers in
shared/drive_memory.py (DUPLICATE_DISTANCE, DEFAULT_MAX_DISTANCE) can be tuned from real data
instead of guesses. Mechanical checks catch the obvious; READ the table.

Run from the repo root:  python -m shared.test_drive_memory_l3
"""
import os
import tempfile

os.environ["DRIVE_MEMORY_PATH"] = tempfile.mkdtemp(prefix="drive_memory_l3_")

from shared import drive_memory as dm

FACTS = {
    "oil":    ("preference", "I always use full synthetic 0W-20 oil in my Civic."),
    "trip":   ("plan", "I'm planning a road trip to Colorado in November."),
    "window": ("project_fact", "The left rear window sticks when I roll it down."),
    "keep":   ("decision", "I decided to keep the Civic until it reaches 150,000 miles."),
    "shop":   ("correction", "The dealership I use is Honda of South Bend, not the one on Main Street."),
    "diy":    ("goal", "My goal is to do all my own oil changes this year."),
}
# query -> which facts are acceptable as the #1 answer
RELATED = {
    "what oil should I use for my next change?": {"oil", "diy"},
    "any trips coming up that I should prepare the car for?": {"trip"},
    "my window is acting up again": {"window"},
    "should I trade in the car soon?": {"keep"},
    "which dealer do I take it to?": {"shop"},
}
UNRELATED = ["what's the capital of France?", "write me a short poem about the sea", "how do I bake sourdough bread?"]

_passed = 0
_total = 0
ids = {}


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


def save_all():
    for key, (cat, text) in FACTS.items():
        r = dm.save_memory(cat, text)
        print(f"{key:7} -> {r['status']}")
        assert r["status"] == "saved", (key, r)
        ids[r["id"]] = key
    assert dm.memory_count() == len(FACTS)


def table():
    print(f"(cutoffs now: related/unrelated = {dm.DEFAULT_MAX_DISTANCE}, duplicate = {dm.DUPLICATE_DISTANCE})")
    worst_related_best = 0.0
    best_unrelated = 9.0
    for query in list(RELATED) + UNRELATED:
        rows = dm.search_memories(query, n_results=10, max_distance=2.0)
        print(f"\nQ: {query}")
        for r in rows:
            print(f"   {r['distance']:.3f}  {ids[r['id']]:7} {r['text'][:60]}")
        assert rows and all(0.0 <= r["distance"] <= 2.0 for r in rows), "distances are not cosine-like (expected 0..2)"
        if query in RELATED:
            worst_related_best = max(worst_related_best, rows[0]["distance"])
        else:
            best_unrelated = min(best_unrelated, rows[0]["distance"])
    print(f"\nWORST best-match distance for a RELATED question : {worst_related_best:.3f}")
    print(f"BEST  best-match distance for an UNRELATED question: {best_unrelated:.3f}")
    print("-> a good DEFAULT_MAX_DISTANCE sits between those two numbers.")


def related():
    for query, acceptable in RELATED.items():
        rows = dm.search_memories(query, n_results=10, max_distance=2.0)
        assert ids[rows[0]["id"]] in acceptable, f"{query!r}: top answer was {ids[rows[0]['id']]!r}, wanted one of {acceptable}"
        kept = dm.search_memories(query)
        assert kept and ids[kept[0]["id"]] in acceptable, f"{query!r}: the right memory is OUTSIDE the cutoff {dm.DEFAULT_MAX_DISTANCE}"


def unrelated():
    for query in UNRELATED:
        kept = dm.search_memories(query)
        assert kept == [], f"{query!r} pulled in memories under the cutoff {dm.DEFAULT_MAX_DISTANCE}: {[ids[k['id']] for k in kept]}"


def duplicates():
    cat, text = FACTS["oil"]
    same = dm.search_memories(text, max_distance=2.0)[0]["distance"]
    print(f"identical text distance: {same:.4f}")
    assert same < 0.01
    variant = text.lower().rstrip(".")
    r = dm.save_memory(cat, variant)
    print(f"case/punctuation variant -> {r['status']}")
    assert r["status"] == "duplicate", "a trivially re-typed fact was NOT recognised as the same memory"
    reworded = "I always put full synthetic 0W-20 in the Civic."
    d = dm.search_memories(reworded, max_distance=2.0)[0]
    print(f"reworded same fact: distance {d['distance']:.3f} to {ids[d['id']]!r} (duplicate threshold {dm.DUPLICATE_DISTANCE}) — for your information")
    changed = text.replace("0W-20", "5W-30")
    d2 = dm.search_memories(changed, max_distance=2.0)[0]["distance"]
    print(f"CHANGED fact (0W-20 -> 5W-30): distance {d2:.3f} to the old one (duplicate threshold {dm.DUPLICATE_DISTANCE})")
    r2 = dm.save_memory("correction", changed)
    print(f"changed fact -> {r2['status']}")
    assert r2["status"] == "saved", "a CHANGED fact was swallowed as a duplicate, so the stale one would stay"
    different = dm.save_memory(cat, "I always use full synthetic oil when towing a trailer.")
    print(f"a genuinely different oil fact -> {different['status']}")
    assert different["status"] == "saved", "a different fact was wrongly treated as a duplicate (threshold too loose)"


def survives_reopen():
    dm._client = None
    dm._collection = None
    kept = dm.search_memories("what oil should I use for my next change?")
    assert kept and ids.get(kept[0]["id"]) in {"oil", "diy"}


try:
    case("save six realistic facts with the real embeddings", save_all)
    case("DISTANCE TABLE (read this one)", table)
    case("every related question finds the right memory inside the cutoff", related)
    case("unrelated questions pull in nothing", unrelated)
    case("duplicate detection: a re-typed fact is recognised, a different one is not", duplicates)
    case("memories survive reopening", survives_reopen)
except RuntimeError as e:
    print(f"\nCould not run: {e}")

print("\n" + "=" * 78)
print(f"L3 MECHANICAL: {_passed}/{_total} passed")
print("Read the distance table: if 'unrelated' pulls memories in, lower DEFAULT_MAX_DISTANCE; if a related one misses, raise it.")
print("=" * 78)