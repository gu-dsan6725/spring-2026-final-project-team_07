import os

from dotenv import load_dotenv
from strands import Agent
from strands.models.anthropic import AnthropicModel

from personal_nutritionist.agents.planning.tools import (
    get_user_profile,
    estimate_calorie_target,
    estimate_protein_target,
    search_meals_tool,
    build_day_plan_tool,
    build_week_plan_tool,
)

load_dotenv()

SYSTEM_PROMPT = """
You are the planning agent for a personal nutritionist app. Your job is to
build personalized meal plans based on the user's profile.

Workflow for every planning request:
1. Call get_user_profile to load the user's current profile from memory
2. Call estimate_calorie_target and estimate_protein_target to derive daily targets
3. Build a RecipeSearchFilters dict from the profile (max_cost_per_serving,
   max_total_time, max_ingredient_count) — only include fields that are set
4. Call build_day_plan_tool or build_week_plan_tool depending on the request
5. Present the plan clearly: meal names, calories, protein, and cost per day

Guidelines:
- Always derive targets from the profile — never guess or assume
- If the profile is missing critical fields (no goal, no constraints), tell the
  user to complete their profile with the intake agent first
- When presenting a plan, summarize the daily totals and highlight how it
  aligns with their goal (fat loss = calorie deficit, muscle gain = protein focus)
- If the user asks to adjust the plan (cheaper, faster, higher protein), update
  the filters accordingly and rebuild — do not manually edit the plan
- include_snack should reflect whether the user's meals_per_day is 4 or more
""".strip()


def create_planning_agent() -> Agent:
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
            search_meals_tool,
            build_day_plan_tool,
            build_week_plan_tool,
        ],
    )
