"""
Web search via SerpApi, shared by every agent.

Returns a string starting with WEB_SEARCH_FAILED_PREFIX on real failure —
callers MUST check for this and tell the model the search failed, rather
than letting it answer as if a real (empty) search had succeeded. This is
the direct fix for Lesson #2's "phantom search" bug (NEXUS once fabricated
a refusal reason from a search that never actually ran).
"""
import os
from dotenv import load_dotenv
from serpapi import GoogleSearch

load_dotenv(override=True)  # Lesson #12: .env must win over a stale system env var
SERPAPI_KEY = os.getenv("SERPAPI_API_KEY")
WEB_SEARCH_FAILED_PREFIX = "[WEB_SEARCH_FAILED]"


def web_search(query: str, num_results: int = 3) -> str:
    try:
        params = {"q": query, "api_key": SERPAPI_KEY, "num": num_results, "hl": "en", "gl": "us"}
        results = GoogleSearch(params).get_dict()
        organic = results.get("organic_results", [])
        if not organic:
            return "[Web search ran successfully but found no results for this query.]"
        formatted = []
        for i, r in enumerate(organic[:num_results]):
            formatted.append(f"{i+1}. {r.get('title','')}\n   {r.get('snippet','')}\n   {r.get('link','')}")
        return "Web search results:\n\n" + "\n\n".join(formatted)
    except Exception as e:
        print(f"[WEB SEARCH ERROR] query={query!r} | {type(e).__name__}: {e}")
        return (
            f"{WEB_SEARCH_FAILED_PREFIX} The search itself failed and returned no data "
            f"({type(e).__name__}). Do not use memory or prior knowledge to answer as if "
            f"the search had succeeded — plainly tell the user the search failed."
        )