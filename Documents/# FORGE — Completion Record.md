# FORGE — Completion Record
# (formerly "NEXUS SYSTEM v2" / "NEXUS 2.0" rebuild)

## Session 1 — Project Setup & Open Decisions

### Decided
1. **Project name:** FORGE — used for both the Claude Project and the
   Windows folder name.
2. **Old NEXUS SYSTEM keeps running day-to-day** during the rebuild.
   Youssef won't be chatting with agents much but will keep using the
   companion apps, so no full switch-over is needed — old and new run
   in parallel until FORGE agents are ready to take over.
3. **Tech stack: no change.** Python/FastAPI backend, Ollama for local
   models, Electron for the desktop shell all carry over as-is.
   Confirmed after comparing Ollama against alternatives (LM Studio,
   vLLM, llama.cpp) — Ollama remains the right fit for a single-user,
   single-machine, code-driven setup. ("Hermes" was clarified as a
   *model* that can run inside Ollama, not a competing runtime — not
   an architecture change.)
4. **Git repo:** set up now (JoeyNofal/forge on GitHub, public, empty)
   rather than waiting for Phase 1 — reasoned as "easiest," since
   Phase 0 already involves setting up `.env`/`.gitignore` at the same
   time.
   - IMPORTANT: real API keys must never be pushed to this repo —
     `.gitignore` must be in place from the first commit (Lesson #7).
5. **Testing rule confirmed with no exceptions:** every feature,
   including Phase 0's shared guardrail utility functions, gets at
   least one full L1-L5 test pass before anything is built on top of
   it.

### New features added to scope (not in the original Rebuild Plan)
6. **Instagram reel idea-extractor** — paste a reel link, the system
   downloads it (yt-dlp, public link only, no login, no automatic
   polling — manual/occasional use only to keep IG ToS risk low),
   transcribes speech (Whisper) and/or analyzes video frames, produces
   an idea summary, and NEXUS routes it to the right agent (recipe →
   FLAME, workout → ATLAS, car tip → DRIVE, etc.) and saves it to a
   running idea list.
   - Scoped as a **NEXUS** capability (NEXUS is the router/hub).
7. **Task scheduler / crontab** (recurring automated jobs, reminders).
8. **Expert / sub-agent spawning** (an agent can spawn a temporary
   helper sub-agent for a complex task instead of staying one flat
   conversation).
9. **Plugin/skill marketplace pattern** (a formal "install a new
   capability" system, vs. hand-building every capability directly
   into an agent like the original build did).
   - Decision: features 7-9 get built into **all 9 agents**, each
     during that agent's own Phase 1-4 build (not bolted on later).

### Research done
- Compared Ollama vs. LM Studio vs. vLLM vs. llama.cpp — Ollama
  confirmed as the right choice, no change.
- Cloned and reviewed 3 open-source reference projects for patterns
  (not for direct copy — reference only, per Youssef's "simplify into
  a feature list, pick what we want, rest stays reference" approach):
  - **QwenPaw** (agentscope-ai/QwenPaw) — validated the idea of
    keeping security/guardrail code in its own dedicated module
    rather than scattered per-agent (supports the Phase 0 approach).
  - **PyGPT** (szczyglis-dev/py-gpt) — plugin folder is a useful
    checklist of "companion app as plugin" ideas (task scheduler,
    file commands, multiple experts/personas, audio I/O).
  - **local-ai-personal-assistant** (tyspinky) — small, readable
    example of a memory layer implementation, useful reference for
    Lesson #2/#3 (memory labeling, filtered saving) once that phase
    starts.

### Standing rules for this project (reconfirmed)
- Claude does not create files — gives code/text in chat, Youssef
  creates the actual files in VS Code.
- No feature is "done" until it has a full L1-L5 test pass, in the
  same session it was built or the very next one.
- All shared guardrails from NEXUS_LESSONS_LEARNED.md apply by default
  to everything built, without needing to be asked for each time.

## Not yet decided / still open
- Phase 0 scope details (exact design of the keyword-matcher, memory-
  labeler, file-locker helpers) — not yet started.
- Whether to dig into additional reference repos beyond the 3 above
  (a few more were found in search but not yet cloned/reviewed).
- Reel idea-extractor: still needs the "how it's saved / what the idea
  list looks like" detail worked out before building.

  # FORGE — Completion Record
# (formerly "NEXUS SYSTEM v2" / "NEXUS 2.0" rebuild)

## Session 1 — Project Setup & Open Decisions

### Decided
1. Project name: FORGE — Claude Project name and Windows folder name.
2. Old NEXUS SYSTEM keeps running day-to-day during the rebuild
   (Youssef mainly uses the companion apps, not direct agent chat).
3. Tech stack confirmed no change: Python/FastAPI, Ollama, Electron.
   Ollama confirmed as the right runtime after comparing against
   LM Studio/vLLM/llama.cpp. ("Hermes" clarified as a model, not a
   competing runtime.)
4. Git repo: github.com/JoeyNofal/forge — public, set up in Phase 0
   rather than deferred to Phase 1.
5. Testing rule, no exceptions: every feature — including small Phase
   0 utility functions — gets at least one full L1-L5 pass before
   anything builds on top of it.
6. Bug-fix philosophy: patch the old NEXUS SYSTEM directly only when a
   bug is actively affecting daily use (done once: ASK_STOCK stale
   bridge). FORGE gets built correctly from scratch during its own
   phases — no porting patches over.

### New features added to scope
7. Instagram reel idea-extractor (NEXUS capability) — paste a link,
   download (yt-dlp, public/no-login/manual only, to keep IG ToS risk
   low), transcribe/analyze, route to the right agent, save to an idea
   list. Not yet built — still scoped for a later phase.
8. Task scheduler/crontab, expert/sub-agent spawning, plugin/skill
   marketplace pattern — to be built into all 9 agents, each during
   that agent's own Phase 1-4 build. Not yet started for any agent.

### Standing project rules
- Claude never creates files in this project — gives code/text in
  chat only, Youssef creates every file himself in VS Code.
- Every code fix is given as an explicit FIND block and REPLACE block
  — never prose description of a change.
- No feature is "done" until it has a full L1-L5 pass, same session
  or the next one.

---

## Session 2 — Phase 0: Shared Guardrail Functions

### Research
- Reviewed real old-system code (chat_streaming.py, nexus_tools.py,
  atlas_memory.py, atlas_tools.py, pending_tasks.py, agent_prompts.json,
  requirements.txt) — pushed to github.com/JoeyNofal/forge/reference/
  for permanent reference.
- Findings from the real code (not narrative — actual inspection):
  - File locking (Lesson #4) — already correctly implemented in
    pending_tasks.py and atlas_tools.py using FileLock.
  - Bridges (Lesson #1) — already correct for 6 of 7 agents via
    call_agent_bridge() → _collect_stream(). **ASK_STOCK was still
    using the old broken standalone bridge — a real, live bug.**
  - Keyword gates (Lesson #6) — confirmed still broken in all 5
    agents that have one (CIPHER, ASSET, ATLAS, DRIVE, CASE) — plain
    substring matching, exactly the old bug pattern.
  - Memory labeling (Lesson #2) — only ATLAS had the "background
    context" framing. CIPHER/ASSET/DRIVE/FLAME/CASE/PULSE did not.
  - Unfiltered memory saving (Lesson #3) — confirmed still live in
    atlas_memory.py.
- Cloned 3 open-source reference projects (QwenPaw, PyGPT,
  local-ai-personal-assistant) for architecture pattern ideas —
  reference only, no code copied directly.

### Built (all in forge/shared/)
- keyword_gate.py — word-boundary-safe keyword matching, fixes
  Lesson #6.
- memory_context.py — labels retrieved memory as background, fixes
  Lesson #2; is_memory_worthy() filter, addresses Lesson #3.
- file_store.py — locked read-modify-write JSON helper, standardizes
  the working FileLock pattern from Lesson #4.
- agent_topics.py — per-agent NON_TOPIC/INTENT keyword lists for
  CIPHER, ASSET, ATLAS, DRIVE, CASE (pulled and cleaned from the real
  old code).
- .env.example and .gitignore — set up from the start (Lesson #7).

### Live bug fixed (in the OLD NEXUS SYSTEM directly, per the bug-fix
philosophy above)
- ASK_STOCK now routes through _collect_stream(stream_stock, ...)
  instead of the old broken standalone bridge.

### Tested — Phase 0 CONFIRMED CLOSED
- L1 (static), L2 (smoke), L4 (sustained/concurrency — 10 simultaneous
  threads, zero data loss), L5 (extreme/breaking — corrupted JSON
  fails loudly, crash-mid-write doesn't corrupt original data) all
  passed on Youssef's real machine.
- L3 flagged as not yet meaningful — Phase 0 functions aren't wired
  into a live agent yet; real L3 happens once Phase 1 code actually
  uses them.

---

## Session 3 — Phase 1: CIPHER (core chat)

### Scope decisions
- Per-agent folder structure: forge/agents/<agent>/, not one giant
  file like the old chat_streaming.py.
- Real file-write/command execution: kept gated behind a NEXUS
  approval workflow (same safety pattern as the old system) — not
  built directly into CIPHER's direct chat. Not yet built (depends on
  NEXUS, Phase 2).
- Memory: deferred as its own tested increment — CIPHER's first build
  proves core chat correctness with zero memory involved.
- Model tier: hardcoded to Free Cloud (Gemini 2.5 Flash) for now —
  Local and Paid Cloud tiers deferred as their own increments.
- Web search: made conditional (CIPHER_SEARCH_TRIGGERS keyword list)
  instead of firing on every message like the old system did (same
  bug shape as Lesson #8's unconditional search call).

### Built
- forge/agents/cipher/prompt.py — CIPHER's existing JARVIS-voice
  personality prompt, carried over unchanged (4,480 characters,
  verified against the reference file).
- forge/agents/cipher/chat.py — stream_cipher(): keyword gate check,
  conditional web search, calls shared Gemini client, strips
  SAVE_FILE/RUN_COMMAND markers into a placeholder (since real
  execution isn't built yet). No memory persistence — caller owns
  history.
- forge/shared/web_search.py — SerpApi search with a WEB_SEARCH_FAILED
  marker, directly fixing Lesson #2's "phantom search" bug.
- forge/shared/model_client.py — Gemini streaming client. Provider
  role-name conversion ("model") isolated to one single function per
  Lesson #11. Fails loudly on a missing API key rather than silently
  depending on the SDK's own fallback (a real near-miss caught during
  testing — .env variable was named GOOGLE_API_KEY, code expected
  GEMINI_API_KEY; it "worked" by accident via a hidden SDK fallback
  until this was found and fixed).
- .env variable renamed to GEMINI_API_KEY to match; load_dotenv(...,
  override=True) added to model_client.py and web_search.py per
  Lesson #12.

### Real bugs caught and fixed during setup (VS Code / packaging, not
FORGE logic)
- Git/PATH and folder-location errors during initial repo setup —
  resolved.
- Python package import structure — imports originally written as
  `forge.shared.X` didn't match the real folder layout (repo root IS
  the forge folder, no nested forge/ subfolder) — fixed to `shared.X`
  / `agents.cipher.X`.
- Test script bug (not a chat.py bug): a "simulate API failure" L5
  test initially patched the wrong module reference and always passed
  vacuously — fixed to patch chat.py's own imported reference.

### Tested — CIPHER Phase 1 core chat CONFIRMED, L1 through L5
- L1/L2: 12/12 passed (mocked model/search, no real keys needed).
- L3 (real live APIs, Youssef's real keys): 5/5 real test cases
  correct — real working prime-check code, clean refusal on
  off-topic, old "workout program" substring bug confirmed fixed,
  real current web-search-backed answer (Python 3.14.7, verified
  independently as accurate), correct multi-turn history recall.
- L4: 100 sequential calls zero crashes/zero empty responses; 20
  simultaneous threads, zero cross-talk between concurrent calls.
- L5: empty message, 50,000-char message, unicode/emoji, None input,
  malformed history, and a simulated model/API failure all handled
  correctly — fails loudly where it should, never silently swallows
  an error or produces garbage output. Refusal gate re-verified intact
  after all extreme-input tests.

## Not yet decided / still open
- CIPHER's memory (save + retrieval) — next increment, not yet
  started.
- Whether to build CIPHER's memory now (closing out everything CIPHER
  can do solo) or move to Phase 2 (NEXUS) first — open question as of
  end of this session.
- NEXUS's approval workflow (Tier 1/2, gates real file-write/command
  execution) — not started, depends on Phase 2.
- Instagram reel extractor and the scheduler/sub-agent/plugin features
  — still scoped, not started for any agent.

  Session 4 — CIPHER Memory, Model-Tier Switching, Phase 2 Kickoff
Built and tested — CIPHER memory (Lesson #2/#3, deferred from Session 3)
shared/cipher_memory.py — ChromaDB storage, filtered saving (only decision/correction/preference/project_fact categories persist — fixes Lesson #3 directly). Embeddings run through Ollama (nomic-embed-text), not ChromaDB's default — decided for local-first consistency over the one-time-download convenience of the default.
agents/cipher/chat.py — inline MEMORY_SAVE marker in CIPHER's own response (no extra classification API call), retrieval only triggered when a message looks like it's referencing something past (CIPHER_MEMORY_TRIGGERS in shared/agent_topics.py). Also fixed a real live Lesson #2 gap found along the way: web search results weren't wrapped in the "background, may be outdated" label — now they are.
agents/cipher/prompt.py — added the MEMORY_SAVE marker instructions.
shared/memory_context.py — added project_fact to MEMORY_WORTHY_CATEGORIES.
Two real bugs caught in L5 and fixed: unbounded content length crashed Ollama's embedding call (fixed with a 2000-char cap + truncation), and an empty search query crashed ChromaDB indexing (fixed by short-circuiting to no results).
Tested — CONFIRMED CLOSED: L1/L2 mocked 21/21, L3 real end-to-end 6/6 (real Gemini + real Ollama embeddings), L4/L5 10/10 (20 concurrent saves, both real bugs above found and fixed here).
Built and tested — CIPHER model-tier switching (Local/Free Cloud/Paid Cloud)
shared/api_budget.py — ported from the old system's real proven dashboard/api_budget.py (rollover-forever $10/day cap, 50/80/90% warnings, hard stop, per-agent tier overrides) — but pointed at a completely fresh database (D:\Projects\forge\data\chat_history.db), deliberately not shared with the old NEXUS SYSTEM's tracker.
shared/model_client.py — extended with stream_ollama, stream_claude, and a stream_by_tier() router, ported from the old system's real proven chat_streaming.py. One deliberate deviation from the old code: Paid Cloud → Local fallback on a real API failure is now visible (yields a clear warning first), never silent — the old silent version was literally the Lesson #11 bug.
agents/cipher/chat.py — stream_cipher() now takes an optional model_tier param; None resolves to CIPHER's live default (paid_cloud, matching old-system precedent).
Tested — CONFIRMED CLOSED: L1/L2 mocked 22/22, L4/L5 8/8 (confirmed SQLite's own locking prevents lost updates under 20 concurrent budget writes — the Lesson #4 risk didn't materialize, but was actually checked rather than assumed), real L3 6/6 across all three tiers (real Ollama, real Gemini, real Sonnet 5 call — ~$0.013, balance moved $10.00 → $9.98686 — including memory+search still working correctly when routed through Paid Cloud).
CIPHER Phase 1 status: complete

Only remaining piece is real file-write/command-execution, which stays blocked on NEXUS's approval workflow (Phase 2) actually existing.

Phase 2 (NEXUS) — scoped, not yet built

Decisions made before any code was written:

Core chat first, same phased approach as CIPHER's Session 3 — tool detection (reminders/search/app-launch), the 8 agent-bridge keyword lists, the approval workflow, and the multi-step tool loop are all separate later increments, not built in one shot.
NEXUS's old bridge-detection keyword lists in reference/chat_streaming.py use plain substring matching (e.g. "swim", "vehicle") — confirmed as the same Lesson #6 bug shape CIPHER's keyword gate already fixed. Will need the same word-boundary treatment when bridges are actually built, not a straight port.
NEXUS's system prompt: carrying over the old NEXUS_PROMPT_DEFAULT (Alfred Pennyworth voice) unchanged for now, same precedent as CIPHER's prompt.py.
NEXUS gets model_tier wired in from day one (not hardcoded to one tier like CIPHER's Session 3 start) — trivial now since stream_by_tier already exists.
NEXUS's memory deferred as its own tested increment after core chat, same split as CIPHER.
Not yet decided / still open
Exact shape of NEXUS's core-chat increment (what stays in scope vs. gets deferred beyond what's listed above) — not yet worked out in detail.
Reel idea-extractor, task scheduler/crontab, expert/sub-agent spawning, plugin/skill marketplace — still scoped from Session 1, not started for any agent.
NEXUS's approval workflow (Tier 1/Tier 2) — not started; this is also what unblocks CIPHER's last remaining piece.

## Session 5 — Phase 2: NEXUS (core chat, memory, model-tier switching, bridges) + CIPHER real actions

### NEXUS Phase 2 — Core chat
Built: agents/nexus/prompt.py (NEXUS_PROMPT_DEFAULT, Alfred Pennyworth
voice, carried over completely unchanged — including its
reminder/app/file/bridge/record-keeping tool-command instructions,
which FORGE hasn't built processors for yet), agents/nexus/chat.py
(strip_unexecuted_action_markers() replaces every unbuilt marker type
with one clear placeholder before saving to history; web search fires
on nearly every message, matching the old system's real behavior, made
safe via shared/web_search.py's WEB_SEARCH_FAILED_PREFIX marker so a
real failure is never silently swallowed).

Decision: NEXUS's live default model tier changed from the old
system's paid_cloud to free_cloud.

Tested — CONFIRMED CLOSED, L1 through L5:
- L1/L2: 12/12 mocked.
- L3: real Gemini + real SerpApi — Alfred voice confirmed natural, real
  weather search hit a real South Bend-area PWS station and hedged
  appropriately on unclear data, SET_REMINDER/ASK_ASSET markers
  correctly stripped for history, no invented figures, multi-turn
  history recall correct.
- L4/L5: 100 sequential + 20 concurrent calls clean (including a
  NEXUS-specific per-call-search cross-talk check since NEXUS searches
  every message, unlike CIPHER); empty/50k-char/unicode/None all
  handled correctly; malformed history fails loudly with a clear
  KeyError (confirmed for real by fixing an initially-too-lenient
  mock); all 17 marker types stripped correctly at once.

### NEXUS Phase 2 — Memory
Decisions: 7 of 8 shared categories accepted (all except
financial_fact — ASSET's exclusive domain); retrieval fires
near-universally like search, not trigger-gated like CIPHER's; same
inline MEMORY_SAVE marker mechanism as CIPHER.

Refactor alongside this build: OllamaEmbeddingFunction +
OLLAMA_EMBED_URL/OLLAMA_EMBED_MODEL/MAX_MEMORY_CONTENT_CHARS extracted
out of shared/cipher_memory.py into new shared/ollama_embeddings.py
(Lesson #9 — merged while it was still just 2 files). shared/nexus_memory.py
built on top of the shared module — own ChromaDB collection, isolated
from CIPHER's per Lesson #3.

Real bug found and fixed: financial_fact's exclusion only lived in
chat.py's extractor, not in save_memory() itself — a direct call with
that category would have succeeded. Fixed by enforcing the exclusion
at the storage layer too (defense in depth).

Tested — CONFIRMED CLOSED, L1 through L5:
- L1/L2: 20/20.
- L3: 6/6 real Ollama embeddings + real Gemini — semantic search
  correctly ranked the relevant saved fact over an unrelated one, real
  response used retrieved memory unprompted with no trigger keyword
  present, a real $4,300 balance mention correctly routed to
  ASK_ASSET and never saved to NEXUS's own memory.
- L4/L5: 12/12 (11/12 first pass, one real gap — see above — found and
  fixed).

### NEXUS Phase 2 — Model-tier switching
Needed zero new code — stream_by_tier/record_usage were already
agent-generic from CIPHER's Session 4 build. Confirmed real
end-to-end (7/7): Local/Free Cloud/Paid Cloud all work, usage
correctly attributed to agent='nexus', memory+search still work when
routed through Paid Cloud.

### Scope expansion: CIPHER's real file-write/command-execution
Originally deferred to "Phase 2's approval workflow" — built now
since NEXUS exists, but SIMPLIFIED from the old system's tiered
permission model to ONE rule (Youssef's decision): approval required
ONLY for creating a file or running a command, nothing else, no
allow/deny command lists, no Tier 1/Tier 2 distinction.

Built: shared/pending_actions.py (generic locked JSON queue, reusable
by future agents, uses shared/file_store.py's Lesson #4 locking) +
agents/cipher/cipher_tools.py (propose_create_file/propose_run_command
create a pending action with zero real effect; approve_and_execute()
is the ONLY function that touches disk/runs a process; deny_action()).
agents/cipher/chat.py updated: SAVE_FILE/RUN_COMMAND markers now go
through extract_pending_actions()/strip_action_markers() (real,
proposes+waits for approval) instead of being placeholder-stripped.

Real race condition found and fixed: approve_and_execute() read
status, executed, then resolved — no atomic claim step, so two
near-simultaneous approvals of the SAME action could both pass the
pending check and both execute for real. Fixed with
claim_action()/finalize_action() (atomic claim before execution).
Confirmed under a real 20-thread race test: exactly one execution, 19
correctly blocked.

Real bug caught in review (not by a failing test): deny_action() was
left calling resolve_action() after that import got swapped for
claim_action/finalize_action — a NameError waiting to happen. Fixed by
keeping resolve_action imported alongside the new two.

Systemic bug found and fixed everywhere: on Windows, plain
open(f).read() defaults to cp1252, not UTF-8 — broke the instant
chat.py gained a ⏳ emoji. Fixed across every L1 static-parse test with
encoding="utf-8" explicitly (test_cipher_actions.py, test_cipher.py,
test_nexus.py, test_cipher_memory.py, test_nexus_memory.py).

Tested — CONFIRMED CLOSED, L1 through L5 (24/24, 9/9, 10/10 across the
tiers) — real file writes and real harmless commands, always against
throwaway temp paths in testing.

### NEXUS's ASK_CIPHER bridge
The only bridge built — CIPHER is the only other agent that exists.
Two trigger paths, matching the old system's real design: (1)
Python-side keyword pre-check (new shared/agent_topics.py
NEXUS_CIPHER_BRIDGE_KEYWORDS, word-boundary safe via
keyword_gate.py's contains_keyword — Lesson #6, the old system used
plain substring matching here) tells NEXUS's own model to write one
brief acknowledgment only; (2) fallback scan of NEXUS's own response
for a real ASK_CIPHER: line (backtick-guarded against mere mentions).
Either path calls agents.cipher.chat.stream_cipher() directly —
Lesson #1, no separate implementation.

Tested — CONFIRMED CLOSED, L1 through L5:
- L1/L2: 20/20 (both stream_by_tier and stream_cipher mocked to
  isolate NEXUS's own bridge logic).
- L3: 9/9 real end-to-end — both trigger paths routed to real CIPHER
  correctly; a real SAVE_FILE proposal surfaced through the bridge
  exactly like direct CIPHER chat, landed in CIPHER's own real
  pending-actions queue, and a real approval created the real file —
  Lesson #1 proven end-to-end, not just by design.
- L4/L5: 7/7 final (one real bug found and fixed along the way — see
  below).

Real cold-start race found via this test (not a mock artifact):
shared/nexus_memory.py's _get_collection() had no lock — 20 threads
hitting an uninitialized ChromaDB collection at once threw a real
AttributeError deep in ChromaDB's Rust bindings, never caught before
because every earlier test happened to warm the singleton sequentially
first. Fixed with double-checked locking (threading.Lock); identical
bug found and fixed in shared/cipher_memory.py too (Lesson #9 — same
code shape, same fix). Both re-confirmed under a real forced
cold-start test in their own memory L4/L5 suites, not assumed fixed by
similarity.

One flawed test assertion caught and fixed: a test checked NEXUS's raw
streamed text for "only the first ASK_CIPHER task," but that text
legitimately contains both lines verbatim (never live-stripped) — the
real check needed was what stream_cipher was actually CALLED with.
Fixed with a call-logging fake.

Real safety observation from testing (not a bug): when Joey doesn't
specify a path, CIPHER's real model picks one on its own — in testing
it picked a real path inside the actual D:\Projects\NEXUS SYSTEM\
folder. The approval step is what catches this.

Decision: conversational approve/deny (chatting with NEXUS to approve
a pending action) deferred to the future dashboard (Phase 5) — the
real gating is what mattered, and it's done. Item #3 (approval
workflow) considered DONE as-is.

### Phase 2 (NEXUS) status: COMPLETE
Core chat, memory, model-tier switching, bridge, and approval workflow
all done and fully tested L1-L5.

---

## Session 6 — Phase 3: ASSET (core chat + memory)

### Research
Pulled reference/asset_tools.py (9 real financial data-getter tools)
and reference/asset_memory.py — confirmed ASSET's prompt identical
between reference/agent_prompts.json and chat_streaming.py's
ASSET_PROMPT_DEFAULT (Walter White/Heisenberg voice, finance-only, no
tool/bridge markers of its own).

Real schema confirmed (financial-tracker-data.json — confirmed by
Youssef as the genuinely live/current source via LastWriteTime, not a
stale migration-export snapshot as first suspected): accounts, settings,
transactions, paychecks, creditScores, groceries, fixedExpenses,
fundsSubAccounts.

### Real bugs found in the old code (fixed during the build)
- NON_FINANCE refusal check and all live-data tool-selection keyword
  checks used plain substring matching (Lesson #6).
- Fetching live financial data was wrapped in a bare try/except: pass
  — a real Lesson #2/#12 violation.
- The old code's own comment claimed BREX was excluded from net worth,
  but the actual math never excluded it (comment was wrong, not the
  math) — confirmed with Youssef that BREX SHOULD count.
- Net worth math: cc/cc2 balances were silently skipped entirely
  regardless of sign; an overdraft on an ordinary account was also
  silently dropped. Both real gaps, not intentional.

### Real net-worth math, confirmed with Youssef
cc/cc2 sign is flipped (positive=liability/owed,
negative=asset/credit-in-favor); car_loan always a liability (abs());
BREX counts as a normal asset; an overdraft on an ordinary account now
correctly counts as a liability.

### Built
- agents/asset/asset_tools.py — all 9 tools ported and fixed: env-var
  FINANCIAL_DATA_PATH, load_data() now raises specific errors (missing
  file / mid-write-retry-once / real corruption) instead of silently
  returning None, fixed net-worth logic, search_financial_news removed
  entirely in favor of the already-tested shared/web_search.py
  (Lesson #9).
- agents/asset/prompt.py — ASSET_PROMPT carried over unchanged.
- shared/asset_memory.py — own category vocabulary (advice/goal/
  market/summary/conversation), NOT the CIPHER/NEXUS shared list; now
  uses shared/ollama_embeddings.py, fixing the old code's use of
  ChromaDB's default embedding function (a real gap for the one agent
  where local-first matters most); the ChromaDB cold-start-race fix
  (found the hard way in NEXUS/CIPHER) applied here from the start.
- agents/asset/chat.py — reuses Phase-0's ASSET_NON_TOPIC/ASSET_INTENT
  refusal gate, word-boundary-safe tool selection via new
  shared/agent_topics.py ASSET_TOOL_KEYWORDS dict, a real load-failure
  surfaced as an explicit context note instead of the old bare
  except:pass, narrow trigger-gated web search via new
  ASSET_NEWS_TRIGGERS (unlike NEXUS's near-universal search).

Confirmed as a hard rule: ASSET is permanently local-only (Ollama) —
stream_asset() has no model_tier parameter at all, unlike every other
agent, not even offered as a default.

### Two real false-refusal bugs found and fixed in ASSET_INTENT
1. "How much do I spend on food" would wrongly refuse ("food" is in
   ASSET_NON_TOPIC, nothing overrode it) — fixed by adding
   spend/spent/cost/grocery/groceries.
2. Found by an ACTUAL L2 test this session: "pay off the car loan"
   wrongly refused ("car" is in ASSET_NON_TOPIC/DRIVE's topic, nothing
   overrode it) — fixed by adding loan/car loan/car payment.

Both the same bug shape as the "workout program" example already
documented in agent_topics.py's own header.

### Real data quirk found during L3 (not a code bug)
carLoanMonthlyTarget and carFundTarget are two separate settings keys
representing the SAME real target ($1,500 — the car fund IS the
monthly car loan payment). A local model blurred them into "two
things, one needing correction" during a real L3 run. Confirmed with
Youssef as a genuine data redundancy — the real fix (consolidating the
schema) is out of scope, that's the separate Financial Tracker app.
Fixed within scope: get_account_settings() now explicitly states
they're the same target under two names; manually re-verified in a
follow-up real run, no longer described as two separate things.

Flagged as an ongoing consideration: ASSET's permanently-local design
makes it more prone to this kind of adjacent-number blurring than a
cloud model — worth periodically re-checking, not assuming this one
fix covers every future case.

### Tested — ASSET core chat CONFIRMED CLOSED, L1 through L5
- L1/L2: 25/25, synthetic data throughout.
- L3: 7/7 mechanical + manual read-through, real Ollama + real
  financial-tracker-data.json — real numbers correct, both
  false-refusal fixes hold under real load, correctly said "not broken
  down by category" instead of guessing a food-spending figure, real
  memory save+recall worked.
- L4/L5: 12/12, mocked — 100 sequential + 20 concurrent clean, net
  worth fully deterministic, empty/50k-char/unicode/None all handled
  (None fails loudly), malformed data degrades gracefully, real Ollama
  failure propagates rather than being swallowed.

### Tested — ASSET memory CONFIRMED CLOSED, L1 through L5
- L1/L2: 12/12 (fake embeddings) — one self-caught test bug (os.environ
  reassignment doesn't affect an already-imported module constant),
  fixed.
- L3: 4/4 real Ollama embeddings — real semantic ranking correctly
  favored the relevant memory over an unrelated one, multi-category
  saves all retrievable, a realistic full-length response saved and
  read back intact.
- L4/L5: 8/8 — real forced cold-start race test confirmed the lock
  (built in from the start here, unlike CIPHER/NEXUS where it was
  found after the fact) actually holds under real conditions.

Minor known gap, low real-world risk: save_conversation_turn(None,
None) doesn't crash but DOES save the literal string "Joey: None\n
ASSET: None" as real memory content. chat.py's only real call site
never passes None, so practical risk is low — flagged, not fixed.

### Phase 3 (ASSET) status: COMPLETE
Core chat and memory both fully closed L1 through L5.

## Not yet decided / still open
- Phase 4 build order confirmed (ATLAS, DRIVE, STOCK, FLAME, CASE,
  PULSE, one at a time) but no agent-specific decisions made yet.
- ATLAS is next — needs reference/atlas_tools.py and
  reference/atlas_memory.py confirmed current (both already exist in
  reference/ from Session 2's research; need to verify they're still
  accurate/complete before building against them).
- Instagram reel idea-extractor, task scheduler/crontab,
  expert/sub-agent spawning, plugin/skill marketplace — still scoped
  from Session 1, not started for any agent.
- Reel idea-extractor's "how it's saved" detail still not worked out.

## Session 7 — Phase 4: ATLAS (core chat)

Built: agents/atlas/prompt.py (Goggins prompt, unchanged, 2,786 chars,
verified against reference/agent_prompts.json), agents/atlas/atlas_tools.py
(read-only fitness data engine — env-var FITNESS_DATA_PATH, auto-creates
a starting file under a lock if missing, both old-ATLAS and Training
tracker data shapes tolerated, corrupt/mid-write files fail loudly or
retry once), agents/atlas/chat.py (stream_atlas() — word-boundary refusal
gate in Goggins voice, tightened "show my logged data" shortcut answered
directly with no model call, live data summary in context, trigger-gated
web search via shared/web_search.py, routes through stream_by_tier).
shared/agent_topics.py extended with ATLAS's trigger/history keyword
lists (word-boundary, Lesson #6).

Real fixes vs the old code: old plain-substring "how much/total/overall"
shortcut wrongly caught real coaching questions like "how much should I
bench" — now needs an explicit history phrase or a quantity+subject pair,
and never fires on advice or workout-report phrasing. Duplicate SerpApi
implementation in atlas_tools.py removed in favor of shared/web_search.py
(Lesson #9). Old code crashed on missing dates and printed raw Python
lists for weaknesses — every reader now shape-checks (Lesson #5).

Tested — CONFIRMED CLOSED, L1 through L5:
- L1/L2 (atlas_tools.py): 14/14 — prompt exact-match, no hardcoded old
  path or secret, mixed real-world shapes (old ATLAS + Training tracker,
  including the exact plain-string-exercise crash) never break a reader,
  corrupt JSON fails loudly, mid-write file recovers on retry, 20
  threads creating the file at once produce exactly one clean file.
- L1/L2 (chat.py): 15/15 — old "food"/"car"/"program" substring
  false-refusals confirmed fixed, history-question table correct,
  failed search passed through as a failure not hidden, history never
  mutated by the caller.
- L4/L5: 15/15 (mocked) — 100 sequential + 20 concurrent zero cross-talk,
  a simulated non-atomic tracker rewrite caught readers mid-write and the
  retry recovered every time (deliberately verified: disabling the retry
  made all 160 reads fail, confirming the test can actually catch this),
  20,000-workout file stayed fast and the prompt summary stayed bounded,
  empty/50k-char/unicode/None/malformed-history/regex-special-chars all
  handled, a real model failure propagates rather than being swallowed,
  deleted data file auto-recreates mid-session.
- L3: 10/10 real end-to-end (real Gemini, real SerpApi, real Ollama, one
  real Sonnet 5 call ~$0.017) — grounded, in-voice responses across
  coaching, empty-log honesty, refusal, direct data lookup, search-backed
  technique advice, real multi-turn recall of an injury and a stated
  goal, coaching through an unreadable data file, and all three model
  tiers. One non-blocking observation: the local-tier model sometimes
  prints its internal mode label ("PUSH MODE") as a literal heading —
  a model-behavior quirk, not a code bug, left as-is / fixed per Joey's
  call.

ATLAS Phase 4 core chat status: complete