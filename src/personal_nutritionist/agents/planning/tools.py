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
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

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
def search_meals_tool(slot: str, filters_dict: dict) -> list[dict]:
    """
    Search recipes eligible for a given meal slot (breakfast, lunch, dinner, snack)
    using the provided filters. Returns a list of matching recipes as dicts.

    Args:
        slot: One of "breakfast", "lunch", "dinner", "snack".
        filters_dict: A dict matching RecipeSearchFilters fields.
    """
    meal_slot: MealSlot = slot  # type: ignore[assignment]
    filters = RecipeSearchFilters(**filters_dict)
    df = get_recipe_df()
    recipes = search_meals(df, meal_slot, filters)
    logger.info("search_meals slot=%s returned %s results", slot, len(recipes))
    return [r.model_dump() for r in recipes]


@tool
def build_week_plan_tool(
    filters_dict: dict, n_days: int = 7, include_snack: bool = False
) -> list[dict]:
    """
    Build a multi-day meal plan with no duplicate meals within a day and no
    meal repeated on consecutive days.

    Args:
        filters_dict: A dict matching RecipeSearchFilters fields.
        n_days: Number of days to plan (default 7).
        include_snack: Whether to include a snack each day.
    """
    filters = RecipeSearchFilters(**filters_dict)
    df = get_recipe_df()
    plans = build_week_plan(df, filters, n_days=n_days, include_snack=include_snack)
    logger.info("build_week_plan n_days=%s include_snack=%s", n_days, include_snack)
    return [
        {
            "breakfast": p.breakfast.model_dump(),
            "lunch": p.lunch.model_dump(),
            "dinner": p.dinner.model_dump(),
            "snack": p.snack.model_dump() if p.snack else None,
            "totals": {
                "calories": p.total_calories,
                "protein": p.total_protein,
                "cost": p.total_cost,
            },
        }
        for p in plans
    ]


@tool
def build_day_plan_tool(filters_dict: dict, include_snack: bool = False) -> dict:
    """
    Build a full day meal plan (breakfast, lunch, dinner, optional snack)
    using the provided filters. Returns a DayPlan as a dict with totals.

    Args:
        filters_dict: A dict matching RecipeSearchFilters fields.
        include_snack: Whether to include a snack in the plan.
    """
    filters = RecipeSearchFilters(**filters_dict)
    df = get_recipe_df()
    plan = build_day_plan(df, filters, include_snack=include_snack)
    logger.info(
        "build_day_plan calories=%.0f protein=%.1fg cost=$%.2f",
        plan.total_calories,
        plan.total_protein,
        plan.total_cost,
    )
    return {
        "breakfast": plan.breakfast.model_dump(),
        "lunch": plan.lunch.model_dump(),
        "dinner": plan.dinner.model_dump(),
        "snack": plan.snack.model_dump() if plan.snack else None,
        "totals": {
            "calories": plan.total_calories,
            "protein": plan.total_protein,
            "cost": plan.total_cost,
        },
    }