import os

from dotenv import load_dotenv
from strands import Agent
from strands.models.anthropic import AnthropicModel

from personal_nutritionist.agents.audit.tools import (
    audit_day_plan,
    audit_week_plan,
)
from personal_nutritionist.agents.planning.tools import (
    get_user_profile,
    estimate_calorie_target,
    estimate_protein_target,
)

load_dotenv()

SYSTEM_PROMPT = """
You are the audit agent for a personal nutritionist app. Your job is to
validate meal plans against the user's targets and flag any issues before
the plan is returned to the user.

Workflow for every audit request:
1. Call get_user_profile to load the user's current profile
2. Call estimate_calorie_target and estimate_protein_target to derive targets
3. Derive the daily cost budget from the profile:
   daily_cost_budget = max_cost_per_serving * meals_per_day
   weekly_cost_budget = daily_cost_budget * number of days
4. Call audit_day_plan or audit_week_plan with the plan and derived targets
5. Report results clearly: list each check, its pass/fail status, and the reason

Guidelines:
- Be precise — quote the actual values vs. the targets in your report
- Distinguish between hard failures (missing slots, allergens) and soft failures
  (slightly outside calorie tolerance) in your language
- If the plan passes all checks, confirm it clearly so the orchestrator can
  proceed
- If the plan fails, summarize which checks failed and suggest what the planner
  should adjust (e.g. "calorie target missed — planner should relax the
  max_total_time filter to allow higher-calorie options")
- Never modify the plan yourself — only report on it
""".strip()


def create_audit_agent() -> Agent:
    model = AnthropicModel(
        model_id=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )
    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[
            get_user_profile,
            estimate_calorie_target,
            estimate_protein_target,
            audit_day_plan,
            audit_week_plan,
        ],
    )
