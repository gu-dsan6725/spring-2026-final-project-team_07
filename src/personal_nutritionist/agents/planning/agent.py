import os
import functools

from dotenv import load_dotenv
from strands import Agent, tool
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

_SYSTEM_PROMPT = """
You are the planning agent for a personal nutritionist app. Your job is to
build personalized meal plans based on the user's profile.

The user you are building a plan for is: {user_id}

Workflow for every planning request:
1. Call get_user_profile("{user_id}") to load the user's current profile from memory
2. Call estimate_calorie_target and estimate_protein_target to derive daily targets
3. Build a RecipeSearchFilters dict from the profile — only include fields that
   are set:
   - max_cost_per_serving, max_total_time, max_ingredient_count from constraints
   - exclude_ingredients: combine the user's allergies and disliked_ingredients
     into a single list (always include this if either list is non-empty)
4. Call build_day_plan_tool or build_week_plan_tool with:
   - filters_dict from step 3
   - calorie_target and protein_target from step 2
   - goal from the profile (fat_loss / muscle_gain / maintenance)
   - include_side=True (always — every day plan includes a lunch side and dinner side)
   - include_snack=True if meals_per_day is 4 or more
5. Present the plan clearly: meal names, calories, protein, cost, and servings per day.
   When a recipe has serving_multiplier > 1.0, show the serving count (e.g. "1.5 servings")
   so the user knows how much to prepare.

Guidelines:
- Always derive targets from the profile — never guess or assume
- If the profile is missing critical fields (no goal, no constraints), tell the
  user to complete their profile with the intake agent first
- When presenting a plan, summarize the daily totals and highlight how it
  aligns with their goal (fat loss = calorie deficit, muscle gain = protein focus)
- If the user asks to adjust the plan (cheaper, faster, higher protein), update
  the filters accordingly and rebuild — do not manually edit the plan
- include_snack should reflect whether the user's meals_per_day is 4 or more

## Structured output (required)

After presenting the plan in natural language, you MUST append the raw plan
dict as JSON wrapped in these exact tags on their own lines:

<plan_json>
{{"breakfast": ..., "lunch": ..., "dinner": ..., "snack": ..., "totals": {{...}}}}
</plan_json>

This is used by the orchestrator to validate the plan before presenting it.
Do not omit these tags. Do not add anything after the closing tag.
""".strip()


def _make_bound_tools(user_id: str):
    """
    Return versions of the plan-building tools with user_id pre-filled so the
    LLM never needs to pass it — cookbook exclusions are always applied.
    """
    @tool
    def build_day_plan_tool_bound(
        filters_dict: dict,
        include_snack: bool = False,
        include_side: bool = False,
        calorie_target: float | None = None,
        protein_target: float | None = None,
        goal: str = "maintenance",
    ) -> dict:
        """
        Build a full day meal plan scored against the user's nutrition targets.

        Args:
            filters_dict: A dict matching RecipeSearchFilters fields.
            include_snack: Whether to consider adding a snack.
            include_side: Whether to include a side dish with lunch and dinner.
            calorie_target: Daily calorie target.
            protein_target: Daily protein target.
            goal: User's goal (fat_loss / muscle_gain / maintenance).
        """
        return build_day_plan_tool(
            filters_dict=filters_dict,
            include_snack=include_snack,
            include_side=include_side,
            calorie_target=calorie_target,
            protein_target=protein_target,
            goal=goal,
            user_id=user_id,
        )

    @tool
    def build_week_plan_tool_bound(
        filters_dict: dict,
        n_days: int = 7,
        include_snack: bool = False,
        include_side: bool = False,
        calorie_target: float | None = None,
        protein_target: float | None = None,
        goal: str = "maintenance",
    ) -> list[dict]:
        """
        Build a multi-day meal plan scored against the user's nutrition targets.

        Args:
            filters_dict: A dict matching RecipeSearchFilters fields.
            n_days: Number of days to plan (default 7).
            include_snack: Whether to include a snack each day.
            include_side: Whether to include a side dish with lunch and dinner.
            calorie_target: Daily calorie target.
            protein_target: Daily protein target.
            goal: User's goal (fat_loss / muscle_gain / maintenance).
        """
        return build_week_plan_tool(
            filters_dict=filters_dict,
            n_days=n_days,
            include_snack=include_snack,
            include_side=include_side,
            calorie_target=calorie_target,
            protein_target=protein_target,
            goal=goal,
            user_id=user_id,
        )

    @tool
    def search_meals_tool_bound(slot: str, filters_dict: dict) -> list[dict]:
        """
        Search recipes eligible for a given meal slot.

        Args:
            slot: One of "breakfast", "lunch", "dinner", "snack".
            filters_dict: A dict matching RecipeSearchFilters fields.
        """
        return search_meals_tool(slot=slot, filters_dict=filters_dict, user_id=user_id)

    return build_day_plan_tool_bound, build_week_plan_tool_bound, search_meals_tool_bound


def create_planning_agent(user_id: str) -> Agent:
    model = AnthropicModel(
        model_id=os.getenv("PLANNING_MODEL", "claude-haiku-4-5-20251001"),
        max_tokens=8192,
    )
    build_day, build_week, search = _make_bound_tools(user_id)
    return Agent(
        model=model,
        system_prompt=_SYSTEM_PROMPT.format(user_id=user_id),
        tools=[
            get_user_profile,
            estimate_calorie_target,
            estimate_protein_target,
            search,
            build_day,
            build_week,
        ],
    )
