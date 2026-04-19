import json
import logging
import re

from strands import tool

from personal_nutritionist.agents.audit.agent import create_audit_agent
from personal_nutritionist.agents.intake.agent import create_intake_agent
from personal_nutritionist.agents.planning.agent import create_planning_agent
from personal_nutritionist.core.memory import profile_from_memories
from personal_nutritionist.core.nutrition import (
    estimate_calorie_target,
    estimate_protein_target,
)
from personal_nutritionist.core.schemas import UserProfile

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

_PROFILE_DEFAULTS = {
    "goal": "maintenance",
    "activity_level": "moderate",
    "meals_per_day": 3,
    "preferred_categories": [],
    "disliked_ingredients": [],
    "allergies": [],
}


def _load_profile(user_id: str) -> UserProfile:
    from_memory = profile_from_memories(user_id)
    merged = {**_PROFILE_DEFAULTS, **from_memory}
    return UserProfile(**merged)


def _extract_tag(text: str, tag: str) -> str | None:
    """Extract content between <tag>...</tag> in an agent response."""
    match = re.search(rf"<{tag}>(.*?)</{tag}>", text, re.DOTALL)
    return match.group(1).strip() if match else None


@tool
def update_user_profile(user_id: str, message: str) -> str:
    """
    Delegate a profile-related message to the intake agent.
    Use for any request to update, view, or collect the user's profile
    (goal, body stats, allergies, preferences, meal constraints).

    Args:
        user_id: The user's unique identifier.
        message: The user's message about their profile.
    """
    agent = create_intake_agent()
    response = agent(f"My user ID is {user_id}. {message}")
    logger.info("update_user_profile user=%s", user_id)
    return str(response)


@tool
def build_meal_plan(
    user_id: str,
    plan_type: str = "day",
    n_days: int = 1,
    include_snack: bool = False,
    override_filters: dict | None = None,
) -> dict:
    """
    Delegate a meal plan request to the planning agent and return the
    structured plan along with the user's nutrition targets.

    Args:
        user_id: The user's unique identifier.
        plan_type: "day" for a single day plan, "week" for multiple days.
        n_days: Number of days — only used when plan_type is "week".
        include_snack: Whether to add a snack slot to each day.
        override_filters: Optional RecipeSearchFilters fields to override the
            profile defaults (e.g. {"max_total_time": 60} to relax time on retry).
    """
    # Compute targets deterministically — no LLM cost for this part
    profile = _load_profile(user_id)

    # Check for a recognized user with enough data to estimate targets
    missing = [
        f for f in ("goal", "weight_lbs", "height_in", "age", "sex")
        if getattr(profile, f) is None
    ]
    if missing or not profile_from_memories(user_id):
        logger.info("build_meal_plan user=%s incomplete profile missing=%s", user_id, missing)
        return {
            "error": (
                "I don't have enough information about you yet to build a plan. "
                "Please tell me your goal, weight, height, age, sex, activity level, "
                "and any dietary preferences or constraints so I can get started."
            )
        }

    calorie_target = estimate_calorie_target(profile)
    protein_target = estimate_protein_target(profile)
    daily_budget = (profile.max_cost_per_serving or 999.0) * profile.meals_per_day

    # Build the request message for the planning agent
    if plan_type == "week":
        request = f"Build me a {n_days}-day meal plan."
    else:
        request = "Build me a day plan."
    if include_snack:
        request += " Include a snack."
    if override_filters:
        request += f" Use these filter overrides: {json.dumps(override_filters)}."

    # Delegate to the planning agent
    planning_agent = create_planning_agent(user_id=user_id)
    response = str(planning_agent(request))

    # Extract the structured plan from <plan_json> tags
    plan_json_str = _extract_tag(response, "plan_json")
    if not plan_json_str:
        logger.warning("build_meal_plan: no <plan_json> tag found in planning agent response")
        return {
            "error": "Planning agent did not return a structured plan.",
            "planning_response": response,
        }

    plan_data = json.loads(plan_json_str)

    logger.info(
        "build_meal_plan user=%s type=%s include_snack=%s overrides=%s",
        user_id, plan_type, include_snack, override_filters,
    )
    return {
        "plan": plan_data,
        "plan_type": plan_type,
        "n_days": n_days,
        "targets": {
            "calories": calorie_target,
            "protein": protein_target,
            "daily_budget": daily_budget,
            "weekly_budget": daily_budget * n_days if plan_type == "week" else None,
        },
        "planning_response": response,
    }


@tool
def audit_meal_plan(user_id: str, plan_result: dict) -> dict:
    """
    Delegate plan validation to the audit agent.
    Pass the full dict returned by build_meal_plan directly.

    Args:
        user_id: The user's unique identifier.
        plan_result: The dict returned by build_meal_plan.
    """
    if "error" in plan_result:
        return {"passed": False, "audit_response": plan_result["error"]}

    plan = plan_result["plan"]
    targets = plan_result["targets"]
    plan_type = plan_result["plan_type"]

    # Build audit request message
    plan_label = f"{plan_result.get('n_days', 1)}-day plan" if plan_type == "week" else "day plan"
    message = (
        f"Audit this {plan_label}. "
        f"Calorie target: {targets['calories']:.0f} kcal. "
        f"Protein target: {targets['protein']:.0f}g. "
        f"Daily budget: ${targets['daily_budget']:.2f}.\n\n"
        f"{json.dumps(plan, indent=2)}"
    )

    audit_agent = create_audit_agent(user_id=user_id)
    response = str(audit_agent(message))

    # Extract pass/fail from <audit_passed> tag
    passed_str = _extract_tag(response, "audit_passed")
    passed = passed_str.lower() == "true" if passed_str else False

    logger.info("audit_meal_plan user=%s passed=%s", user_id, passed)
    return {
        "passed": passed,
        "audit_response": response,
    }
