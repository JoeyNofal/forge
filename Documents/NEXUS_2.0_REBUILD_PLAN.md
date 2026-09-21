# NEXUS 2.0 — REBUILD MASTER PLAN
# Status: PLANNING, NOT YET STARTED
# Companion document: NEXUS_LESSONS_LEARNED.md (read that one first)

---

## WHY THIS EXISTS

The original NEXUS SYSTEM grew to 9 agents, several companion apps, an
autonomous build system, and a full testing framework — built by a
complete beginner, directing every line by hand, over several months.
That's a real, substantial thing to have built. But the project's
*process* — build features in batches, test them thoroughly much later —
let real bugs (stale bridges, race conditions, unlabeled memory context)
accumulate faster than they got caught, and that's what's actually
driving the "this feels like it went wrong" feeling, not the underlying
idea of the system.

This rebuild changes the process, not the ambition: same 9 agents, same
personalities, same companion apps — built and fully tested one piece at
a time, with the real bug patterns from the first build guarded against
from the start instead of discovered later.

---

## THE "SMART AND AUTOMATED, FOR FREE" QUESTION — ADDRESSED DIRECTLY

My Claude feels more reliable than NEXUS not because it's free — it
isn't; it runs on paid Sonnet 5, with its own budget tracker built
specifically to cap real spend. It feels more reliable because it's one
agent, built recently, tested right after each feature, with no
accumulated debt.

NEXUS already has the same free/paid structure My Claude does — Local
Gemma (free) → Free Cloud Gemini (free) → Paid Cloud Sonnet (metered,
capped at $10/day) — built during the Reasoning Upgrade project. That
part of the architecture doesn't need reinventing. What needs to change
is testing discipline, so the smart-and-automated parts (multi-step tool
loops, the Autonomous Build System, agent bridges) actually work
reliably every time, the way they do in My Claude.

---

## WHAT CARRIES OVER AS-IS (no rebuilding needed)

- Every agent's personality/voice writing (Alfred, JARVIS, Walter White,
  Goggins, Clarkson, STOCK's calm voice, Ramsay, Ultron, Baymax) — pulled
  from the existing `agent_prompts.json`, re-validated during each
  agent's rebuild but not rewritten from scratch.
- Trained/found RVC voice models and their tuned settings.
- Proven data schemas (`pantry.json`, `vehicle.json`, `fitness.json`,
  the Financial Tracker link, etc.) — companion apps already depend on
  these shapes, no reason to change them.
- The three-tier model system (Local/Free Cloud/Paid Cloud) and the
  daily budget-cap concept from the Reasoning Upgrade project.

## WHAT GETS REBUILT, WITH FIXES BUILT IN FROM THE START

- Every agent bridge — same function as direct chat, never a second
  implementation, checked at build time.
- Memory saving and retrieval — filtered before saving, labeled as
  background when retrieved, for every agent from agent #1 onward.
- Every shared data file — file-locked from its first write.
- Every keyword gate — word-boundary matching, not substring matching.
- Secrets handling — `.env` + `.gitignore` from the first commit.

---

## PROJECT SETUP

- **New folder**, separate from the current `D:\Projects\NEXUS SYSTEM\`
  — the old folder stays exactly as it is, untouched, as a working
  reference to pull real prompt text, tuned configs, and working code
  from while rebuilding each piece. Nothing gets deleted from it.
- **A real git repo from day one this time** — now that secrets are
  already out of the old project's source (and the same discipline
  applies from the start here), there's no reason to defer this the way
  the original project did. Doesn't need to be public; a private repo
  is enough to get real version history instead of the old
  zip-backup-as-git-substitute system.
- This document and `NEXUS_LESSONS_LEARNED.md` live in the new project's
  own files, pasted into every rebuild session — same convention already
  used for every other sub-project here.

---

## BUILD + TEST ORDER

The core rule for the whole rebuild: **a feature is not "done" until it
has passed its own full L1-L5 test pass, in the same session it was
built or the very next one.** Nothing new gets built on top of something
untested.

**Phase 0 — Shared guardrails, built once, reused everywhere**
Since several of the lessons above (keyword-gate matching, memory
labeling, file locking) apply to *every* agent, build them once as
shared utility functions before the first agent, rather than
re-implementing (and re-breaking) them per agent:
- A word-boundary-safe keyword-matching helper
- A "wrap this as background context" memory-labeling helper
- A file-locking wrapper for read-modify-write JSON operations
- The `.env` / `.gitignore` setup

**Phase 1 — CIPHER** (matches the original build order — it helps build
everything after it)

**Phase 2 — NEXUS** (the hub; bridges to other agents built using the
Phase 0 "same function as direct chat" rule from the start, since there's
nothing to bridge to yet at this point except CIPHER)

**Phase 3 — ASSET** (a good third agent to validate the shared
guardrails against real, sensitive financial data before rolling them out
further)

**Phase 4 — ATLAS, DRIVE, STOCK, FLAME, CASE, PULSE**, one at a time,
each with its own full L1-L5 pass before starting the next. (Same order
as the original testing round, since it already reflects a sensible
dependency order — locally-hosted agents and simpler agents first.)

**Phase 5 — Dashboard UI**, then the companion tracker apps (Financial,
STOCK, DRIVE, Training, Usage, Progress, PULSE Tracker) — upgraded, not
rebuilt from scratch, once the agents underneath them are stable.

**Phase 6 — Voice pipeline, mobile app, Autonomous Build System** —
upgraded on top of ground that's already been proven solid, rather than
built in parallel with agents that are still changing underneath them.

Each phase gets: build → L1 → L2 → L3 → L4 → L5 → confirmed closed →
*then* move to the next phase. No building two agents in parallel before
either one is tested.

---

## OPEN DECISIONS — ANSWER BEFORE THE FIRST LINE OF CODE

1. What should the new folder be called? (e.g. `NEXUS SYSTEM v2`, a
   different name entirely — your call.)
2. Do you want the **old** NEXUS SYSTEM to keep running day-to-day while
   the rebuild happens (so you're not without your agents for months),
   or is a full switch-over once Phase 4 finishes acceptable?
3. Same tech stack as before (Python/FastAPI backend, Ollama for local
   models, Electron for the desktop shell), or is there anything about
   that stack you specifically want to reconsider given what My Claude
   taught you?
4. For the git repo — do you want me to walk you through setting that up
   as part of Phase 0, or hold off until Phase 1 (CIPHER) is actually
   built and there's real code to put in it?
5. Should Phase 0's shared guardrail functions get their *own* dedicated
   L1-L5 pass before Phase 1 starts (since every later agent depends on
   them working correctly), or is that overkill for utility functions
   this small?
