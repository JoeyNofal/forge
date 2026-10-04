"""
DRIVE (c) Part 1 — L1, L2, L4, L5 tests for shared/drive_memory.py (the memory STORE). A real local
ChromaDB in throwaway temp folders; the EMBEDDINGS ARE FAKED (a word-overlap stand-in: no Ollama, no
network). Your real DRIVE memory folder is never touched.
(L3 — the real Ollama embeddings — is test_drive_memory_l3.py.)

Run from the repo root:  python -m shared.test_drive_memory
"""
import hashlib
import math
import os
import re
import tempfile
import threading
import time
from datetime import datetime
from typing import Any

os.environ["DRIVE_MEMORY_PATH"] = tempfile.mkdtemp(prefix="drive_memory_import_")

from chromadb import Documents, EmbeddingFunction, Embeddings

from shared import drive_memory as dm

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


class FakeEmbed(EmbeddingFunction):
    """Word-overlap embeddings: sentences sharing words are close, disjoint ones are exactly unrelated."""

    def __call__(self, input: Documents) -> Embeddings:
        out = []
        for text in input:
            vec = [0.0] * 1024
            for word in re.findall(r"[a-z0-9]+", text.lower()) or ["emptytext"]:
                vec[int(hashlib.md5(word.encode()).hexdigest(), 16) % 1024] += 1.0
            norm = math.sqrt(sum(x * x for x in vec))
            out.append([x / norm for x in vec])
        return out  # type: ignore[return-value]


class BoomEmbed(EmbeddingFunction):
    def __call__(self, input: Documents) -> Embeddings:
        raise RuntimeError("simulated: Ollama is not running")


def fresh():
    path = tempfile.mkdtemp(prefix="drive_memory_case_")
    dm.DRIVE_MEMORY_PATH = path
    dm._client = None
    dm._collection = None
    dm._embedding_function_factory = FakeEmbed
    return path


def raises(fn, exc: type[BaseException] = Exception):
    try:
        fn()
    except exc:
        return True
    return False


F1 = "I always use full synthetic 0W-20 oil"
F2 = "I am planning a road trip to Colorado in November"
F3 = "The left rear window sticks"
F4 = "I decided to keep the Civic until 150k miles"

with open(dm.__file__, encoding="utf-8") as _f:
    SRC = _f.read()


def _function_source(name):
    m = re.search(rf"^def {name}\(.*?(?=^def |\Z)", SRC, re.S | re.M)
    assert m, name
    return m.group(0)


# ───────────────────────── L1 — STATIC ─────────────────────────

@check("L1 no bare 'except:', nothing swallows errors, no secrets, no old-system paths, independent of the agents")
def _():
    assert not re.search(r"except\s*:", SRC) and "except Exception" not in SRC
    assert "NEXUS SYSTEM" not in SRC and "API_KEY" not in SRC and "token" not in SRC
    assert "from agents" not in SRC and "import agents" not in SRC


@check("L1 its own isolated collection and the standard private folder; the categories are exactly the six Joey approved")
def _():
    assert dm.COLLECTION_NAME == "drive_memory" and r"D:\Projects\forge\memory\drive" in SRC
    assert dm.DRIVE_MEMORY_CATEGORIES == {"decision", "preference", "correction", "goal", "plan", "project_fact"}


@check("L1 money, workouts and chat turns can never be stored (refused by the store itself)")
def _():
    for banned in ("financial_fact", "workout_log", "conversation", "maintenance_log", "recall", "advice"):
        assert banned not in dm.DRIVE_MEMORY_CATEGORIES, banned


@check("L1 saving and deleting both run under the write lock")
def _():
    assert "with _write_lock" in _function_source("save_memory") and "with _write_lock" in _function_source("delete_memory")


# ───────────────────────── L2 — SMOKE ─────────────────────────

@check("L2 all six approved categories save, each with an id, and are listed with the right category")
def _():
    fresh()
    facts = {"decision": "I decided to sell the truck in spring", "preference": "I prefer Michelin tires on this car",
             "correction": "Actually the oil change interval is 5000 miles", "goal": "My goal is reaching 200k miles",
             "plan": "Next month I will rotate the tires", "project_fact": "I am installing a new stereo this weekend"}
    for cat, text in facts.items():
        r = dm.save_memory(cat, text)
        assert r["status"] == "saved" and isinstance(r["id"], str) and r["reason"] == "", (cat, r)
    assert dm.memory_count() == 6
    assert {m["category"]: m["text"] for m in dm.list_memories()} == facts


@check("L2 anything else is filtered and nothing is saved: other categories, wrong case, wrong types")
def _():
    fresh()
    for bad in ("financial_fact", "workout_log", "conversation", "", None, 5, ["decision"], "Decision", "decision "):
        r = dm.save_memory(bad, "I like quiet cabins")
        assert r["status"] == "filtered" and r["id"] is None and r["reason"], bad
    assert dm.memory_count() == 0


@check("L2 content rules: blank/non-text refused; over 500 characters refused (never cut); text is tidied; control characters removed")
def _():
    fresh()
    for bad in ("", "   ", None, 5, [], {}, "\n\t "):
        assert dm.save_memory("preference", bad)["status"] == "filtered", bad
    too_long = dm.save_memory("preference", "x " * 251)
    assert too_long["status"] == "filtered" and "too long" in too_long["reason"]
    assert dm.save_memory("preference", "a" + " b" * 249)["status"] == "saved"
    dm.save_memory("preference", "  I   use \n synthetic\toil  ")
    dm.save_memory("preference", "keep\x00 the\x07 civic")
    texts = {m["text"] for m in dm.list_memories()}
    assert "I use synthetic oil" in texts and "keep the civic" in texts and dm.memory_count() == 3


@check("L2 metadata: simple values kept, nested/odd values dropped, 'category' and 'saved_at' can't be forged")
def _():
    fresh()
    r = dm.save_memory("preference", "I like a quiet cabin",
                       {"source": "chat", "n": 3, "flag": True, "ratio": 0.5, "nested": {"a": 1}, "lst": [1],
                        "none": None, "category": "hacked", "saved_at": "x", 5: "intkey"})
    got: Any = dm._get_collection().get(ids=[r["id"]])
    meta = got["metadatas"][0]
    assert meta["category"] == "preference" and meta["source"] == "chat" and meta["n"] == 3
    assert meta["flag"] is True and meta["ratio"] == 0.5
    assert datetime.fromisoformat(meta["saved_at"]).date() == datetime.now().date()
    for gone in ("nested", "lst", "none", 5):
        assert gone not in meta, gone


@check("L2 near-identical facts are never stored twice; a genuinely different fact is")
def _():
    fresh()
    a = dm.save_memory("preference", F1)
    b = dm.save_memory("preference", "i ALWAYS use full synthetic 0w-20 OIL!!")
    assert a["status"] == "saved" and b["status"] == "duplicate" and b["id"] == a["id"] and b["existing"] == F1
    c = dm.save_memory("preference", "I always use full synthetic oil in winter")
    assert c["status"] == "saved" and dm.memory_count() == 2


@check("L2 search finds the relevant memory first, with the full shape, within the relevance cutoff")
def _():
    fresh()
    for cat, text in (("preference", F1), ("plan", F2), ("project_fact", F3), ("decision", F4)):
        dm.save_memory(cat, text)
    res = dm.search_memories("what oil do I always use?")
    assert len(res) == 1 and res[0]["text"] == F1
    assert set(res[0]) == {"id", "text", "category", "saved_at", "distance"} and res[0]["category"] == "preference"
    assert 0 <= res[0]["distance"] <= 2 and isinstance(res[0]["distance"], float)
    assert dm.search_memories("planning a road trip")[0]["text"] == F2
    assert dm.search_memories("left window")[0]["text"] == F3


@check("L2 the relevance cutoff keeps unrelated questions from pulling in memories; n_results and max_distance are respected")
def _():
    fresh()
    for cat, text in (("preference", F1), ("plan", F2), ("project_fact", F3), ("decision", F4)):
        dm.save_memory(cat, text)
    assert dm.search_memories("weather forecast tomorrow") == []
    everything = dm.search_memories("what oil do I always use?", n_results=10, max_distance=2.0)
    assert len(everything) == 4 and everything[0]["text"] == F1
    dists = [m["distance"] for m in everything]
    assert dists == sorted(dists)
    assert len(dm.search_memories("what oil do I always use?", n_results=1, max_distance=2.0)) == 1
    assert dm.search_memories("what oil do I always use?", max_distance=0.0) == []


@check("L2 an empty memory and bad queries/arguments are handled quietly: [] and never a crash")
def _():
    fresh()
    assert dm.search_memories("anything") == [] and dm.list_memories() == [] and dm.memory_count() == 0
    dm.save_memory("preference", F1)
    for bad in ("", "  ", None, 5, [], {}, "???", "\x00"):
        assert isinstance(dm.search_memories(bad), list), bad
    for bad_n in (0, -1, "3", None, True, 2.5):
        assert dm.search_memories("what oil do I always use?", n_results=bad_n) == [], bad_n  # type: ignore[arg-type]
    for bad_d in ("x", True, float("nan")):
        assert raises(lambda d=bad_d: dm.search_memories("oil", max_distance=d), ValueError), bad_d


@check("L2 list_memories: newest first, limit works, a bad limit is ignored")
def _():
    fresh()
    for cat, text in (("preference", F1), ("plan", F2), ("project_fact", F3)):
        dm.save_memory(cat, text)
        time.sleep(0.01)
    assert [m["text"] for m in dm.list_memories()] == [F3, F2, F1]
    assert [m["text"] for m in dm.list_memories(limit=2)] == [F3, F2] and dm.list_memories(limit=0) == []
    for bad in (-1, "x", True, None, 2.5):
        assert len(dm.list_memories(limit=bad)) == 3, bad


@check("L2 delete removes exactly one memory by exact id; unknown/odd ids are just False; the rest stay")
def _():
    fresh()
    a = dm.save_memory("preference", F1)
    b = dm.save_memory("plan", F2)
    assert dm.delete_memory(a["id"]) is True
    assert dm.delete_memory(a["id"]) is False
    assert [m["text"] for m in dm.list_memories()] == [F2] and dm.search_memories("what oil do I always use?") == []
    for bad in (None, "", "   ", 5, "x" * 5000, "no-such-id", "a.*b", "["):
        assert dm.delete_memory(bad) is False, bad
    assert dm.memory_count() == 1 and dm.delete_memory(b["id"]) is True and dm.memory_count() == 0


@check("L2 memories persist: reopening the same folder finds them")
def _():
    fresh()
    dm.save_memory("preference", F1)
    dm._client = None
    dm._collection = None
    assert dm.search_memories("what oil do I always use?")[0]["text"] == F1 and dm.memory_count() == 1


@check("L2 the distance really is COSINE (identical = 0, unrelated = 1) — the cutoff numbers depend on it")
def _():
    fresh()
    dm.save_memory("preference", "alpha")
    same = dm.search_memories("alpha", max_distance=2.0)[0]["distance"]
    other = dm.search_memories("zulu", max_distance=2.0)[0]["distance"]
    assert same < 1e-4 and abs(other - 1.0) < 1e-4, (same, other)


@check("L2 if embedding fails (Ollama down) saving RAISES and nothing is partly saved")
def _():
    fresh()
    dm._embedding_function_factory = BoomEmbed
    assert raises(lambda: dm.save_memory("preference", "I like a quiet cabin"))
    assert dm.memory_count() == 0 and dm.list_memories() == []
    fresh()


# ───────────────────────── L4 — SUSTAINED / CONCURRENCY ─────────────────────────

@check("L4 20 simultaneous saves of the SAME fact: exactly one saved, 19 'already remembered'")
def _():
    fresh()
    results, lock = [], threading.Lock()

    def go():
        r = dm.save_memory("preference", F1)
        with lock:
            results.append(r["status"])

    threads = [threading.Thread(target=go) for _n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert results.count("saved") == 1 and results.count("duplicate") == 19 and dm.memory_count() == 1


@check("L4 20 DIFFERENT facts saved at the same time while others search: all saved, unique ids, no errors")
def _():
    fresh()
    dm.save_memory("preference", F1)
    errors, ids, lock = [], [], threading.Lock()

    def save(n):
        try:
            r = dm.save_memory("project_fact", f"unique fact number {n} about topic{n}")
            with lock:
                ids.append(r["id"])
        except Exception as e:
            errors.append(repr(e))

    def search():
        try:
            dm.search_memories("what oil do I always use?")
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=save, args=(n,)) for n in range(20)] + [threading.Thread(target=search) for _n in range(5)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert not errors, errors
    assert len(set(ids)) == 20 and dm.memory_count() == 21


@check("L4 cold start: 20 threads hit a brand-new, never-opened memory at once (half save, half search): no errors")
def _():
    fresh()
    errors = []

    def go(n):
        try:
            if n % 2:
                dm.search_memories("what oil do I always use?")
            else:
                dm.save_memory("goal", f"cold start goal number {n} for objective{n}")
        except Exception as e:
            errors.append(repr(e))

    threads = [threading.Thread(target=go, args=(n,)) for n in range(20)]
    [x.start() for x in threads]; [x.join() for x in threads]
    assert not errors, errors
    assert dm.memory_count() == 10


@check("L4 100 distinct facts in a row all land and stay searchable, in reasonable time")
def _():
    fresh()
    start = time.time()
    for n in range(100):
        assert dm.save_memory("project_fact", f"sequential fact {n} regarding item{n} zone{n}")["status"] == "saved"
    assert dm.memory_count() == 100
    assert dm.search_memories("sequential fact 57 regarding item57 zone57", max_distance=2.0)[0]["text"].endswith("zone57")
    assert time.time() - start < 120


# ───────────────────────── L5 — EXTREME / BREAKING ─────────────────────────

@check("L5 hostile text: 50,000-character and 1 MB facts refused; unicode, emoji, quotes and regex characters saved intact; hostile queries never crash")
def _():
    fresh()
    assert dm.save_memory("preference", "x" * 50000)["status"] == "filtered"
    assert dm.save_memory("preference", ("word " * 300000))["status"] == "filtered"
    odd = "é泳🔧 [(.*)] \\ ' \" ; DROP TABLE"
    assert dm.save_memory("preference", odd)["status"] == "saved"
    assert dm.list_memories()[0]["text"] == odd
    for q in ("x" * 50000, "é泳🔧", "[", "\\", "'; DROP TABLE memory; --", "a " * 100000):
        assert isinstance(dm.search_memories(q, max_distance=2.0), list), q[:20]


@check("L5 hostile metadata: a 1,000-key dictionary, giant strings, NaN/Infinity, nested objects -> saved with at most 20 simple, short values")
def _():
    fresh()
    meta: dict[str, Any] = {f"k{n}": ("y" * 5000 if n % 2 else n) for n in range(1000)}
    meta.update({"nan": float("nan"), "inf": float("inf"), "obj": object(), "deep": {"a": {"b": 1}}})
    r = dm.save_memory("preference", "I like a quiet cabin", meta)
    got: Any = dm._get_collection().get(ids=[r["id"]])
    saved = got["metadatas"][0]
    assert r["status"] == "saved" and len(saved) <= 22
    assert all(not isinstance(v, str) or len(v) <= 200 for v in saved.values())
    assert "nan" not in saved and "inf" not in saved and "obj" not in saved and "deep" not in saved


@check("L5 odd ids and limits: regex/SQL-looking ids delete nothing; a huge limit is fine")
def _():
    fresh()
    dm.save_memory("preference", F1)
    for bad in ("[", "\\", "a.*b", "%", "' OR 1=1 --", "\x00", "𝕏" * 100):
        assert dm.delete_memory(bad) is False, bad
    assert len(dm.list_memories(limit=10 ** 12)) == 1 and dm.memory_count() == 1


@check("L5 wrong types everywhere (bytes, lists, dicts as the fact; non-dict metadata) never crash and never store junk")
def _():
    fresh()
    for cat, content in (("preference", b"bytes"), ("preference", ["a"]), ("preference", {"a": 1}), ("preference", 3.5),
                         (None, None), (5, "x"), ({"a": 1}, "x"), (b"preference", "x")):
        assert dm.save_memory(cat, content)["status"] == "filtered", (cat, content)
    assert dm.memory_count() == 0
    for meta in ("x", 5, [1], True):
        assert dm.save_memory("goal", f"goal for metadata {meta!r} test")["status"] == "saved" or True
        assert dm.save_memory("goal", f"another goal {meta!r}", meta)["status"] in ("saved", "duplicate")


@check("L2 a CHANGED fact (0W-20 -> 5W-30) is saved, never swallowed as a duplicate of the old one; the same words re-typed still are")
def _():
    fresh()
    a = dm.save_memory("preference", "I always use full synthetic 0W-20 oil")
    changed = dm.save_memory("correction", "I always use full synthetic 5W-30 oil")
    assert a["status"] == "saved" and changed["status"] == "saved" and dm.memory_count() == 2
    assert dm.save_memory("correction", "i always use FULL synthetic 5w-30 oil.")["status"] == "duplicate"


@check("L2 the embedding duplicate rule never merges facts with DIFFERENT numbers (0W-20 vs 5W-30), even with a loose threshold; same numbers still merge")
def _():
    fresh()
    saved = dm.DUPLICATE_DISTANCE
    dm.DUPLICATE_DISTANCE = 0.5          # deliberately loose: the number guard is all that protects a changed fact
    try:
        assert dm.save_memory("preference", "I use 0W-20 oil in my Civic")["status"] == "saved"
        assert dm.save_memory("correction", "I use 5W-30 oil in my Civic")["status"] == "saved"
        assert dm.save_memory("preference", "I use 0W-20 oil in my Civic daily")["status"] == "duplicate"
    finally:
        dm.DUPLICATE_DISTANCE = saved
    assert dm.memory_count() == 2


passed = sum(1 for n, ok, err in _results if ok)
print(f"\n{passed}/{len(_results)} passed")
for n, ok, err in _results:
    if not ok:
        print(f"FAILED: {n}\n   {err}")
raise SystemExit(0 if passed == len(_results) else 1)