"""
Per-agent topic keyword lists, used with keyword_gate.py's
should_refuse(). Each agent has:
  - NON_TOPIC keywords: suggest the message belongs to a DIFFERENT agent
  - INTENT keywords: if present, override the refusal because the
    message is actually about THIS agent's topic despite a NON_TOPIC
    word appearing too (e.g. "workout program" shouldn't trip
    CIPHER's refusal just because "program" is in NON_CODING)

Pulled from the old chat_streaming.py's NON_CODING/NON_FINANCE/
NON_FITNESS/NON_AUTO/NON_LEGAL lists, cleaned up. FLAME, PULSE, and
STOCK never had a keyword gate in the old system — add lists here if
that changes during their Phase 4 build.
"""

CIPHER_NON_TOPIC = ["weather", "finance", "money", "fitness", "workout",
                     "car", "vehicle", "recipe", "food", "legal", "law"]
CIPHER_INTENT = ["code", "python", "script", "function", "program",
                  "app", "class", "algorithm", "debug", "refactor",
                  "write me a", "build a", "javascript", "html", "css",
                  "sql", "api", "backend", "frontend"]

ASSET_NON_TOPIC = ["weather", "fitness", "workout", "recipe", "food",
                    "car", "vehicle", "legal", "law", "code", "python"]
ASSET_INTENT = ["money", "budget", "spending", "invest", "stock",
                 "portfolio", "expense", "income", "savings", "debt",
                 "finance", "financial"]

ATLAS_NON_TOPIC = ["weather", "finance", "money", "car", "vehicle",
                    "recipe", "legal", "law", "code", "python"]
ATLAS_INTENT = ["workout", "fitness", "gym", "swim", "run", "exercise",
                 "training", "reps", "sets", "cardio", "strength",
                 "program", "routine"]

DRIVE_NON_TOPIC = ["weather", "stock market", "finance", "fitness",
                    "workout", "recipe", "food", "legal", "law",
                    "code", "python"]
DRIVE_INTENT = ["car", "vehicle", "engine", "oil change", "tire",
                 "brake", "mileage", "maintenance", "mechanic",
                 "transmission"]

CASE_NON_TOPIC = ["weather", "fitness", "workout", "car", "vehicle",
                   "recipe", "food", "code", "python"]
CASE_INTENT = ["legal", "law", "lawyer", "attorney", "contract",
                "lawsuit", "rights", "court", "statute", "regulation",
                "compliance"]

# Words that suggest a question needs CURRENT/live information, not
# just general programming knowledge — this is what makes CIPHER's
# web search conditional instead of firing on every message (old bug,
# same shape as Lesson #8's unconditional search call).
CIPHER_SEARCH_TRIGGERS = [
    "latest", "newest", "current version", "just released", "changelog",
    "recently released", "new release", "this year", "today", "right now",
    "new feature", "deprecated", "breaking change", "up to date", "up-to-date",
]

# Words that suggest the message is referencing something from a past
# session, not just the live conversation — this is what makes CIPHER's
# memory search conditional instead of firing on every message (same
# shape as the CIPHER_SEARCH_TRIGGERS fix, applied to memory retrieval).
CIPHER_MEMORY_TRIGGERS = [
    "remember", "recall", "we discussed", "we decided", "you said",
    "i said", "i told you", "last time", "before", "earlier",
    "previously", "like i mentioned", "as i mentioned", "what did i",
    "what did we", "we talked about", "we agreed",
]