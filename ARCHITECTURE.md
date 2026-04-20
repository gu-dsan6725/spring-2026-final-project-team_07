# Personal Nutritionist — Architecture Summary

This document describes the current state of the system as of April 20, 2026.

---

## High-Level Design

The system is a **multi-agent pipeline** built with the [Strands SDK](https://github.com/strands-agents/sdk-python).
An orchestrator agent routes user requests to two specialized sub-agents and exposes
four tools to the user-facing conversation. All user state lives in **Mem0** cloud
memory, keyed by `user_id`.

```
User
 └── Orchestrator Agent  (claude-sonnet-4-6)
      │  Tools:
      │  ├── update_user_profile   → delegates to Intake Agent
      │  ├── build_meal_plan       → delegates to Planning Agent
      │  ├── audit_meal_plan       → deterministic inline check (no LLM)
      │  └── generate_shopping_list → aggregates ingredients from plan
      │
      ├── Intake Agent    (claude-sonnet-4-6)
      │    Collects / updates the user profile via natural language conversation.
      │
      └── Planning Agent  (claude-haiku-4-5-20251001)
           Builds day or multi-day meal plans from the recipe database.
```

---

## Agents

### Orchestrator
**File:** `src/personal_nutritionist/agents/orchestrator/agent.py`
**Tools file:** `src/personal_nutritionist/agents/orchestrator/tools.py`
**Model:** `claude-sonnet-4-6` (set via `ORCHESTRATOR_MODEL` env var)

The entry point for every user interaction. On each message the orchestrator detects
intent and routes accordingly:

- **Profile intent** → `update_user_profile` (spins up the Intake Agent)
- **Meal plan intent** → Plan-Audit Loop (see below)
- **Shopping list intent** → `generate_shopping_list` from the most recent plan
- **Out-of-scope** → declines gracefully without calling tools

**Plan-Audit Loop:**
1. Call `build_meal_plan` (delegates to Planning Agent)
2. Call `audit_meal_plan` (deterministic check — no LLM cost)
3. If audit passes → present plan to user
4. If audit fails → retry up to 2×, progressively relaxing `override_filters`

**Token management:** The Planning Agent returns slim recipe dicts (no `steps` or
`ingredient_details`). The orchestrator re-enriches the plan with full recipe data
from the DataFrame via title lookup before presenting it to the user.

---

### Intake Agent
**File:** `src/personal_nutritionist/agents/intake/agent.py`
**Model:** `claude-sonnet-4-6` (set via `INTAKE_MODEL` env var)

Handles open-ended conversation to collect and update a user's profile. Uses Sonnet
because it must handle natural language, resolve ambiguity, and decide when enough
information has been gathered.

**Tools available:**
| Tool | Purpose |
|---|---|
| `get_user_profile` | Load raw Mem0 memories (returns unstructured memory objects for LLM interpretation) |
| `update_goal` | Store nutrition goal (`fat_loss` / `muscle_gain` / `maintenance`) |
| `update_body_stats` | Store weight, height, age, sex |
| `update_activity_level` | Store activity level |
| `update_dietary_preferences` | Store allergies, dislikes, preferred categories |
| `update_meal_constraints` | Store budget, time limit, ingredient count, meals per day |
| `recall_user_info` | Semantic search over a user's memories |
| `reset_user_profile` | Delete all memories for a user |

**Note:** The intake agent's `get_user_profile` returns raw Mem0 memory objects for
the LLM — different from the planning version which returns a structured `UserProfile` dict.

---

### Planning Agent
**File:** `src/personal_nutritionist/agents/planning/agent.py`
**Model:** `claude-haiku-4-5-20251001` (set via `PLANNING_MODEL` env var)

Builds meal plans by following a deterministic tool-call workflow. Uses Haiku because
the workflow is structured with little open-ended reasoning.

**Instantiation:** `create_planning_agent(user_id="...")` — user_id baked into system prompt.

**Tools available:**
| Tool | Purpose |
|---|---|
| `get_user_profile` | Load structured `UserProfile` via `profile_from_memories` |
| `estimate_calorie_target` | Mifflin-St Jeor + activity multiplier + goal adjustment |
| `estimate_protein_target` | Goal-based g/lb rule |
| `search_meals_tool` | Search recipe dataset by slot and filters |
| `build_day_plan_tool` | Build a single-day plan (breakfast / lunch / dinner + sides) |
| `build_week_plan_tool` | Build a multi-day plan with no consecutive repeats |

**Workflow:**
1. `get_user_profile` → load profile
2. `estimate_calorie_target` + `estimate_protein_target` → derive daily targets
3. Build `RecipeSearchFilters` from profile constraints
4. `build_day_plan_tool` or `build_week_plan_tool`
5. Return slim plan JSON (no `steps` / `ingredient_details` — stripped to save tokens)

**Slim returns:** Tool responses exclude `steps` and `ingredient_details` to stay
within the model's token budget. The orchestrator re-attaches this data from the
recipe DataFrame by title lookup before presenting the plan.

---

## Audit (Deterministic Inline Check)

**File:** `src/personal_nutritionist/agents/orchestrator/tools.py` → `_deterministic_audit()`

The audit is a fast, zero-LLM-cost check run inside `audit_meal_plan` before the
plan reaches the user. It replaced a separate LLM-based Audit Agent to eliminate
latency and token costs.

**Checks performed:**
- All required meal slots are present (`breakfast`, `lunch`, `dinner`)
- No duplicate meal titles across slots
- No allergen violations — cross-references the user's `allergies` and
  `disliked_ingredients` against every meal's ingredient list

**Returns:** `{"passed": bool, "issues": [str]}`

The orchestrator retries planning up to 2× if audit fails, progressively widening
`override_filters` (`max_total_time`, `max_ingredient_count`). Calorie/protein
shortfalls are handled at the **planner level** via per-meal serving scaling (see
below) — audit does not retry for nutritional targets.

---

## Calorie Targeting via Serving Scaling

**File:** `src/personal_nutritionist/core/recipes.py` → `build_day_plan()`

Rather than relying on audit-loop retries to hit calorie targets, the planner scales
individual meal servings by ×1.5 increments:

1. Assign slot calorie fractions (breakfast 25%, lunch 28%, lunch_side 7%,
   dinner 28%, dinner_side 7%) summing to 95% of target — leaving 5% tolerance.
2. After all slots are filled, if total calories < 95% of target, iterate through
   meals in priority order (`lunch → dinner → breakfast → sides`) and apply ×1.5
   scaling to the first meal where doing so doesn't bust the cost cap.
3. Scaled meals carry a `serving_multiplier > 1.0` so the user sees how many
   portions to eat.

---

## Memory Layer

**File:** `src/personal_nutritionist/core/memory.py`

All user state is stored in **Mem0** cloud memory. Key design decisions:

- Every `add_memory` call stores the actual value in `metadata["value"]`
  alongside human-readable text. Mem0's LLM may rewrite the text, but metadata
  is preserved verbatim.
- `profile_from_memories(user_id)` reconstructs a `UserProfile`-compatible dict
  by reading `metadata["value"]` for each field. Falls back to regex parsing of
  memory text for any legacy memories without metadata.
- List fields (`allergies`, `disliked_ingredients`, `preferred_categories`) are
  coerced back to `list[str]` — Mem0 may serialize them as comma-separated strings.
- `get_memory` uses `client.get_all(filters={"user_id": user_id})` and unwraps
  the `{"results": [...]}` envelope. Using positional `user_id=` silently fails.

---

## Data Layer

**Files:** `src/personal_nutritionist/core/recipes.py`, `schemas.py`, `nutrition.py`

- Recipe data loaded from `data/recipes_final.csv` at startup via a cached
  singleton (`dependencies.py`).
- `RecipeSearchFilters` drives all recipe queries — unset fields are ignored.
- Allergen filtering strips trailing `s` from each exclusion term so
  `"peanuts"` matches both `"peanut butter"` and `"peanuts"` in ingredient lists.
- Calorie targets: **Mifflin-St Jeor BMR** × activity multiplier → −500 kcal
  (fat loss) / +250 kcal (muscle gain) / flat (maintenance).
- Protein targets: 0.9 g/lb (fat loss), 1.0 g/lb (muscle gain), 0.8 g/lb (maintenance).

---

## Model Selection

| Agent | Model | Rationale |
|---|---|---|
| Orchestrator | `claude-sonnet-4-6` | Intent routing, retry logic, multi-turn coordination |
| Intake | `claude-sonnet-4-6` | Open-ended conversation, ambiguity, memory handling |
| Planning | `claude-haiku-4-5-20251001` | Structured tool-call workflow, little open-ended reasoning |

All model IDs are overridable via env vars in `.env`.
The orchestrator uses `max_tokens=16384` to handle large 3-day plan + shopping list responses.

---

## Smoke Tests

**Directory:** `scripts/`

Scripts are numbered in run order. `01`–`04` test the data/tools layer without LLM
calls. `06`, `07`, `09` test agents end-to-end.

| Script | What it tests | Notes |
|---|---|---|
| `01` | Recipe loading and search | No LLM, no Mem0 |
| `02` | `get_user_profile` tool (planning version) | Requires `intake_test_user` in Mem0 |
| `03` | Calorie/protein target estimation | Requires `intake_test_user` in Mem0 |
| `04` | Day plan build via `recipes.py` | Requires `intake_test_user` in Mem0 |
| `06` | Intake agent — full onboarding conversation | Seeds `intake_test_user` in Mem0 |
| `07` | Planning agent — day + 3-day plan | Requires `06` to have run first |
| `09` | Orchestrator — end-to-end multi-turn test | Requires `06` to have run first |

**Run order for a clean test:**
```bash
PYTHONPATH=src uv run python scripts/06-intake-agent-test.py
PYTHONPATH=src uv run python scripts/07-planning-agent-test.py
PYTHONPATH=src uv run python scripts/09-orchestrator-test.py
```

All agent test output is written to `test-output/` (tracked in git).

---

## Evaluations

**Directory:** `evals/`

A Braintrust-based eval framework runs 29 test cases across five categories against
a pre-seeded `intake_test_user` profile and 10 additional user profiles with varied
demographics, goals, and dietary restrictions.

| File | Purpose |
|---|---|
| `evals/dataset.json` | 29 test cases with inputs, expected outputs, expected tools, and scorer metadata |
| `evals/seed_eval_users.py` | Seeds 10 eval user profiles in Mem0 (run once before evals) |
| `evals/eval.py` | Braintrust `Eval()` runner with 8 deterministic scorers |
| `evals/eval_checkpoint.json` | Per-case result cache (auto-saved; resume after crash by re-running) |
| `evals/eval_metrics.json` | Aggregated scorer results exported after each run |

**Test categories:** `meal_planning`, `profile_update`, `shopping_list`,
`dietary_restriction`, `out_of_scope`

**Scorers (all deterministic — no LLM cost):**
| Scorer | What it checks |
|---|---|
| `ToolSelection` | Recall of expected tools ± mild precision penalty for extra calls |
| `Latency` | Response time bands: <15s=1.0, <30s=0.75, <60s=0.5, <120s=0.25 |
| `NoError` | No traceback / exception / API error keywords in output |
| `ScopeAwareness` | Out-of-scope requests declined; in-scope requests answered |
| `PlanCompleteness` | Plan output contains breakfast, lunch, dinner, calories, protein, cost |
| `CalorieTarget` | Total calories within ±15% of user's target (reads from `plan_json` block) |
| `AllergenSafety` | No allergen ingredients in `plan_json` ingredient lists |
| `ShoppingList` | Shopping list output contains quantities and multiple line items |

**Running evals:**
```bash
# First time (or after adding new users):
PYTHONPATH=src uv run python evals/seed_eval_users.py

# Run evals (2-minute sleep between cases to avoid rate limits):
PYTHONPATH=src uv run python evals/eval.py

# Clear checkpoint and start fresh:
PYTHONPATH=src uv run python evals/eval.py --clear-checkpoint
```
