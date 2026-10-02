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

# ── ATLAS logging triggers (increment (b), Part 3) ──
# These only decide whether ATLAS even TRIES to turn a message into a log
# proposal (a cheap pre-filter, whole-word matching — Lesson #6). The local
# model then decides whether it's really a report (it can answer "none"),
# and nothing is saved until Youssef approves anyway.

# "I already did a workout" phrasings. (ATLAS_ADVICE_SIGNALS blocks planning
# questions like "what should I lift".)
ATLAS_WORKOUT_REPORT_PHRASES = [
    "just did", "just finished", "i did", "i swam", "i went", "did a",
    "finished a", "completed", "done with", "i lifted", "went to the gym",
    "just swam", "just lifted", "today i", "this morning i", "last night i",
    "yesterday i", "i hit", "i benched", "i squatted", "i deadlifted",
    "i pressed", "i trained", "i worked out", "got back from the gym",
    "just got back from", "did chest", "did back", "did legs", "did arms",
    "did shoulders", "hit chest", "hit back", "hit legs",
]

ATLAS_BODY_PARTS = [
    "shoulder", "shoulders", "knee", "knees", "back", "lower back", "hip",
    "hips", "elbow", "elbows", "wrist", "wrists", "ankle", "ankles", "neck",
    "hamstring", "hamstrings", "quad", "quads", "calf", "calves", "groin",
    "bicep", "biceps", "tricep", "triceps", "forearm", "forearms", "chest",
    "pec", "pecs", "glute", "glutes", "rotator cuff", "achilles", "shin",
    "shins", "foot", "feet", "hand", "hands", "thumb", "finger", "fingers",
    "ribs", "lat", "lats", "trap", "traps", "hip flexor",
]

ATLAS_INJURY_REPORT_WORDS = [
    "hurts", "hurt", "hurting", "sore", "soreness", "pulled", "strained",
    "strain", "tweaked", "injured", "injury", "pain", "painful", "aches",
    "aching", "ache", "pinch", "pinched", "sprained", "twisted", "swollen",
    "clicking", "popping",
]

# "It's getting better" phrasings — these mean UPDATE an existing injury,
# not log a new one.
ATLAS_INJURY_RECOVERY_PHRASES = [
    "better", "feels better", "feeling better", "getting better", "healed",
    "recovered", "no longer", "doesn't hurt", "does not hurt", "not sore",
    "no more pain", "back to normal", "resolved", "pain free", "pain-free",
    "improving", "improved", "feels fine", "is fine", "are fine",
]



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

# ── DRIVE logging (increment (b), Part 3b) ──
# PRE-FILTERS ONLY: a cheap whole-word check on whether a message is worth a
# local-model call. A false alarm costs one model call (the model still says
# "none"); a miss means a report is never offered for logging, so these lean
# generous. All matching goes through contains_keyword (Lesson #6).
DRIVE_MILEAGE_WORDS = ["miles", "mileage", "odometer"]
DRIVE_FILLUP_WORDS = [
    "fueled up", "fuelled up", "filled up", "filled her up", "filled it up",
    "filled the tank", "fill up", "fill-up", "fillup", "topped off", "topped up",
    "pumped", "gallons", "gallon", "gal",
]
DRIVE_SERVICE_WORDS = [
    "service", "services", "serviced", "oil change", "oil changed", "changed the oil",
    "changed my oil", "tire rotation", "tires rotated", "rotated", "rotation", "new tires",
    "tires", "brakes", "brake", "brake pads", "new brakes", "battery", "new battery",
    "air filter", "cabin filter", "filter", "wiper blades", "wipers", "spark plugs",
    "coolant", "transmission", "alignment", "tune-up", "tune up", "inspection",
    "flushed", "repair", "repaired", "mechanic", "dealership",
]
DRIVE_SERVICE_DONE_SIGNALS = [
    "got", "had", "just", "changed", "replaced", "rotated", "flushed", "serviced",
    "installed", "done", "did", "finished", "completed", "bought", "put on",
    "swapped", "fixed",
]
DRIVE_ISSUE_SYMPTOM_WORDS = [
    "light is on", "light came on", "light's on", "warning light", "check engine",
    "engine light", "tire pressure", "noise", "noises", "grinding", "squeaking",
    "squealing", "squeaks", "rattling", "clunking", "buzzing", "vibrating",
    "vibration", "shaking", "leaking", "leak", "won't start", "wont start",
    "stalling", "stalled", "overheating", "smoke", "smoking", "smell", "smells",
    "flat", "pulling", "dead battery", "slipping", "jerking", "rough idle",
    "knocking", "ticking", "whining", "humming", "something wrong", "not working",
    "broken",
]
# "100%" is handled separately in drive_extract (a percent sign has no word boundary).
DRIVE_ISSUE_RESOLVED_PHRASES = [
    "fixed", "got fixed", "is fixed", "resolved", "went away", "is gone", "are gone",
    "no longer", "stopped", "all good", "all fixed", "everything's fixed",
    "everything is fixed", "fully fixed", "working again", "back to normal",
    "not on anymore", "went off", "light is off", "repaired", "taken care of",
    "sorted", "gone now", "all clear",
]
# A fixed command (no model call): proposes ONE "Brake Inspection, due today" reminder.
DRIVE_BRAKE_REMINDER_PHRASES = [
    "add a brake reminder", "set a brake reminder", "brake reminder",
    "remind me about my brakes", "remind me about the brakes",
    "remind me to check my brakes", "remind me to check the brakes",
]