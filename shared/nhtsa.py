"""
NHTSA recalls client — the official US government recall database (api.nhtsa.gov), no key needed.
Used by DRIVE's recall check (increment (b), Part 6).

IMPORTANT LIMIT, stated in everything shown to the model and to Joey: this API is keyed by
model year + make + model, NOT by VIN. A listed recall applies to that model year in general;
it may not apply to Joey's exact car, or may already be repaired. Only a VIN check at
nhtsa.gov/recalls can say that.

Same discipline as shared/web_search.py (Lessons #2 and #12): a real failure is NEVER returned
as "no recalls". Callers get an NHTSAError, and failure_note() tells the model the lookup failed
so it cannot answer from memory. An EMPTY list from NHTSA is a successful, genuinely empty answer.

The only place that touches the network is _http_get, so tests can replace it.
"""
import json
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime

NHTSA_RECALLS_URL = "https://api.nhtsa.gov/recalls/recallsByVehicle"
NHTSA_FAILED_PREFIX = "[NHTSA_LOOKUP_FAILED]"
MAX_RECALLS = 40              # recalls kept in a result (and later in a saved snapshot)
MAX_FIELD = 600               # characters kept per text field
CONTEXT_RECALLS = 10          # recalls shown to the DRIVE model
CONTEXT_FIELD = 220           # characters per field shown to the DRIVE model
MAX_RESPONSE_BYTES = 8_000_000


class NHTSAError(Exception):
    """The lookup failed. This NEVER means 'no recalls' — an empty list is a successful answer."""


def _http_get(url: str, timeout: float) -> str:
    """The ONE function that touches the network. Returns the response body as text."""
    request = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "FORGE-DRIVE/1.0"})
    with urllib.request.urlopen(request, timeout=timeout) as response:
        raw = response.read(MAX_RESPONSE_BYTES + 1)
    if len(raw) > MAX_RESPONSE_BYTES:
        raise NHTSAError("NHTSA's answer was unexpectedly huge")
    return raw.decode("utf-8-sig")


def trim_text(text: str, limit: int) -> str:
    """Cut at a WORD boundary (never in the middle of a word or a phone number) and mark the cut with an ellipsis."""
    if len(text) <= limit:
        return text
    cut = text[:limit]
    if " " in cut:
        cut = cut[:cut.rfind(" ")]
    return cut.rstrip(" ,;:-") + "…"


def _clean_text(value, limit: int = MAX_FIELD) -> str:
    if value is None or isinstance(value, (dict, list)):
        return ""
    return trim_text(" ".join(str(value).split()), limit)


def _iso_date(value) -> str:
    """NHTSA reports DD/MM/YYYY (checked against real data: '18/12/2023'). Shown as YYYY-MM-DD so nobody,
    and no model, can misread 11/07/2016 as November 7th. Anything else is kept as given."""
    text = _clean_text(value, 40)
    try:
        return datetime.strptime(text, "%d/%m/%Y").strftime("%Y-%m-%d")
    except ValueError:
        return text


def _normalize_recall(item):
    """One recall from NHTSA -> a small clean dict, or None if it isn't usable."""
    if not isinstance(item, dict):
        return None
    campaign = _clean_text(item.get("NHTSACampaignNumber"), 40)
    if not campaign:
        return None                      # a recall without a campaign number can't be identified
    return {
        "campaign": campaign,
        "manufacturer": _clean_text(item.get("Manufacturer"), 120),
        "component": _clean_text(item.get("Component"), 200),
        "summary": _clean_text(item.get("Summary")),
        "consequence": _clean_text(item.get("Consequence")),
        "remedy": _clean_text(item.get("Remedy")),
        "reported": _iso_date(item.get("ReportReceivedDate")),
        "park_it": item.get("parkIt") is True,       # only a real JSON true counts
    }


def lookup_recalls(make, model, model_year, timeout: float = 15.0) -> dict:
    """
    Official NHTSA recalls for a model year + make + model. Returns a plain, JSON-safe dict:
      {source, fetched_at, make, model, model_year, url, count, shown, recalls: [...]}
    `count` is how many recalls NHTSA listed; `recalls` keeps at most MAX_RECALLS of them.
    Raises NHTSAError on ANY failure (bad input, no connection, HTTP error, junk answer).
    """
    make_s, model_s = _clean_text(make, 60), _clean_text(model, 60)
    if not make_s or not model_s:
        raise NHTSAError("I need the vehicle's make and model to look up recalls")
    if (isinstance(model_year, bool) or not isinstance(model_year, int)
            or not 1950 <= model_year <= datetime.now().year + 2):
        raise NHTSAError(f"I need a real model year to look up recalls (got {model_year!r})")

    url = NHTSA_RECALLS_URL + "?" + urllib.parse.urlencode({"make": make_s, "model": model_s, "modelYear": model_year})
    try:
        body = _http_get(url, timeout)
    except urllib.error.HTTPError as e:
        if e.code in (400, 404):
            raise NHTSAError(f"NHTSA doesn't recognize {model_year} {make_s} {model_s} (HTTP {e.code})") from None
        raise NHTSAError(f"NHTSA answered with an error (HTTP {e.code})") from None
    except NHTSAError:
        raise
    except (urllib.error.URLError, TimeoutError, OSError, UnicodeDecodeError) as e:
        raise NHTSAError(f"couldn't reach NHTSA ({type(e).__name__}: {e})") from None

    try:
        data = json.loads(body)
    except (ValueError, TypeError, RecursionError):
        raise NHTSAError("NHTSA's answer wasn't valid JSON") from None
    if not isinstance(data, dict):
        raise NHTSAError("NHTSA's answer wasn't the expected kind of data")
    results = data.get("results", data.get("Results"))
    if not isinstance(results, list):
        raise NHTSAError("NHTSA's answer had no list of results")

    recalls = [r for r in (_normalize_recall(item) for item in results) if r]
    return {
        "source": "NHTSA recallsByVehicle",
        "fetched_at": datetime.now().isoformat(timespec="seconds"),
        "make": make_s,
        "model": model_s,
        "model_year": model_year,
        "url": url,
        "count": len(recalls),
        "shown": min(len(recalls), MAX_RECALLS),
        "recalls": recalls[:MAX_RECALLS],
    }


def format_for_context(result: dict) -> str:
    """The labeled block DRIVE's model gets (Lesson #2): official data, model-year level, NOT the VIN."""
    head = (f"[NHTSA RECALL DATA — official US government database, fetched {result['fetched_at'][:10]}. "
            f"This covers ALL {result['model_year']} {result['make']} {result['model']} vehicles, NOT Joey's VIN "
            "specifically: a listed recall may not apply to his exact car or may already be repaired. "
            "Only a VIN check at nhtsa.gov/recalls can say that. "
            "The texts below are shortened; never quote phone numbers from them. ")
    if result["count"] == 0:
        return head + "NHTSA lists NO recalls for this model year, make and model.]"
    lines = [head + f"{result['count']} recall(s) listed:"]
    shown = result["recalls"][:CONTEXT_RECALLS]
    for n, r in enumerate(shown, 1):
        park = " [NHTSA 'park it' warning]" if r.get("park_it") else ""
        lines.append(
            f"{n}. Campaign {r['campaign']} — {trim_text(r['component'], CONTEXT_FIELD)}{park}. "
            f"Defect: {trim_text(r['summary'], CONTEXT_FIELD)} Risk: {trim_text(r['consequence'], CONTEXT_FIELD)} "
            f"Remedy: {trim_text(r['remedy'], CONTEXT_FIELD)} (reported {r['reported']})")
    more = result["count"] - len(shown)
    if more > 0:
        lines.append(f"...and {more} more not shown here.")
    return "\n".join(lines) + "]"


def failure_note(error) -> str:
    """What the model is told when the lookup failed (like web_search's failure marker)."""
    return (f"{NHTSA_FAILED_PREFIX} The official recall lookup failed and returned no data ({error}). "
            "Do not guess or recall any recalls from memory; plainly tell Joey the lookup failed and "
            "that he can check his VIN at nhtsa.gov/recalls.")