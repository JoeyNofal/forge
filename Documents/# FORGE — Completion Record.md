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

## Session 8 — Phase 4: DRIVE (core chat)

Built: agents/drive/prompt.py (Clarkson prompt, unchanged, 1,946 chars,
verified against reference/agent_prompts.json — includes Joey's real
VIN, confirmed still current), agents/drive/drive_tools.py (read-only
vehicle data engine — env-var VEHICLE_DATA_PATH, auto-creates Joey's
real 2016 Honda Civic under a lock if missing, every reader shape-safe),
agents/drive/chat.py (stream_drive() — word-boundary refusal gate using
DRIVE's own prompt line, tightened "show my logged data" shortcut
answered directly with no model call, live data summary in context,
trigger-gated web search via shared/web_search.py, routes through
stream_by_tier). shared/agent_topics.py extended with DRIVE's
trigger/history keyword lists (word-boundary, Lesson #6).

Real fixes vs the old code: drive_tools.py had ZERO file locking on
vehicle.json — a real live gap, unlike pending_tasks.py/atlas_tools.py
which Phase 0 confirmed already had it. The old code indexed
vehicle['year']/vehicle['vin'] etc. directly and would KeyError on a
malformed or partial entry, and assumed the vehicles list always exists
and is non-empty — now fully shape-safe (Lesson #5). The old code
searched the web on EVERY message wrapped in a bare except: pass — a
live Lesson #2/#8/#12 phantom-search risk, now trigger-gated with
failures surfaced explicitly. Duplicate SerpApi implementation removed
in favor of shared/web_search.py (Lesson #9).

Tested — CONFIRMED CLOSED, L1 through L5:
- L1/L2 (drive_tools.py): 16/16 — prompt exact-match, VIN correct on
  auto-create, mixed real-world junk (non-dict vehicle entries, wrong
  types, missing fields) never breaks a reader, corrupt JSON fails
  loudly, mid-write file recovers on retry, 20 threads creating the
  file at once produce exactly one clean file, multi-vehicle handling
  correct (inactive vehicle ignored for the summary).
- L1/L2 (chat.py): 16/16 — old "code"/"program" substring false-refusals
  confirmed fixed, refusal message matches DRIVE's own prompt line,
  history-question table correct, failed search passed through as a
  failure not hidden.
- L4/L5: 15/15 (mocked) — 100 sequential + 20 concurrent zero cross-talk,
  a simulated non-atomic writer caught readers mid-write and the retry
  recovered every time, 20,000-entry file stayed fast and bounded,
  empty/50k-char/unicode/None/malformed-history/regex-special-chars all
  handled, a real model failure propagates rather than being swallowed,
  deleted data file auto-recreates mid-session.
- L3: 10/10 real end-to-end (real Gemini, real SerpApi, real Ollama, one
  real Sonnet 5 call ~$0.0135) — grounded, in-voice responses across
  advice, empty-log honesty, refusal, direct data lookup, real
  recall-search grounding, real multi-turn recall of a reported issue
  and correctly averaged MPG, advice through an unreadable data file,
  and all three model tiers. Note: a specific real recall claim (case 5)
  should be independently verified against NHTSA/Honda before acting on
  it — DRIVE grounds its answer in real search results, but a factual
  safety claim about a real VIN still deserves a manual check.

DRIVE Phase 4 core chat status: complete

## Session 9 — ATLAS increment (b): logging, approvals, extraction

Built (agents/atlas/): atlas_logging.py (validators + locked writers for
swim/gym/injury/injury-status-update; all fitness writes live here),
atlas_actions.py (approval gate: propose / approve_and_execute / deny /
list_pending; ids can be typed as a unique 6+ char start), atlas_extract.py
(whole-word trigger pre-filter, local gemma3:12b JSON extraction of Joey's own
message only, always ends in a proposal, never a save). shared/model_client.py:
new complete_ollama_json(). shared/agent_topics.py: ATLAS logging trigger lists.
ATLAS prompt unchanged; a separate format note stops the local model printing
"PUSH MODE" (verified over 4 real runs).

Decisions: nothing saves without approval (same queue pattern as CIPHER); FORGE
ATLAS writes only its own data file until switch-over; extraction always local;
"my shoulder is better now" updates the one matching open injury (never
guesses); photo scan deferred; workout template = own later increment
(single HTML page, phone, gym only, copy-paste back to ATLAS).

Real bugs found and fixed: (1) shared file_store returned the caller's own
default object, so the pending-actions queue could resurrect old actions;
(2) pending_actions readers didn't take the writers' lock (half-written reads
under 20 concurrent approvals); (3) invented defaults: unstated difficulty 5 /
duration 0 were being saved as real values — now null, shown as "not stated";
(4) extraction leaked injury soreness into the workout's "weaknesses";
(5) Phase 0 test checked for a leftover .lock file (a library detail) — replaced
with a test that proves update_json really blocks on a held lock.

Tested — CONFIRMED CLOSED, L1-L5: logging 26/26, actions 26/26, extraction
31/31 (mocked), real L3 14/14 twice with local Ollama, read for invented
numbers/dates/statuses; all earlier ATLAS suites and Phase 0 (35/35) and CIPHER's
queue tests still pass after the shared-code fixes.

## Session 10 — DRIVE (b), Parts 1–3a: logging, approval gate, resolve-all

Setup: pushed the DRIVE Tracker (Electron app) into reference/DRIVE Tracker (BACKEND_URL is 127.0.0.1, safe
to publish; two stray empty files "cd" and "npm" removed). Read the tracker, the old drive_tools.py writers
and the live vehicle.json shape before writing anything.

### Findings in the OLD code / tracker (not ported, fixed in FORGE)
- The tracker and the old agent disagreed on field names for the same file: upcoming service due
  (due_mileage/due_date vs next_due_miles/next_due_date), issue date (reported_date vs date_reported),
  issue severity (high/medium/low vs mild/moderate/severe). The tracker's Upcoming screen could not show
  due dates the agent wrote.
- Old log_maintenance reset the next-due schedule BACKWARDS when an older service was logged.
- Old wiper-fluid logging used the car's current mileage as an invented value.
- Tracker bugs, noted for Phase 5 (NOT fixed, tracker not rebuilt yet): preload.js calls drive-load-data /
  drive-save-data but main.js registers load-data / save-data; the tracker rewrites the whole vehicle.json
  with no locking (a real risk at switch-over).

### Decisions
- FORGE writes the TRACKER's field names; readers accept both naming conventions.
- Severity words: low / medium / high. performed_by: shop or diy ("dealership" counts as shop).
- Nothing saves without approval (same queue as CIPHER/ATLAS). Extraction is always the local model.
- Unstated mileage/cost/severity/performed-by are saved as null (0 = not stated). A missing or future date
  becomes today (EXCEPT Carfax history, see Session 12).
- A service logged for an OLDER date never rewinds the next-due schedule. Current mileage only goes UP from a
  service/fill-up; stating a mileage outright sets it even if lower (proposal shows a warning).
- MPG is worked out at approval from the nearest EARLIER fill-up by mileage (null if none/implausible).
- Proposal warnings (never blocking): a mileage UPDATE lower than current; any mileage more than 5,000 above
  current (MAX_JUMP_WARNING_MILES). A backdated service at a lower mileage does not warn.
- Resolving issues: one issue by id, or SEVERAL / ALL in one approved action (named in the proposal).
- Deleting/editing a wrong entry stays in the tracker for now.

### Built (agents/drive/)
- drive_logging.py: normalizers + locked writers (mileage, maintenance, fill-up, issue, issue status, bulk
  resolve). Every write is one locked read-modify-write; a failure writes nothing.
- drive_actions.py: the approval gate (propose / approve_and_execute / deny / list_pending; ids can be typed
  as a unique 6+ character start). Only approve_and_execute writes. Atomic claim, so two simultaneous
  approvals can never both save.
- drive_tools.py readers updated (both field names); brake_replacement display name.

### Tested — CONFIRMED CLOSED, L1-L5
test_drive_logging 39/39, test_drive_actions 30/30, test_drive_resolve_all 20/20 (a test-helper bug,
comparing a number with "i2", was found and fixed).

---

## Session 11 — DRIVE (b), Part 3b/3c: extraction, Python guards, chat wiring, brake reminder

### Decisions
- Extraction (drive_extract.py): a cheap whole-word pre-filter decides if the local model (gemma3:12b) is
  asked; the model sees ONLY Joey's own message plus his NUMBERED open issues (it answers with numbers,
  Python maps them to ids). Up to 3 things per message; a 4th, or a 2nd job in a service report, gets an
  explicit note. A mileage riding along with a service/fill-up goes on THAT record.
- Questions/advice never log; a problem report plus a question still logs the problem.
- "X is fixed": one named issue -> single proposal; several -> bulk; "everything's fixed / 100%" -> ALL open
  issues (Python decides "all", only a real JSON true counts). A service that clearly fixes an open issue
  gives TWO separate proposals (service + resolve), never duplicated.
- DRIVE's context note tells the model it cannot save/log/remember anything, to react briefly to routine
  reports, not to speculate, recommend a dealership, do arithmetic, or invent what other people said.
- DRIVE's open issues now appear in its data summary.
- DRIVE's prompt is UNCHANGED (Clarkson). Known limit: it still hardcodes the 2016 Civic and VIN, and the
  catchphrase "The dealership is the right call here" comes from the prompt itself. Part 4 (add/switch
  vehicle) was CANCELLED: there is only one car.
- Brake reminder (Part 3c): "brake replacement" is a real service type (wording variants such as brake pad
  replacement / brake repair map to it; lights, bulbs, fluid, noises do not) and restarts the brake-INSPECTION
  schedule (20,000 mi / 12 months). One approved "Brake Inspection, due today" entry sorts first on the
  tracker's dashboard until brake work is logged. Triggered by a fixed phrase (add a brake reminder / remind me
  about my brakes / remind me to check my brakes), no model call.

### Real bugs found by the REAL model (each fixed in PYTHON, not just the prompt)
Re-logged an already-open issue (duplicate guard, issue_match.py); resolved the wrong issue for "my light is
fixed" with two light issues (asks which); claimed brakes fixed a tire light (fix claims must share words);
wrote "dealership" as a shop name (generic shop words dropped, performed_by kept); leaked "100%" and
"Joey's question" into notes (prompt tightened); showed raw snake_case names (tidied); said "I'll have a
proposal generated" (note tightened).

### Built
drive_extract.py, issue_match.py (pure word matching), chat.py wiring (proposals appended AFTER the reply;
a crash in extraction becomes a visible note), shared/agent_topics.py DRIVE lists.

### Tested — CONFIRMED CLOSED
test_drive_extract 42/42, test_issue_match 9/9, test_drive_extract_guards 14/14, test_drive_chat_extract
16/16, test_drive_brakes 26/26; real L3 against local gemma 24/24 (read for exact numbers/dates).

---

## Session 12 — DRIVE (b), Parts 5–6: Carfax entries and the NHTSA recall check

### Part 5 — typed Carfax entries
One record per message typed in chat (the tracker already imports whole Carfax files). Stored as
source "carfax", performed_by "previous_owner" (matches the tracker's importer). The DATE MUST BE STATED
(never defaulted to today: history); no relative dates. They do NOT touch the next-due schedule or current
mileage. An identical Carfax record (same service/date/mileage) is refused. Tested: test_drive_carfax 25/25;
real L3 10/10 (missing and "last year" dates correctly refused).

### Part 6 — recall check (official NHTSA API)
- shared/nhtsa.py: api.nhtsa.gov recallsByVehicle (no key, standard library only, one network function).
  IMPORTANT LIMIT: keyed by make/model/YEAR, NOT by VIN. Real response shape verified on the machine
  (Count/Message/results; fields NHTSACampaignNumber, Component, Summary, Consequence, Remedy,
  ReportReceivedDate in DD/MM/YYYY -> shown as YYYY-MM-DD, parkIt). A FAILED lookup is never "no recalls".
- drive_recall.py: on any message with recall/recalls/recalled, the active vehicle's year/make/model come
  from the vehicle FILE; DRIVE's model gets a labeled block (or a "lookup failed, do not guess" note).
  After the reply: a FIXED Python reminder ("covers ALL <year> <make> <model> vehicles, not your VIN
  specifically... check your VIN at nhtsa.gov/recalls") because the real model ignored the caveat; then an
  offer to save a dated snapshot — ONLY if the list changed since the last saved one, approval required.
  Snapshots go in vehicle["recalls"] (a list; older text-style entries are never touched); the last 10 NHTSA
  snapshots are kept; a snapshot for a different vehicle, or a repeat of the last one, is refused.
- Remaining text cut at WORD boundaries (a real phone number was being cut in half).
- The web search on "recall" still runs as before.

### Tested — CONFIRMED CLOSED
shared test_nhtsa 26/26; test_drive_recall 29/29; real L3: NHTSA 7/7, end-to-end recall 4/4.

---

## Session 13 — DRIVE (c): permanent memory

### Decisions (Joey's)
Six categories only: decision, preference, correction, goal, plan, project_fact (money is ASSET's, workouts
ATLAS's). Memories come ONLY from Joey's own words (never DRIVE's replies), picked out by the local model
after DRIVE's reply, saved AUTOMATICALLY with a visible "Remembered: ..." line. Logged data (mileage,
services, fill-ups, issues, recalls, Carfax) is never copied into memory. Recall on every question except
"show me my logged data" and refusals (top 3, relevance cutoff, labeled "background, may be outdated").
List and forget commands wanted (forget always via approval). Started EMPTY; the old NEXUS SYSTEM DRIVE memory
was left untouched (it saved every turn and DRIVE's own advice: the Lesson #3 anti-pattern).

### Built
- shared/drive_memory.py: own ChromaDB collection "drive_memory", cosine distance, Ollama embeddings, memory
  folder D:\Projects\forge\memory\drive (gitignored). Facts only (max 500 chars, refused not cut). Duplicates
  are refused under a lock; delete_memory / delete_memories.
- agents/drive/drive_remember.py: pre-filter phrases (I always / I prefer / I decided / I'm planning / from
  now on / remember / actually...), local extraction, Python guards (category list, no money, no workouts, no
  past-tense logged events unless a habit/plan word is present, max 3 with a note about the rest), recall
  block (a stored fact cannot fake the block's end marker). A statement with no signal phrase is not picked up
  (say "remember that ...").
- agents/drive/drive_memory_commands.py: "what do you remember?" answered with NO model call (numbered, newest
  first, category/date/6-char id, max 20); "forget <description | id | that | everything>" ALWAYS a proposal
  through drive_actions; "forget everything" deletes exactly the memories existing when it was proposed;
  ambiguous targets (equal meaning OR his exact words fit several memories) ask which, never guess; everyday
  phrases ("forget it", "I forgot", "don't forget") are not commands.

### Calibrated from REAL nomic-embed-text distances (not guessed)
Relevance cutoff 0.50 (related questions' best match <= 0.44, unrelated >= 0.557). Duplicate rule: identical
words always a duplicate; embedding duplicate only at <= 0.005 AND identical numbers, because a CHANGED fact
(0W-20 -> 5W-30) measured only 0.041 apart and would have been swallowed (stale fact kept). Forget cutoff 0.52
(unrelated 0.554, worst legitimate 0.493). Env overrides: DRIVE_MEMORY_PATH, DRIVE_MEMORY_MAX_DISTANCE,
DRIVE_MEMORY_DUPLICATE_DISTANCE.

### Real bugs found
A list/dict category crashed the filter (unhashable type); the real model wrote the CATEGORY into "kind"
(Python now salvages only the fact it actually gave); a planned road trip was missed until the prompt said
plans include trips/purchases; "forget the Civic" guessed one of two memories (now asks).

### Tested — CONFIRMED CLOSED
shared test_drive_memory 30/30; test_drive_remember 33/33; test_drive_memory_commands 31/31; real L3: store
6/6, remember 6/6, commands 8/8. Whole DRIVE regression green (test_drive 16, tools 16, l4_l5 15, logging 39,
actions 30, resolve_all 20, extract 42, issue_match 9, guards 14, chat_extract 16, brakes 26, carfax 25,
recall 29, remember 33, memory_commands 31).

### DRIVE status: COMPLETE (core chat, increment (b), increment (c))
Whole-suite command (skips the real-model _l3 files):
  Get-ChildItem agents\drive\test_*.py | Where-Object { $_.BaseName -notlike "*_l3" } | ForEach-Object {
  "== " + $_.BaseName; python -m ("agents.drive." + $_.BaseName) 2>&1 | Select-String -Pattern "passed|FAIL" }

---

## Standing project rules (reconfirmed this stretch)
- Claude never creates files; every change is a FIND block and a REPLACE block (or a whole new file pasted).
- Nothing is "done" until a full L1-L5 pass; real-model (L3) output is READ, not just counted.
- Wherever a real model ignored a rule, ENFORCE it in Python (guards), then re-test.
- Older chat tests are kept hermetic by stubbing the newer chat steps (extraction, recall, memory).

## Not yet decided / still open
- NEXT per plan: ATLAS workout template (single HTML page, phone, gym only, copy-paste back to ATLAS), then
  STOCK, then FLAME, CASE, PULSE (Phase 4 order), then Phase 5 dashboard/companion apps, Phase 6 voice/mobile/
  Autonomous Build System.
- BACKLOG (requested, not designed): ATLAS tracks macros (calories, protein, ...) from food PHOTOS; each
  estimate shown (with a range) and saved only after approval; later FLAME (halal-only) builds a healthy diet
  from the history. Depends on ATLAS's deferred photo scan and on FLAME existing.
- CONSOLIDATION refactor (small, tested) before STOCK: the same normalizer helpers exist in atlas_logging.py
  and drive_logging.py; the approval-gate skeleton exists in atlas_actions.py and drive_actions.py;
  drive_remember.py imports the private _parse_model_json/ExtractionError from drive_extract.py.
- Phase 5 tracker fixes: the preload/main channel-name mismatch; locking (or switch the tracker to go through
  FORGE) before switch-over; chat-based edit/delete of a wrong log entry (today: the tracker's own delete).
- Conversational approve/deny (approving a pending action by chatting) still deferred to the dashboard.
- Reel idea-extractor, task scheduler/crontab, expert/sub-agent spawning, plugin/skill marketplace: still
  scoped from Session 1, not started for any agent.
- DRIVE's local-tier replies still invent colourful flourishes in Clarkson's voice (forum posts, brand
  claims); the context note now forbids it, but every claim about the car should still be sanity-checked.

# FORGE — Completion Record, Session 14
*(consolidation refactor, unit fixes for ATLAS and DRIVE, STOCK decisions. Paste this into the Completion Record file.)*

## Session 14 — Consolidation refactor, unit fixes, STOCK decisions

### Decided (Joey's)
1. **Order:** consolidation refactor first, then the ATLAS workout template, then STOCK.
2. **Refactor scope:** fix all three duplications, move the approval gate to ONE shared module, and also re-point CIPHER at it.
3. **STOCK, decided before any code:**
   - It writes to its own FORGE pantry file until switch-over (like ATLAS and DRIVE).
   - Routine pantry and grocery changes save DIRECTLY, with a visible "Logged: ..." line, and no approval queue.
   - STOCK's image/photo scan is deferred until image upload exists.
4. **Standing rule (new):** whenever a bug is found, fix it immediately, even in an already-closed feature.
5. **ATLAS unitless weight:** a weight given with no unit ("at 50") is taken as POUNDS and shown "(unit assumed)" on the proposal.
6. **ATLAS injury severity:** the default "mild" when unstated is left as-is for now. Revisit later.
7. **DRIVE:** the redundant "couldn't tell which open problem you mean" note (it can appear alongside a service proposal) is left as-is.
8. **DRIVE unitless values:** a unitless mileage or fuel amount is simply miles/gallons, with NO "(unit assumed)" label. This was Claude's design call, stated at the time and not objected to. Reasoning: nothing the model guesses can reach the number any more, unlike ATLAS where the shown unit was itself an assumption. Adding the label is a separate small step if wanted.

### Baseline at the start
A full regression run found three stale tests, all fixed (test-only, no product bug):
- `test_nexus` and `test_nexus_l4_l5` still expected the old stripper to remove ASK_CIPHER, which has been a real bridge since Session 5 (handled by `strip_bridge_markers`).
- `test_cipher_l4_l5` still faked `stream_gemini` instead of `stream_by_tier` (stale since Session 4).

### Built and tested

**Part A: shared approval gate** (`shared/action_gate.py`)
- One `ActionGate(agent_name, display_name, describe, handlers)`: `propose`, `find_action` (full id or unique 6+ char start), `approve_and_execute` (atomic claim, handler returns `(ok, message)`), `deny_action`, `list_pending`.
- A buggy `describe()` can never break deny or list. A handler returning junk is recorded FAILED. An unknown action type is refused at propose time.
- `shared/test_action_gate.py`: **24/24**.

**Part B: ATLAS onto the gate** (`atlas_actions.py` with `_run_*` handlers). Two static checks in `test_atlas_actions` were re-pointed. **26/26**.

**ATLAS unit fix** (real L3 found "incline press at 50" saved as `weight_lbs: 110.23`: the local model assumed kg and did the multiplication itself, because the prompt said "convert kg to pounds")
- The model now reports `weight` exactly as said plus `weight_unit` ONLY if Joey wrote one. PYTHON converts (kg × 2.20462, meters × 1.09361). Same for swim `total_distance` / `distance_unit`.
- A unitless weight is taken as pounds, and a unitless swim distance as yards. Both are flagged by a proposal-only `units_assumed` list, which is NEVER saved. The exercise record shape is unchanged: `weight_lbs`.
- The proposal now shows the weights: `; weights: bench press 135 lbs, incline press 50 lbs (unit assumed)`.
- `atlas_extract._enforce_stated_units`: a unit the model reports survives only if Joey's own message contains a word of that unit family. Real L3 showed the model copying "lbs" from the example shape, and it could just as well guess "kg". Known residual: this check is per message, not per exercise.
- Older keys (`weight_lbs`, `total_distance_yards`) still work, unflagged.
- `agents/atlas/test_atlas_units.py` (new): **34/34**. Real L3: unitless lines are flagged, a written "lbs" is not.

**Part C: DRIVE onto the gate**
- `drive_actions.py` now has 11 `_run_*` handlers plus the gate.
- Six static checks were re-pointed in `test_drive_actions` (x2), `test_drive_recall`, `test_drive_brakes`, `test_drive_carfax`, `test_drive_memory_commands` and `test_drive_resolve_all`.

**DRIVE unit fix** (same bug class: `drive_extract.py` told the model "Convert units: liters to US gallons, km to miles")
- `agents/drive/drive_units.py` (new, pure): unit words and the two conversion factors (0.264172 L→gal, 0.621371 km→mi). It exists because `test_drive_extract` forbids importing `drive_logging` into `drive_extract`.
- `drive_logging.py`: `_odometer()` converts km to miles, and `_fuel_gallons()` converts liters to gallons. Both work for mileage, maintenance, fill-up and Carfax (Carfax inherits maintenance's). Clean records carry no unit keys, so re-checking at approval never converts twice.
- The prompts now say NEVER convert. They carry `mileage_unit` and `fuel_amount` / `fuel_unit`, and ask for price per gallon only (never per liter).
- `drive_extract._enforce_stated_units`: same guard as ATLAS.
- **Extra gap found and fixed:** `shared/agent_topics.py` had no km words in `DRIVE_MILEAGE_WORDS` and no liter words in `DRIVE_FILLUP_WORDS`, so "my car has 80,000 km on it" was silently ignored. They are now added.
- `test_drive_units`: **22/22**. `test_drive_units_l3` (new, real local model): **9/9**. Read: 80,000 km → 49,710 miles; "filled up 40 for $50" stays 40 gal at $1.25 (the guessed-unit trap holds); 20 L → 5.28 gal.

**DRIVE "100%" notes leak** (a real L3 slip after the prompt edit: the model copied "it's at a 100%" into the service notes)
- Enforced in Python: `_without_percent_notes()` in `drive_extract` drops notes with a % sign, for both service and Carfax entries.
- 4 tests were added to `test_drive_extract_guards` (**18/18**). Its fake `kind_of()` was also taught the Carfax prompt (it predated Carfax).

**Part D: CIPHER onto the gate** (`cipher_tools.py`: `_run_create_file` and `_run_command`)
- Behaviour changes, all accepted:
  1. Short ids now work.
  2. REAL BUG FIXED: `deny_action` never checked whose action it was.
  3. REAL BUG FIXED: a command exiting non-zero was recorded "executed" whenever it printed anything. It is now FAILED with `Command failed (exit code N): ...`.
  4. `list_pending()` was added.
- `agents/cipher/test_cipher_gate.py` (new): **16/16**.

**Part E: shared normalizers** (`shared/normalizers.py`: `num`, `text`, `str_list`, `date_or_today`, `require_dict`, `MAX_TEXT`, `MAX_LIST`)
- The copies in `atlas_logging` and `drive_logging` had drifted; DRIVE's were the better ones and were adopted.
- Fixes for ATLAS: strings like "1,500" or "$30" are now numbers (they were silently "not stated"), and a dict is no longer saved as its Python repr.
- Both logging files import them under their old private names via `import ... as _num`, so every call site and test is unchanged.
- `shared/test_normalizers.py`: **14/14**.

**Part F: shared JSON-parse helper** (`shared/model_json.py`: `ExtractionError`, `model_call_failed`, `parse_model_json`)
- It replaced identical copies in `atlas_extract` and `drive_extract`, plus `drive_remember`'s reaching into drive_extract's privates.
- A 100,000-level-deep model answer is now a typed `ExtractionError`, not a raw `RecursionError`.
- The model CALL stays inside each extractor, because many tests replace `complete_ollama_json` on that module.
- `import json` was removed from both extract files.
- `shared/test_model_json.py`: **11/11**.

**The consolidation refactor is fully closed (Parts A to F).**

### Full regression baseline (all non-L3 suites, as of end of session)
- **shared:** action_gate 24, normalizers 14, model_json 11, phase0 35, phase0_l4_l5 9, model_client 22, model_client_l4_l5 8, asset_memory 12, asset_memory_l4_l5 8, drive_memory 30, nhtsa 26.
- **ASSET:** asset 25, asset_l4_l5 12.
- **ATLAS:** atlas 15, actions 26, extract 31, l4_l5 15, logging 26, tools 14, units 34.
- **DRIVE:** drive 16, actions 30, brakes 26, carfax 25, chat_extract 16, extract 42, extract_guards 18, l4_l5 15, logging 39, memory_commands 31, recall 29, remember 33, resolve_all 20, tools 16, units 22, issue_match 9.
- **CIPHER:** cipher 12, actions 24, actions_l4_l5 10, gate 16, l4_l5 10, memory 21, memory_l4_l5 11.
- **NEXUS:** nexus 12, bridge 20, bridge_l4_l5 7, l4_l5 13, memory 20, memory_l4_l5 13.

Whole-suite command, run from `D:\Projects\forge` (it skips the real-model `_l3` files):
```
Get-ChildItem -Recurse -Filter "test_*.py" agents,shared | Where-Object { $_.BaseName -notlike "*_l3" } | ForEach-Object { $mod = ($_.FullName.Substring((Get-Location).Path.Length+1) -replace '\\','.' -replace '\.py$',''); "== $mod"; python -m $mod 2>&1 | Select-String -Pattern "passed|FAIL" }
```
Real-model (L3) smoke files kept green this session: `agents.atlas.test_atlas_extract_l3` (14/14), `agents.drive.test_drive_extract_l3` (24/24), `agents.drive.test_drive_units_l3` (9/9), `agents.drive.test_drive_remember_l3` (6/6), `agents.drive.test_drive_carfax_l3`, `agents.drive.test_drive_recall_l3`, `agents.drive.test_drive_memory_commands_l3`, `agents.cipher.test_cipher_actions_l3` (9/9), `agents.nexus.test_nexus_bridge_l3` (9/9).

### Files new or changed this session (commit and push if not already done)
- **New:** `shared/action_gate.py`, `shared/test_action_gate.py`, `shared/normalizers.py`, `shared/test_normalizers.py`, `shared/model_json.py`, `shared/test_model_json.py`, `agents/atlas/test_atlas_units.py`, `agents/drive/drive_units.py`, `agents/drive/test_drive_units.py`, `agents/drive/test_drive_units_l3.py`, `agents/cipher/test_cipher_gate.py`.
- **Changed:** `agents/atlas/atlas_actions.py`, `atlas_logging.py`, `atlas_extract.py`, `agents/drive/drive_actions.py`, `drive_logging.py`, `drive_extract.py`, `drive_remember.py`, `agents/cipher/cipher_tools.py`, `shared/agent_topics.py`, and the existing tests whose static checks were re-pointed (see Parts B, C and the guards fix above).

### Findings to remember
- **Prompt edits ripple.** Editing the shared rules at the top of DRIVE's prompts also changed behavior in unrelated prompts (the "100%" leak, an extra note). After ANY prompt edit, re-run the real-model L3 files, and enforce what matters in Python, not just in the prompt.
- **Real-model quirks, now enforced in Python:** the local model copies units from the prompt's example shape, can guess units nobody stated, and sometimes ignores "never put percentages in notes". Do arithmetic and unit logic in Python only.
- **Safety observation (not a bug):** when Joey gives no path, CIPHER's real model picks one on its own. In L3 it picked a path inside the old `D:\Projects\NEXUS SYSTEM\dashboard\` folder. Approval is what protects that folder. Check for stale proposals with: `python -c "from agents.cipher import cipher_tools as c; print(c.list_pending())"`, and deny any that point into the old folder.
- **DRIVE known limit, unchanged:** the local-tier replies still invent colourful Clarkson flourishes and catchphrases ("The dealership is the right call here" comes from the prompt). Sanity-check any factual claim about the car (for example "it's what Honda specifies").
- **Claude's own miscounts this session:** several test counts were predicted wrong and corrected from real output. Trust the real counts above.

### Not yet applied by Joey
- Pylance warning in `agents/cipher/test_cipher_gate.py` (cosmetic, the test passes): on the line `out = fn(bad)`, add `  # pyright: ignore[reportArgumentType]`.

### Not yet decided / still open
- **NEXT: the ATLAS workout template** (single HTML page for the phone, gym only, copy-paste back to ATLAS). Claude asked five questions that Joey has NOT answered yet:
  1. Which fields to fill in at the gym per exercise (name, sets, reps, weight, notes, rest timer, how it felt?), and should it also log swims or be gym only?
  2. Should the page remember a saved list of usual exercises and last time's weights (needs phone storage), or be an empty form each visit?
  3. What does the copy-paste output look like? Suggestion: one plain sentence like "I did chest today. Bench press 3 sets of 8 at 135 lbs, incline dumbbell press 3x10 at 50 lbs", with the unit always included so "(unit assumed)" never appears.
  4. How does the page get onto the phone (send the file to himself, host it, or serve it from the laptop on the home network)?
  5. Must it work with no signal at the gym (assumed yes)?
- **THEN: STOCK**, per the decisions above. It needs `reference/stock_tools.py` (and `reference/stock_memory.py` if any) read and confirmed current first. `reference/stock_tools.py` points at the live `D:\Projects\NEXUS SYSTEM\data\pantry.json`, but FORGE's STOCK uses its own fresh pantry file. Its image feature (`extract_pantry_items_from_image`) is deferred. The FLAME ASK_STOCK bridge comes later with FLAME.
- **Remaining Phase 4 order:** STOCK, FLAME (halal only, checks STOCK first), CASE, PULSE.
- **ATLAS (c) memory** has not been built. ATLAS has core chat and logging only. A photo scan for ATLAS is deferred.
- **ATLAS injury severity default** ("mild") revisit later (see Decided #6).
- **BACKLOG (requested, not designed):** ATLAS tracks macros from food PHOTOS, shown with a range and saved only after approval. FLAME later builds a halal diet from that history. It depends on ATLAS's photo scan and on FLAME existing.
- **Phase 5 tracker fixes** (DRIVE Tracker): the preload/main channel-name mismatch, and locking (or going through FORGE) before switch-over. Chat-based edit/delete of a wrong log entry is also wanted.
- **Conversational approve/deny** (approving a pending action by chatting) is still deferred to the dashboard (Phase 5).
- **Still scoped from Session 1, not started for any agent:** reel idea-extractor (its "how it's saved" detail is still undecided), task scheduler/crontab, expert/sub-agent spawning, plugin/skill marketplace.
- **Possible small step:** add the "(unit assumed)" label to DRIVE too, if Joey wants it.

### Standing project rules (reconfirmed)
- Claude never creates files or runs commands to edit the project. It gives code and text in chat, and Joey creates every file himself in VS Code. (Reading and cloning the repo with bash is allowed.)
- Every change is given as a FIND block and a REPLACE block (or a whole new file pasted).
- Nothing is "done" until a full L1-L5 pass. Real-model (L3) output is READ, not just counted.
- Wherever a real model ignored a rule, ENFORCE it in Python (a guard), then re-test.
- Whenever a bug is found, fix it immediately.
- Claude asks questions in ONE numbered list, plain (no multiple-choice cards), before writing code.
- Older chat tests are kept hermetic by stubbing the newer chat steps (extraction, recall, memory).