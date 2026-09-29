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
                 "finance", "financial",
                 # Found during Phase 3 build: "how much do I spend on
                 # food" would otherwise wrongly refuse, since "food" is
                 # in ASSET_NON_TOPIC and neither "spend" nor "grocery"
                 # were here to override it (same shape as the
                 # "workout program" example in this file's own header).
                 "spend", "spent", "cost", "grocery", "groceries",
                 # Found by an actual L2 test this session: "pay off
                 # the car loan" wrongly refused, since "car" is in
                 # ASSET_NON_TOPIC (DRIVE's topic) and nothing here
                 # overrode it back to finance. Same bug shape, caught
                 # by testing exactly as intended.
                 "loan", "car loan", "car payment"]

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

# NEXUS's Python-side pre-detection for the ASK_CIPHER bridge — the
# ONLY bridge that exists yet, since CIPHER is the only other agent
# built so far. Pulled from the old chat_streaming.py's own CIPHER
# bridge list, used here with keyword_gate.py's word-boundary-safe
# contains_keyword() instead of the old plain substring check
# (Lesson #6 — flagged as a real gap back in Phase 2 kickoff notes).
NEXUS_CIPHER_BRIDGE_KEYWORDS = [
    "write me a script", "write me code", "fix this code", "debug this",
    "build me a", "python script", "how do i code",
]

# ASSET's real-data tool selection — which of its 9 real data-getters
# actually fire, based on what's being asked. Not an elif chain: every
# tool whose keywords match runs, same as the old system. Pulled from
# the old chat_streaming.py's plain substring checks, now word-boundary
# safe via keyword_gate.py's contains_keyword (Lesson #6).
ASSET_TOOL_KEYWORDS = {
    "spending_summary": ["spend", "spent", "expense", "cost", "groceries", "grocery"],
    "net_worth": ["worth", "total", "balance", "net worth"],
    "recent_transactions": ["transaction", "recent", "last", "latest", "history"],
    "income_summary": ["income", "paycheck", "pay", "salary", "wage"],
    "savings_rate": ["savings rate", "saving rate", "save", "saving"],
    "credit_score": ["credit score", "credit", "fico", "vantage"],
    "grocery_history": ["grocery", "groceries"],
    "emergency_fund": ["emergency fund", "emergency", "buffer", "3-month", "3 month", "6-month", "6 month"],
}

# ASSET's own web search is narrow on purpose (old comment: "Only used
# when Joey explicitly asks for news or rates") — unlike NEXUS's
# near-universal search, this stays trigger-gated, same shape as
# CIPHER_SEARCH_TRIGGERS.
ASSET_NEWS_TRIGGERS = [
    "news", "rate", "rates", "market", "economy", "inflation",
    "fed", "federal reserve", "stock market",
]



# ───────────────────────── ATLAS (Phase 4) ─────────────────────────

# ATLAS's web search is trigger-gated, like CIPHER's — it only fires when
# the message looks like a research/technique question. Carried over from
# the old code's RESEARCH_SIGNALS (plain substring matching there; whole
# word/phrase matching now — Lesson #6).
ATLAS_SEARCH_TRIGGERS = [
    "technique", "how to", "best way", "research", "tips", "recommend",
    "should i eat", "nutrition", "recovery", "what's the best",
    "how do i improve",
]

# "Show me my logged data" questions are answered DIRECTLY from the data
# file with no model call at all (old design: this is what stops ATLAS
# from ever inventing a workout count). The old check was a bare
# substring match on things like "how much" / "total" / "overall", which
# turned real coaching questions ("how much should I bench") into a data
# dump. Now a history question needs EITHER an explicit history phrase,
# OR a quantity word AND a logged-data subject together — and never fires
# when the message is asking for advice or reporting a new workout.
ATLAS_HISTORY_PHRASES = [
    "logged so far", "past workouts", "my workouts", "my swims",
    "my sessions", "my injuries", "my history", "swim history",
    "gym history", "injury history", "workout history", "all-time",
    "all time", "what have i done", "what have i logged",
    "progress so far",
]
ATLAS_HISTORY_QUANTITY = ["how many", "how much", "total", "overall", "in total", "so far"]
ATLAS_HISTORY_SUBJECTS = ["workouts", "sessions", "swims", "yards", "injuries", "logged", "swum"]
ATLAS_ADVICE_SIGNALS = [
    "should i", "can i", "how do i", "how should i", "how can i",
    "what's the best", "what is the best", "is it ok", "is it okay",
]
ATLAS_REPORT_PHRASES = [
    "just did", "just finished", "i did", "i swam", "i went", "did a",
    "finished a", "completed", "done with", "i lifted", "went to the gym",
    "just swam", "just lifted",
]

# Which slice of the data a history question is about.
ATLAS_SWIM_WORDS = ["swim", "swims", "swimming", "swam", "swum"]
ATLAS_GYM_WORDS = ["gym", "lift", "lifts", "lifting", "lifted"]
ATLAS_INJURY_WORDS = ["injury", "injuries", "injured"]



# ───────────────────────── DRIVE (Phase 4) ─────────────────────────

# DRIVE's web search is trigger-gated (the old code searched on EVERY
# message, wrapped in a bare except: pass — a live Lesson #2/#12 phantom-
# search risk). Now it only fires on things a search actually helps with.
DRIVE_SEARCH_TRIGGERS = [
    "recall", "how do i", "should i", "best way", "which", "compare",
    "review", "worth it", "how much does", "how much should", "safe to",
]

# "Show me my logged data" — answered directly from the data file, no
# model call, same reasoning as ATLAS: a model can't invent a number it
# never gets to write. Needs an explicit history phrase, or a quantity
# word AND a logged-data subject together — never on advice or a new
# report of work just done.
DRIVE_HISTORY_PHRASES = [
    "maintenance history", "maintenance log", "service history",
    "gas history", "gas log", "fill-up history", "my mileage",
    "current mileage", "open issues", "what have i logged",
    "what's due", "what is due", "upcoming maintenance",
    "all-time", "all time",
]
DRIVE_HISTORY_QUANTITY = ["how many", "how much", "total", "overall", "in total", "so far"]
DRIVE_HISTORY_SUBJECTS = ["oil changes", "fill-ups", "fillups", "services", "logged", "spent on gas"]
DRIVE_ADVICE_SIGNALS = [
    "should i", "can i", "how do i", "how should i", "how can i",
    "what's the best", "what is the best", "is it ok", "is it okay",
    "worth it", "recommend",
]
DRIVE_REPORT_PHRASES = [
    "just did", "just got", "just filled", "just topped", "i got",
    "i did", "i filled", "i topped", "i added", "got an", "got a",
    "just changed", "just replaced", "finished", "completed",
    "done with", "went to the", "they did", "they changed", "they rotated",
]

# Which slice of the data a history question is about.
DRIVE_MAINTENANCE_WORDS = ["maintenance", "service", "oil change", "tire rotation", "repair"]
DRIVE_GAS_WORDS = ["gas", "fuel", "fill-up", "fillup", "mpg", "gallon"]
DRIVE_ISSUE_WORDS = ["issue", "issues", "problem", "noise", "warning light"]