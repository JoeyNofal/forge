# NEXUS SYSTEM — LESSONS LEARNED (READ BEFORE REBUILDING)
# Purpose: every recurring real bug pattern found across the original
# NEXUS build, extracted so the rebuild avoids repeating them — not as
# retrofits after the fact, but built in from the first line of code.
# Paste this whole document into any NEXUS 2.0 build session.

---

## 1. Bridge/wrapper code must call the SAME function as direct chat — never a parallel copy

**What happened:** NEXUS's own bridges to ATLAS, DRIVE, FLAME, CASE, CIPHER,
and (found much later, separately) ASSET all started as standalone files
calling raw Ollama on an old model directly — completely bypassing every
personality rewrite, hallucination fix, and tool upgrade made to the real
agents for months. Nobody noticed until a specific feature (image support)
happened to test that exact path end-to-end for the first time.

**Rule for the rebuild:** the moment NEXUS calls a specialist agent, it
calls the *exact same function* that agent's own direct chat uses. No
agent gets its own second implementation of "how it answers a question."
If a bridge needs to exist for architectural reasons (e.g. converting a
generator into a single return value), it should be a thin wrapper around
the real function, never a re-implementation.

---

## 2. Retrieved memory/context must be explicitly labeled as background, never presented as fact

**What happened:** this exact bug appeared at least four separate times,
independently, in different agents, because the fix was never built in
from the start — only patched after each incident:
- NEXUS insisting on a fake location ("Hickory Hills") after GPS was already fixed
- NEXUS confidently claiming to be "LLaMA via Ollama" months after migrating to Gemini/Sonnet
- ASSET's cross-chat memory overriding what was actually just said in the current chat
- NEXUS fabricating a refusal reason (a phantom web search that never happened) while misdating a real old memory as current

**Root cause every time:** search results / recalled memory get spliced
into the prompt with no framing distinguishing them from the live,
trusted conversation. The model treats stale or unrelated background
content as equally authoritative to what the user just said.

**Rule for the rebuild:** every place memory or search results get
injected into a prompt, wrap them explicitly: *"background context, may
be outdated or unrelated — the current conversation is authoritative."*
Do this for every agent from day one, not after the first hallucination
report.

---

## 3. Unfiltered memory-saving creates self-reinforcing false memories

**What happened:** agents that saved every single turn to permanent
memory (no filter) occasionally saved a hallucinated or wrong statement.
That wrong statement then got recalled on a similar future question,
restated, and saved *again* — compounding across turns until it became
the agent's confident "truth." Happened to CIPHER (invented a fake
approval rule) and to NEXUS (self-identity claims).

**Rule for the rebuild:** filter what's actually worth saving (goals,
decisions, preferences, corrections) before writing to permanent memory.
Routine turns don't need to be remembered forever, and unfiltered saving
is what let bad information compound.

---

## 4. Every shared JSON file needs real file locking, from the first write

**What happened:** `pending_tasks.json`, `fitness.json`, and
`reminders.json` all used a load-modify-save pattern with no protection.
Two simultaneous writes could each read the same "before" state and one
would silently overwrite the other — no crash, no error, just missing
data. Found via deliberate concurrency testing (L4/L5), not everyday use,
which means it could have been silently losing data for a long time
without anyone noticing.

**Rule for the rebuild:** use a file-locking library (`filelock`) around
every read-modify-write cycle on a shared data file, as a standard part
of how any new data file is built — not something added after a stress
test finds the gap.

---

## 5. Extraction/generation prompts need an exact output shape, and downstream code needs to defend against getting it wrong anyway

**What happened:** the gym-workout JSON extraction prompt said
`"exercises": []` but never specified what should be *inside* the list.
The model filled the gap by guessing plain strings instead of proper
objects. That malformed data sat quietly in the real data file until a
completely unrelated live conversation crashed the whole agent, because
downstream code assumed every exercise was a dict and indexed it like one.

**Rule for the rebuild:** every structured-extraction prompt gets an
explicit example of the exact shape wanted. Separately — and just as
important — every function that *reads* that data checks the shape
before trusting it (`isinstance(x, dict)` checks, safe numeric
conversion), so a single malformed entry can never take the whole agent
down.

---

## 6. Keyword gates need word-boundary matching, not substring matching

**What happened:** hard refusal lists used plain substring checks
(`"code" in message`), which wrongly blocked real requests — a legitimate
coding question mentioning "food" got refused by CIPHER, a legitimate
finance question about a "program" got refused by ASSET, a real fitness
question about a "workout program" got refused by ATLAS.

**Rule for the rebuild:** keyword-based routing/refusal needs either
whole-word matching or a proper intent check — never a bare `in` on
partial strings. Worth building as one shared, tested helper function
used by every agent, instead of each agent reinventing its own keyword
list with the same class of bug.

---

## 7. Secrets never go directly in source files

**What happened:** real API keys (SerpApi, Gemini, Anthropic) ended up
hardcoded directly into 7+ different files, some duplicated across
multiple agents. No `.env`, no `.gitignore`, no central place — meaning
any accidental sharing, screenshot, or future git repo would have leaked
real, funded credentials.

**Rule for the rebuild:** one `.env` file, one `.gitignore`, from the
very first commit — not a cleanup pass done after the fact once a repo
becomes a real possibility.

---

## 8. Test each feature fully (L1-L5) in the same session it's built — not months later

**What happened:** this is the core process issue this whole rebuild is
responding to. CIPHER was tested roughly two months after being built.
ATLAS went untested for months and turned out to be missing basic
safeguards (no memory filter, no history bypass, an unconditional web
search call, a genuine production-crashing data bug) that had already
been proven necessary in other agents built around the same time — the
lesson from one agent never made it into the next because there wasn't a
testing checkpoint forcing the comparison.

**Rule for the rebuild:** no feature is "done" until it's passed its own
L1-L5 pass, in the same session (or the very next one) it was built in.
Nothing new gets built on top of an untested feature.

---

## 9. Delete dead code as you go — don't "keep it for reference"

**What happened:** old standalone bridge files sat unreferenced on disk
for months after being replaced, duplicate endpoint definitions existed
silently (the second one just never ran), and throwaway diagnostic
scripts lingered in real project folders. None of this caused active
bugs by itself, but it made "what's actually live right now" genuinely
hard to know for certain, and cost real debugging time more than once.

**Rule for the rebuild:** once something is confirmed replaced, delete
it. Rely on backups/git history for "what did this used to look like,"
not a growing pile of unused files sitting next to the real ones.

---

## 10. Always view the real, current file before editing it — never edit from memory or an old paste

**What happened:** more than once, an edit was proposed against a
slightly stale copy of a file (proposed from an earlier message, or from
what a completion record *said* the file should look like), and the
find-and-replace either silently failed to match or applied wrong.

**Rule for the rebuild:** before editing any file that's been touched in
a prior session, get the real current contents first. This already is a
stated rule in the old project — it just wasn't followed consistently
enough.

---

## 11. Shared code across multiple model providers needs one normalized convention, converted at the edges

**What happened:** a multi-step tool loop hardcoded Gemini's internal
role name (`"model"`) directly into shared conversation-history code.
The moment that same code ran against Claude instead of Gemini, Claude's
API rejected it outright — silently falling back to local Ollama with
*zero visible error* for an unknown period of time, quietly degrading
every multi-step Paid Cloud conversation and undercounting real spend the
whole time.

**Rule for the rebuild:** pick one internal role convention
(`"user"`/`"assistant"`) for all shared logic, and only convert to a
specific provider's exact format at the single point where that
provider's API is actually called — never let a provider-specific string
leak into code meant to be provider-agnostic.

---

## 12. "Looks like an auth error" isn't always an auth error

**What happened:** at least twice, a confusing 401/authentication-shaped
error turned out to actually be an account balance issue, and once (very
recently) turned out to be a completely unrelated bug — a stale Windows
system-level environment variable silently overriding a correct `.env`
file, because the code didn't tell `load_dotenv()` to prefer the file
over an existing system value.

**Rule for the rebuild:** when a key "looks wrong," check three things in
order before assuming the key itself is bad: (1) is there real balance on
the account, (2) is something else (a system env var, a second config
file) silently overriding the value you think is being used — verify
with a `repr()`-style print of the actual loaded value, not just a
successful file save, (3) only then assume the key itself needs
regenerating.
