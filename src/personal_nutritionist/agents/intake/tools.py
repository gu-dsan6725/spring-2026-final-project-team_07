import json
import logging

from strands import tool

from personal_nutritionist.core.memory import (
    add_memory,
    delete_all_memories,
    get_memory,
    search_memory,
)
from personal_nutritionist.core.schemas import UserProfile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)


@tool
def get_user_profile(user_id: str) -> dict:
    """
    Retrieve the user's full profile by loading all memories and reconstructing
    a UserProfile. Returns a dict of profile fields.

    If the user has no stored memories yet, returns an empty dict.

    Args:
        user_id: Unique user identifier.
    """
    memories = get_memory(user_id)
    if not memories:
        logger.info("get_user_profile user=%s — no memories found", user_id)
        return {}

    # Build a single text block from all memories for the LLM to interpret,
    # and also return the raw memories so the agent can act on them.
    memory_text = "\n".join(m.get("memory", "") for m in memories)
    logger.info("get_user_profile user=%s — %s memories loaded", user_id, len(memories))
    return {"user_id": user_id, "memories": memories, "summary": memory_text}


@tool
def update_goal(user_id: str, goal: str) -> dict:
    """
    Store or update the user's nutrition goal.

    Args:
        user_id: Unique user identifier.
        goal: One of "fat_loss", "muscle_gain", or "maintenance".
    """
    valid = {"fat_loss", "muscle_gain", "maintenance"}
    if goal not in valid:
        return {"status": "error", "message": f"goal must be one of {valid}"}
    result = add_memory(user_id, f"User's nutrition goal is {goal}.", metadata={"field": "goal"})
    logger.info("update_goal user=%s goal=%s", user_id, goal)
    return {"status": "ok", "goal": goal}


@tool
def update_body_stats(
    user_id: str,
    weight_lbs: float | None = None,
    height_in: float | None = None,
    age: int | None = None,
    sex: str | None = None,
) -> dict:
    """
    Store or update the user's body stats. Only pass the fields being updated.

    Args:
        user_id: Unique user identifier.
        weight_lbs: Body weight in pounds.
        height_in: Height in inches.
        age: Age in years.
        sex: "male" or "female".
    """
    stored = []
    if weight_lbs is not None:
        add_memory(user_id, f"User weighs {weight_lbs} lbs.", metadata={"field": "weight_lbs"})
        stored.append(f"weight_lbs={weight_lbs}")
    if height_in is not None:
        add_memory(user_id, f"User's height is {height_in} inches.", metadata={"field": "height_in"})
        stored.append(f"height_in={height_in}")
    if age is not None:
        add_memory(user_id, f"User is {age} years old.", metadata={"field": "age"})
        stored.append(f"age={age}")
    if sex is not None:
        if sex not in {"male", "female"}:
            return {"status": "error", "message": "sex must be 'male' or 'female'"}
        add_memory(user_id, f"User's sex is {sex}.", metadata={"field": "sex"})
        stored.append(f"sex={sex}")
    logger.info("update_body_stats user=%s stored=%s", user_id, stored)
    return {"status": "ok", "updated": stored}


@tool
def update_activity_level(user_id: str, activity_level: str) -> dict:
    """
    Store or update the user's activity level.

    Args:
        user_id: Unique user identifier.
        activity_level: One of "sedentary", "light", "moderate", "active", "very_active".
    """
    valid = {"sedentary", "light", "moderate", "active", "very_active"}
    if activity_level not in valid:
        return {"status": "error", "message": f"activity_level must be one of {valid}"}
    add_memory(
        user_id,
        f"User's activity level is {activity_level}.",
        metadata={"field": "activity_level"},
    )
    logger.info("update_activity_level user=%s level=%s", user_id, activity_level)
    return {"status": "ok", "activity_level": activity_level}


@tool
def update_dietary_preferences(
    user_id: str,
    preferred_categories: list[str] | None = None,
    disliked_ingredients: list[str] | None = None,
    allergies: list[str] | None = None,
) -> dict:
    """
    Store or update the user's dietary preferences and restrictions.
    Only pass the fields being updated.

    Args:
        user_id: Unique user identifier.
        preferred_categories: Meal categories the user enjoys (e.g. ["Comfort Meals"]).
        disliked_ingredients: Ingredients the user dislikes but isn't allergic to.
        allergies: Ingredients the user is allergic to.
    """
    stored = []
    if preferred_categories is not None:
        add_memory(
            user_id,
            f"User's preferred meal categories are: {', '.join(preferred_categories)}.",
            metadata={"field": "preferred_categories"},
        )
        stored.append("preferred_categories")
    if disliked_ingredients is not None:
        add_memory(
            user_id,
            f"User dislikes these ingredients: {', '.join(disliked_ingredients)}.",
            metadata={"field": "disliked_ingredients"},
        )
        stored.append("disliked_ingredients")
    if allergies is not None:
        add_memory(
            user_id,
            f"User is allergic to: {', '.join(allergies)}.",
            metadata={"field": "allergies"},
        )
        stored.append("allergies")
    logger.info("update_dietary_preferences user=%s stored=%s", user_id, stored)
    return {"status": "ok", "updated": stored}


@tool
def update_meal_constraints(
    user_id: str,
    max_cost_per_serving: float | None = None,
    max_total_time: int | None = None,
    max_ingredient_count: int | None = None,
    meals_per_day: int | None = None,
) -> dict:
    """
    Store or update the user's practical meal constraints.
    Only pass the fields being updated.

    Args:
        user_id: Unique user identifier.
        max_cost_per_serving: Maximum cost per serving in USD.
        max_total_time: Maximum total cook+prep time in minutes.
        max_ingredient_count: Maximum number of ingredients per recipe.
        meals_per_day: Number of meals per day (1-6).
    """
    stored = []
    if max_cost_per_serving is not None:
        add_memory(
            user_id,
            f"User's maximum cost per serving is ${max_cost_per_serving:.2f}.",
            metadata={"field": "max_cost_per_serving"},
        )
        stored.append(f"max_cost_per_serving={max_cost_per_serving}")
    if max_total_time is not None:
        add_memory(
            user_id,
            f"User wants meals that take no more than {max_total_time} minutes.",
            metadata={"field": "max_total_time"},
        )
        stored.append(f"max_total_time={max_total_time}")
    if max_ingredient_count is not None:
        add_memory(
            user_id,
            f"User prefers recipes with at most {max_ingredient_count} ingredients.",
            metadata={"field": "max_ingredient_count"},
        )
        stored.append(f"max_ingredient_count={max_ingredient_count}")
    if meals_per_day is not None:
        add_memory(
            user_id,
            f"User eats {meals_per_day} meals per day.",
            metadata={"field": "meals_per_day"},
        )
        stored.append(f"meals_per_day={meals_per_day}")
    logger.info("update_meal_constraints user=%s stored=%s", user_id, stored)
    return {"status": "ok", "updated": stored}


@tool
def recall_user_info(user_id: str, query: str) -> dict:
    """
    Semantic search over the user's memories to answer a specific question
    (e.g. "what are this user's allergies?", "what is the user's goal?").

    Args:
        user_id: Unique user identifier.
        query: Natural-language question about the user.
    """
    results = search_memory(user_id, query)
    logger.info("recall_user_info user=%s query='%s' hits=%s", user_id, query, len(results))
    return {
        "query": query,
        "results": [r.get("memory", "") for r in results],
    }


@tool
def reset_user_profile(user_id: str) -> dict:
    """
    Delete all stored memories for the user, resetting their profile.
    Use only when the user explicitly requests a full reset.

    Args:
        user_id: Unique user identifier.
    """
    delete_all_memories(user_id)
    logger.info("reset_user_profile user=%s", user_id)
    return {"status": "ok", "message": f"All memories deleted for user '{user_id}'."}
