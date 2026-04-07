# Personal Nutritionist — Architecture Summary

This document describes the current state of the system as of April 7, 2026.
Written for a partner onboarding to the codebase mid-project.

---

## High-Level Design

The system is a **multi-agent pipeline** built with the [Strands SDK](https://github.com/strands-agents/sdk-python).
Three specialized agents handle distinct responsibilities and will be coordinated
by an orchestrator (not yet implemented). Each agent is stateless — all user
state lives in Mem0 cloud memory, keyed by `user_id`.

```
User
 └── Orchestrator (TODO)
      ├── Intake Agent       — collects & updates the user profile
      ├── Planning Agent     — builds day/week meal plans
      └── Audit Agent        — validates plans before returning them to the user
```

---

## Agents

### Intake Agent
**File:** `src/personal_nutritionist/agents/intake/agent.py`
**Model:** `claude-sonnet-4-6` (set via `INTAKE_MODEL` env var)

Handles open-ended conversation with the user to collect and update their profile.
Uses Sonnet because it needs to handle natural language, ask follow-up questions,
and decide when enough information has been gathered.

**Tools available:**
| Tool | Purpose |
|---|---|
| `get_user_profile` | Load raw Mem0 memories for a user |
| `update_goal` | Store nutrition goal (fat_loss / muscle_gain / maintenance) |
| `update_body_stats` | Store weight, height, age, sex |
| `update_activity_level` | Store activity level |
| `update_dietary_preferences` | Store allergies, dislikes, preferred categories |
| `update_meal_constraints` | Store budget, time, ingredient count, meals per day |
| `recall_user_info` | Semantic search over a user's memories |
| `reset_user_profile` | Delete all memories for a user |

**Important:** The intake agent's `get_user_profile` returns raw Mem0 memory
objects for the LLM to interpret — it is different from the planning/audit
version which returns a structured `UserProfile` dict.

---

### Planning Agent
**File:** `src/personal_nutritionist/agents/planning/agent.py`
**Model:** `claude-haiku-4-5-20251001` (set via `PLANNING_MODEL` env var)

Builds meal plans by following a deterministic tool-call workflow. Uses Haiku
because the workflow is structured — there is little open-ended reasoning needed.

**Instantiation:** `create_planning_agent(user_id="...")` — the `user_id` is
baked into the system prompt so the agent always knows who it's working for.
The orchestrator is responsible for passing the correct `user_id` at construction.

**Tools available:**
| Tool | Purpose |
|---|---|
| `get_user_profile` | Load structured `UserProfile` from Mem0 via `profile_from_memories` |
| `estimate_calorie_target` | Mifflin-St Jeor + activity multiplier + goal adjustment |
| `estimate_protein_target` | Goal-based g/lb rule |
| `search_meals_tool` | Search recipe dataset by slot and filters |
| `build_day_plan_tool` | Build a single day plan (breakfast/lunch/dinner/snack) |
| `build_week_plan_tool` | Build a multi-day plan with no consecutive repeats |

**Workflow the agent is instructed to follow:**
1. `get_user_profile(user_id)` → load profile
2. `estimate_calorie_target` + `estimate_protein_target` → derive daily targets
3. Build `RecipeSearchFilters` from profile constraints
4. `build_day_plan_tool` or `build_week_plan_tool`
5. Present the plan with totals and goal alignment

---

### Audit Agent
**File:** `src/personal_nutritionist/agents/audit/agent.py`
**Model:** `claude-haiku-4-5-20251001` (set via `AUDIT_MODEL` env var)

Validates a plan against the user's targets before it reaches the user.
If it fails, it tells the planner specifically what to adjust — it never
modifies the plan itself.

**Instantiation:** `create_audit_agent(user_id="...")` — same pattern as planning.

**Tools available:**
| Tool | Purpose |
|---|---|
| `get_user_profile` | Load structured `UserProfile` |
| `estimate_calorie_target` | Derive calorie target for comparison |
| `estimate_protein_target` | Derive protein target for comparison |
| `audit_day_plan` | Run all checks on a single day plan |
| `audit_week_plan` | Run per-day + week-level checks on a multi-day plan |

**Day plan checks:** slots present, no duplicate meals, meal slot eligibility,
calories ±15% of target, protein ±10% of target, cost within daily budget.

**Week plan checks:** all of the above per day, plus average calorie/protein
targets across the week, total weekly cost, and meal variety
(no single meal on >40% of days).

---

## Memory Layer

**File:** `src/personal_nutritionist/core/memory.py`

All user state is stored in **Mem0** cloud memory. Key design decisions:

- Every `add_memory` call stores the actual value in `metadata["value"]`
  alongside the human-readable text. This is critical — Mem0's LLM may
  rewrite the stored text, but metadata is preserved verbatim.
- `profile_from_memories(user_id)` reconstructs a `UserProfile`-compatible
  dict by reading `metadata["value"]` for each field. It falls back to
  regex parsing of memory text for any legacy memories written before the
  metadata approach was adopted.
- List fields (`allergies`, `disliked_ingredients`, `preferred_categories`)
  are coerced back to `list[str]` in `profile_from_memories` because Mem0
  serializes them as comma-separated strings.
- `get_memory` uses `client.get_all(filters={"user_id": user_id})` and
  unwraps the `{"results": [...]}` envelope — the Mem0 v2 API requires
  filters and wraps results; using positional `user_id=` silently fails.

---

## Data Layer

**Files:** `src/personal_nutritionist/core/recipes.py`, `schemas.py`, `nutrition.py`

- Recipe data is loaded from `data/recipes_final.csv` at startup via a
  cached singleton (`dependencies.py`).
- `RecipeSearchFilters` drives all recipe queries — pass only the fields
  that are set; unset fields are ignored.
- Calorie targets use **Mifflin-St Jeor BMR** × activity multiplier, then
  −500 kcal for fat loss, +250 for muscle gain, flat for maintenance.
- Protein targets use a simple g/lb rule: 0.9 (fat loss), 1.0 (muscle gain),
  0.8 (maintenance).

---

## Model Selection

| Agent | Model | Rationale |
|---|---|---|
| Intake | `claude-sonnet-4-6` | Open-ended conversation, ambiguity, memory handling |
| Orchestrator (TODO) | `claude-sonnet-4-6` | Intent routing, retry logic, multi-turn coordination |
| Planning | `claude-haiku-4-5-20251001` | Structured tool-call workflow, little open-ended reasoning |
| Audit | `claude-haiku-4-5-20251001` | Deterministic checks, structured output |

All model IDs are overridable via env vars in `.env`.

---

## Smoke Tests

**Directory:** `scripts/`

Scripts are numbered and run in order. 01–05 test the data/tools layer directly
(no LLM calls). 06–08 test the agents end-to-end.

| Script | What it tests | Notes |
|---|---|---|
| `01` | Recipe loading and search | |
| `02` | `get_user_profile` tool (planning version) | Requires `tyler` in Mem0 |
| `03` | Calorie/protein target estimation | Requires `tyler` in Mem0 |
| `04` | Day plan build | Requires `tyler` in Mem0 |
| `05` | Audit tools (day + week) | No Mem0 needed |
| `06` | Intake agent — full onboarding conversation | Seeds `intake_test_user` in Mem0 |
| `07` | Planning agent — day + 3-day plan | Requires `06` to have run first |
| `08` | Audit agent — real plan + deliberately bad plan | Requires `06` to have run first |

All agent test output is written to `test-output/` (tracked in git so partners
can review without rerunning).

**Run order for a clean test:**
```bash
PYTHONPATH=src python scripts/06-intake-agent-test.py
PYTHONPATH=src python scripts/07-planning-agent-test.py
PYTHONPATH=src python scripts/08-audit-agent-test.py
```

---

## What's Next

The only missing piece is the **Orchestrator**, which needs to:
1. Receive a user request and identify intent (update profile vs. build plan)
2. Route to the intake agent for profile updates
3. Invoke `create_planning_agent(user_id)` → get a plan
4. Invoke `create_audit_agent(user_id)` → validate the plan
5. Retry planning with relaxed filters if audit fails (the audit agent's
   failure messages are designed to tell the planner exactly what to relax)
6. Return the approved plan to the user
