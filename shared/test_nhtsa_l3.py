"""
DRIVE increment (b), Part 6a — L3: the REAL NHTSA recall API (your internet connection).
Free, no key, read-only. It also prints the RAW response shape, because this client was written
from NHTSA's documentation without being able to call the API — this run is what proves the
assumed field names are right.

Run from the repo root:  python -m shared.test_nhtsa_l3
"""
import json
import urllib.parse

from shared import nhtsa as N

_passed = 0
_total = 0


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


def show(r, n=3):
    print(f"count={r['count']} shown={r['shown']} fetched_at={r['fetched_at']}\nurl={r['url']}")
    for rec in r["recalls"][:n]:
        print(f" - {rec['campaign']} | {rec['component']} | {rec['summary'][:110]} | reported {rec['reported']} | park_it={rec['park_it']}")


def raw_shape():
    url = N.NHTSA_RECALLS_URL + "?" + urllib.parse.urlencode({"make": "Honda", "model": "Civic", "modelYear": 2016})
    data = json.loads(N._http_get(url, 15))
    print("top-level keys:", list(data.keys()))
    key = "results" if "results" in data else "Results"
    items = data[key]
    print(f"list key = {key!r}, items = {len(items)}")
    if items:
        print("first item keys:", list(items[0].keys()))
        print("first item NHTSACampaignNumber:", items[0].get("NHTSACampaignNumber"), "| ReportReceivedDate:", items[0].get("ReportReceivedDate"))
    assert isinstance(items, list)
    if items:
        for field in ("NHTSACampaignNumber", "Component", "Summary", "Consequence", "Remedy", "ReportReceivedDate"):
            assert field in items[0], f"expected field {field!r} is missing from the real response"


def civic():
    r = N.lookup_recalls("Honda", "Civic", 2016)
    show(r)
    assert isinstance(r["count"], int) and r["count"] >= 0
    assert all(rec["campaign"] and rec["component"] for rec in r["recalls"]), "a recall is missing its campaign or component"
    print("\n--- what DRIVE's model would be shown ---")
    print(N.format_for_context(r))


def lowercase():
    a = N.lookup_recalls("Honda", "Civic", 2016)
    b = N.lookup_recalls("honda", "civic", 2016)
    print(f"Honda/Civic count={a['count']}  honda/civic count={b['count']}")
    assert a["count"] == b["count"]


def f150():
    r = N.lookup_recalls("Ford", "F-150", 2018)
    show(r)
    assert r["count"] > 0, "expected the 2018 F-150 to have recalls (checks that a hyphenated model is encoded right)"


def tesla():
    r = N.lookup_recalls("Tesla", "Model 3", 2023)
    show(r)
    assert r["count"] >= 0


def nonsense():
    try:
        r = N.lookup_recalls("Zzzzmake", "Qqqqmodel", 2016)
        print(f"NHTSA answered normally: count={r['count']}")
        assert r["count"] == 0
    except N.NHTSAError as e:
        print(f"NHTSAError (also fine): {e}")


def too_old():
    try:
        N.lookup_recalls("Honda", "Civic", 1900)
    except N.NHTSAError as e:
        print(f"refused locally: {e}")
        return
    raise AssertionError("a 1900 model year should have been refused")


case("RAW SHAPE of the real response (verifies the assumed field names)", raw_shape)
case("your real car: 2016 Honda Civic", civic)
case("capitalization does not matter", lowercase)
case("hyphenated model: 2018 Ford F-150", f150)
case("model with a space: 2023 Tesla Model 3", tesla)
case("nonsense make/model -> clean error or empty, never a crash", nonsense)
case("impossible year is refused without a network call", too_old)

print("\n" + "=" * 78)
print(f"L3 MECHANICAL: {_passed}/{_total} passed")
print("Now READ the output: do the recalls look like the real ones for a 2016 Civic? Is anything missing or odd?")
print("=" * 78)