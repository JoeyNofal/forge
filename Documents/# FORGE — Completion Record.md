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