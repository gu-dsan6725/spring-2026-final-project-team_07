import logging

from strands import tool

from personal_nutritionist.core.dependencies import get_recipe_df
from personal_nutritionist.core.recipes import build_day_plan, build_week_plan, search_meals
from personal_nutritionist.core.memory import profile_from_memories
from personal_nutritionist.core.schemas import MealSlot, RecipeSearchFilters, UserProfile

from personal_nutritionist.core.nutrition import (
    estimate_calorie_target as calculate_calorie_target,
    estimate_protein_target as calculate_protein_target,
)

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# Side-channel: the orchestrator reads this after build_day/week_plan_tool runs
# so it doesn't have to rely on the LLM serializing <plan_json> tags correctly.
last_plan_data: list[dict] | None = None

@tool
def get_user_profile(user_id: str) -> dict:
    """
    Load the user's profile from Mem0 and return it as a UserProfile dict.
    Falls back to safe defaults for any fields not yet stored.

    Args:
        user_id: Unique user identifier.
    """
    defaults = {
        "user_id": user_id,
        "goal": "maintenance",
        "activity_level": "moderate",
        "meals_per_day": 3,
        "preferred_categories": [],
        "disliked_ingredients": [],
        "allergies": [],
    }
    from_memory = profile_from_memories(user_id)
    merged = {**defaults, **from_memory}
    profile = UserProfile(**merged)
    logger.info("get_user_profile user=%s goal=%s", user_id, profile.goal)
    return profile.model_dump()

# estimate_calorie_target(...)
@tool
def estimate_calorie_target(profile_dict: dict) -> float:
    """
    Estimate daily calorie target from a user profile.
    """
    profile = UserProfile(**profile_dict)
    target = calculate_calorie_target(profile)
    logger.info("Estimated calorie target=%s for user_id=%s", target, profile.user_id)
    return target

# estimate_protein_target(...)
@tool
def estimate_protein_target(profile_dict: dict) -> float:
    """
    Estimate daily protein target from a user profile.
    """
    profile = UserProfile(**profile_dict)
    target = calculate_protein_target(profile)
    logger.info("Estimated protein target=%s for user_id=%s", target, profile.user_id)
    return target

@tool
def search_meals_tool(slot: str, filters_dict: dict, user_id: str | None = None) -> list[dict]:
    """
    Search recipes eligible for a given meal slot (breakfast, lunch, dinner, snack)
    using the provided filters. Returns a list of matching recipes as dicts.

    Args:
        slot: One of "breakfast", "lunch", "dinner", "snack".
        filters_dict: A dict matching RecipeSearchFilters fields.
        user_id: Optional user ID to apply cookbook exclusions and custom recipes.
    """
    meal_slot: MealSlot = slot  # type: ignore[assignment]
    filters = RecipeSearchFilters(**filters_dict)
    df = get_recipe_df(user_id=user_id)
    recipes = search_meals(df, meal_slot, filters)
    logger.info("search_meals slot=%s returned %s results", slot, len(recipes))
    return [r.model_dump() for r in recipes]


@tool
def build_week_plan_tool(
    filters_dict: dict,
    n_days: int = 7,
    include_snack: bool = False,
    include_side: bool = False,
    calorie_target: float | None = None,
    protein_target: float | None = None,
    goal: str = "maintenance",
    user_id: str | None = None,
) -> list[dict]:
    """
    Build a multi-day meal plan scored against the user's nutrition targets.
    Meals are selected to hit per-slot calorie targets and maximise protein,
    with soft variety penalties to diversify categories and clusters across days.

    Args:
        filters_dict: A dict matching RecipeSearchFilters fields.
        n_days: Number of days to plan (default 7).
        include_snack: Whether to include a snack each day (only added if needed).
        include_side: Whether to include a side dish with lunch and dinner.
        calorie_target: Daily calorie target — pass from estimate_calorie_target.
        protein_target: Daily protein target — pass from estimate_protein_target.
        goal: User's goal (fat_loss / muscle_gain / maintenance).
        user_id: Optional user ID to apply cookbook exclusions and custom recipes.
    """
    filters = RecipeSearchFilters(**filters_dict)
    df = get_recipe_df(user_id=user_id)
    plans = build_week_plan(
        df, filters,
        n_days=n_days,
        include_snack=include_snack,
        include_side=include_side,
        calorie_target=calorie_target,
        protein_target=protein_target,
        goal=goal,
    )
    logger.info("build_week_plan n_days=%s include_snack=%s include_side=%s", n_days, include_snack, include_side)
    _SLIM = {"steps", "ingredient_details"}
    result = [
        {
            "breakfast": p.breakfast.model_dump(exclude=_SLIM),
            "lunch": p.lunch.model_dump(exclude=_SLIM),
            "lunch_side": p.lunch_side.model_dump(exclude=_SLIM) if p.lunch_side else None,
            "dinner": p.dinner.model_dump(exclude=_SLIM),
            "dinner_side": p.dinner_side.model_dump(exclude=_SLIM) if p.dinner_side else None,
            "snack": p.snack.model_dump(exclude=_SLIM) if p.snack else None,
            "totals": {
                "calories": p.total_calories,
                "protein": p.total_protein,
                "cost": p.total_cost,
            },
        }
        for p in plans
    ]
    global last_plan_data
    last_plan_data = result
    return result


@tool
def build_day_plan_tool(
    filters_dict: dict,
    include_snack: bool = False,
    include_side: bool = False,
    calorie_target: float | None = None,
    protein_target: float | None = None,
    goal: str = "maintenance",
    user_id: str | None = None,
) -> dict:
    """
    Build a full day meal plan scored against the user's nutrition targets.
    Meals are selected to hit per-slot calorie targets and maximise protein,
    with soft variety penalties. Snack is only added when needed to close a
    calorie or protein gap.

    Args:
        filters_dict: A dict matching RecipeSearchFilters fields.
        include_snack: Whether to consider adding a snack.
        include_side: Whether to include a side dish with lunch and dinner.
        calorie_target: Daily calorie target — pass from estimate_calorie_target.
        protein_target: Daily protein target — pass from estimate_protein_target.
        goal: User's goal (fat_loss / muscle_gain / maintenance).
        user_id: Optional user ID to apply cookbook exclusions and custom recipes.
    """
    filters = RecipeSearchFilters(**filters_dict)
    df = get_recipe_df(user_id=user_id)
    plan = build_day_plan(
        df, filters,
        include_snack=include_snack,
        include_side=include_side,
        calorie_target=calorie_target,
        protein_target=protein_target,
        goal=goal,
    )
    logger.info(
        "build_day_plan calories=%.0f protein=%.1fg cost=$%.2f",
        plan.total_calories,
        plan.total_protein,
        plan.total_cost,
    )
    _SLIM = {"steps", "ingredient_details"}
    result = {
        "breakfast": plan.breakfast.model_dump(exclude=_SLIM),
        "lunch": plan.lunch.model_dump(exclude=_SLIM),
        "lunch_side": plan.lunch_side.model_dump(exclude=_SLIM) if plan.lunch_side else None,
        "dinner": plan.dinner.model_dump(exclude=_SLIM),
        "dinner_side": plan.dinner_side.model_dump(exclude=_SLIM) if plan.dinner_side else None,
        "snack": plan.snack.model_dump(exclude=_SLIM) if plan.snack else None,
        "totals": {
            "calories": plan.total_calories,
            "protein": plan.total_protein,
            "cost": plan.total_cost,
        },
    }
    global last_plan_data
    last_plan_data = [result]
    return result