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