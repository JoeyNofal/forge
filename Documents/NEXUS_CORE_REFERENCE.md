# NEXUS SYSTEM — CORE REFERENCE (v2)

**What it is:** a private, personal AI ecosystem built and run entirely
on Youssef's own Windows 11 laptop — 9 distinct AI agents, each with its
own personality, memory, tools, and area of responsibility, designed to
feel like real characters, not a generic chatbot.

**Founding principles:**
- Local-first and private by default — sensitive data (finances,
  personal conversations) never has to leave the laptop unless a cloud
  model is chosen for better reasoning
- No required subscriptions — cloud model usage (Claude, Gemini) is
  optional, metered, and capped; the system works fully offline on
  local models at zero ongoing cost
- Agents should feel alive — distinct character voice and personality,
  and (where wired up) a distinct spoken voice, not a generic assistant
  with a different system prompt
- Youssef is a complete beginner at programming — built entirely by
  directing Claude, either manual copy-paste or (previously) an
  Autonomous Build System

## Agent Roster

| Agent | Full Name | Role | Character | Restriction |
|---|---|---|---|---|
| N.E.X.U.S. | Neural Executive Unified System | Central butler, life organizer, action-taker | Alfred Pennyworth — warm, measured, dry wit | None — fully unrestricted |
| C.I.P.H.E.R. | Computational Intelligence for Programming, Heuristics & Execution Runtime | Programmer agent, executes real build tasks | JARVIS — precise, efficient, quietly competent | Programming only |
| A.S.S.E.T. | Automated System for Strategic Economic Tracking | Financial advisor, reads real financial data | Walter White / Heisenberg — direct, controlled intensity | Finance only |
| A.T.L.A.S. | Athletic Training, Lifestyle & Analysis System | Fitness & swimming coach | David Goggins — raw, blunt, zero excuses | Fitness only |
| D.R.I.V.E. | Diagnostic Routing, Intelligence & Vehicle Engineering | Car maintenance advisor | Jeremy Clarkson — dramatic, opinionated | Automotive only |
| F.L.A.M.E. | Food Logistics & Automated Meal Engine | Personal chef, checks STOCK before suggesting meals | Gordon Ramsay (teaching mode) — passionate, encouraging | Food/cooking/nutrition only — **all suggestions must be halal, non-negotiable** |
| S.T.O.C.K. | System for Tracking Orders, Consumables & Kitchenware | Pantry & grocery tracker | Calm, grounded — no celebrity voice | Grocery/pantry only |
| C.A.S.E. | Compliance, Analysis & Strategic Evaluation | Legal advisor, defaults to Indiana/St. Joseph County | Ultron (James Spader) — philosophical, precise, dry | Legal only |
| P.U.L.S.E. | Performance, Utilization, Logging & System Evaluation | Computer health — diagnostics, cleanup, monitoring | Baymax — gentle, literal, caring | Computer/tech only |

## Model tiers (already proven, carries over)

Every agent except ASSET can run on **Local** (Gemma via Ollama, free) /
**Free Cloud** (Gemini Flash, free) / **Paid Cloud** (Claude Sonnet 5,
metered, $10/day cap). ASSET is permanently local-only — the one
privacy-driven exception, never part of the switcher.

## Tech stack (carries over, revisit only if there's a specific reason to)

- **Ollama** — local models
- **Claude Sonnet 5** (Anthropic API) — paid cloud tier
- **Gemini 2.5 Flash** (Google API) — free cloud tier
- **Python 3.11 + FastAPI/Uvicorn** — backend
- **ChromaDB** — per-agent vector memory
- **SQLite** — chat history, uploads, spend tracking
- **Electron + HTML/CSS/JS** — desktop app
- **SerpApi** — web search
- **Whisper (local GPU) + XTTS v2 + RVC** — voice input/output
