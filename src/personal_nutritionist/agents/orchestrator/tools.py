import json
import logging
import re
from collections import defaultdict

from strands import tool

from personal_nutritionist.agents.intake.agent import create_intake_agent
from personal_nutritionist.agents.planning.agent import create_planning_agent
from personal_nutritionist.core.dependencies import get_recipe_df
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


_PLAN_SLOTS = ("breakfast", "lunch", "lunch_side", "dinner", "dinner_side", "snack")


def _enrich_plan(plan_data: dict | list) -> dict | list:
    """
    Re-attach steps and ingredient_details to each recipe in a plan.
    The planning agent strips these to save tokens; we restore them here
    using a title lookup against the recipe dataframe.
    """
    df = get_recipe_df()
    title_index = df.set_index("title")

    def _enrich_recipe(recipe: dict) -> dict:
        title = recipe.get("title")
        if not title or title not in title_index.index:
            return recipe
        row = title_index.loc[title]
        recipe["steps"] = row.get("steps") or []
        recipe["ingredient_details"] = row.get("ingredient_details") or []
        return recipe

    def _enrich_day(day: dict) -> dict:
        for slot in _PLAN_SLOTS:
            if day.get(slot) and isinstance(day[slot], dict):
                day[slot] = _enrich_recipe(day[slot])
        return day

    if isinstance(plan_data, list):
        return [_enrich_day(day) for day in plan_data]
    return _enrich_day(plan_data)


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

    plan_data = _enrich_plan(json.loads(plan_json_str))

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
            "max_cost_per_serving": profile.max_cost_per_serving,
        },
        "planning_response": response,
    }


_PREP_WORDS = {
    "chopped", "diced", "pressed", "minced", "sliced", "shredded", "peeled",
    "trimmed", "seeded", "softened", "melted", "divided", "uncooked", "cooked",
    "grated", "torn", "crumbled", "halved", "quartered", "julienned", "thinly",
    "roughly", "finely", "lightly", "beaten", "sifted", "rinsed", "drained",
    "freshly", "cracked", "ground", "packed",
}
_SIZE_WORDS = {"small", "medium", "large", "baby", "jumbo", "mini"}
_QUALITY_WORDS = {
    "fresh", "frozen", "canned", "dried", "unsalted", "salted", "low-sodium",
    "reduced-sodium", "whole", "lean", "boneless", "skinless", "raw",
}
_TRAILING_PHRASES = [
    "for garnish", "for serving", "to taste", "or to taste",
    "room temperature", "divided", "optional", "as needed",
]


def _clean_name(name: str) -> str:
    """Normalise an ingredient name for deduplication."""
    name = name.lower().strip()
    name = re.sub(r"\(.*?\)", "", name)
    name = re.sub(r"\*+", "", name)
    name = name.replace(",", " ")
    for phrase in _TRAILING_PHRASES:
        name = name.replace(phrase, "")
    words = [
        w for w in name.split()
        if w not in _PREP_WORDS and w not in _SIZE_WORDS and w not in _QUALITY_WORDS
    ]
    return re.sub(r"\s+", " ", " ".join(words)).strip()


# ---------------------------------------------------------------------------
# Unit normalisation
# ---------------------------------------------------------------------------

# Aliases → canonical unit name
_UNIT_ALIASES: dict[str, str] = {
    # imperial weight
    "oz": "oz", "ounce": "oz", "ounces": "oz",
    "lb": "lb", "lbs": "lb", "pound": "lb", "pounds": "lb",
    # imperial volume
    "tsp": "tsp", "teaspoon": "tsp", "teaspoons": "tsp", "t.": "tsp",
    "tbsp": "tbsp", "tablespoon": "tbsp", "tablespoons": "tbsp", "tbsps": "tbsp",
    "t": "tbsp",   # capital T is tablespoon in recipes — normalise lowercase
    "fl oz": "fl oz", "fluid oz": "fl oz", "fluid ounce": "fl oz",
    "cup": "cup", "cups": "cup", "c.": "cup", "c": "cup",
    "pint": "pint", "pints": "pint", "pt": "pint", "pt.": "pint",
    "quart": "qt", "quarts": "qt", "qt": "qt", "qt.": "qt",
    # metric weight
    "g": "g", "gram": "g", "grams": "g",
    "kg": "kg", "kilogram": "kg", "kilograms": "kg",
    # metric volume
    "ml": "ml", "milliliter": "ml", "milliliters": "ml", "millilitre": "ml",
    "l": "L", "liter": "L", "liters": "L", "litre": "L", "litres": "L",
    # counts
    "clove": "clove", "cloves": "clove",
    "slice": "slice", "slices": "slice",
    "piece": "piece", "pieces": "piece",
    "can": "can", "cans": "can",
    "package": "package", "packages": "package", "pkg": "package",
    "packet": "packet", "packets": "packet",
    "pinch": "pinch", "pinches": "pinch",
    "dash": "dash", "dashes": "dash",
}

# Family membership: canonical unit → (family, factor_to_base)
# base for imperial weight  = oz
# base for imperial volume  = tsp
# base for metric weight    = g
# base for metric volume    = ml
_UNIT_FAMILIES: dict[str, tuple[str, float]] = {
    "oz":   ("imp_weight", 1.0),
    "lb":   ("imp_weight", 16.0),
    "tsp":  ("imp_vol",    1.0),
    "tbsp": ("imp_vol",    3.0),
    "fl oz":("imp_vol",    6.0),
    "cup":  ("imp_vol",    48.0),
    "pint": ("imp_vol",    96.0),
    "qt":   ("imp_vol",    192.0),
    "g":    ("met_weight", 1.0),
    "kg":   ("met_weight", 1000.0),
    "ml":   ("met_vol",    1.0),
    "L":    ("met_vol",    1000.0),
}

# How to display accumulated base units
# (threshold_in_base_units, display_unit, divisor)
_DISPLAY_THRESHOLDS: dict[str, list[tuple[float, str, float]]] = {
    "imp_weight": [(4.0,   "lb",   16.0),  (0.0,  "oz",   1.0)],
    "imp_vol":    [(192.0, "qt",  192.0),  (12.0, "cup",  48.0),
                   (3.0,   "tbsp", 3.0),   (0.0,  "tsp",  1.0)],
    "met_weight": [(1000.0, "kg", 1000.0), (0.0,  "g",    1.0)],
    "met_vol":    [(1000.0, "L",  1000.0), (0.0,  "ml",   1.0)],
}


def _canonical_unit(raw: str | None) -> str | None:
    if not raw:
        return None
    return _UNIT_ALIASES.get(raw.strip().lower())


def _fmt_number(n: float) -> str:
    if n == int(n):
        return str(int(n))
    # Express as a simple fraction when close to common cooking amounts
    for num, den in [(1, 4), (1, 3), (1, 2), (2, 3), (3, 4)]:
        if abs(n - num / den) < 0.01:
            return f"{num}/{den}"
    return f"{n:.2f}".rstrip("0").rstrip(".")


def _format_amount(amounts: list[tuple[float | None, str | None]]) -> str:
    """
    Aggregate (amount, unit) pairs for one ingredient.
    - Normalises unit aliases (tbsps → tbsp, lbs → lb, etc.)
    - Converts within a unit family to a common base, then picks the best
      display unit (e.g. 48 tsp → 1 cup, 32 oz → 2 lb)
    - Lists amounts from incompatible families separately
    - Amounts with no unit are summed and shown as a bare count
    """
    family_totals: dict[str, float] = defaultdict(float)  # family → base-unit sum
    count_totals: dict[str, float] = defaultdict(float)   # canonical count unit → sum
    truly_unknown: list[str] = []                         # unrecognised units
    no_unit_total: float = 0.0
    has_amounts = False

    for raw_amount, raw_unit in amounts:
        if raw_amount is None:
            continue
        has_amounts = True

        canon = _canonical_unit(raw_unit)

        if canon is None and raw_unit:
            truly_unknown.append(f"{_fmt_number(raw_amount)} {raw_unit.strip()}")
            continue

        if canon is None:
            no_unit_total += raw_amount
            continue

        family_info = _UNIT_FAMILIES.get(canon)
        if family_info is None:
            # Recognised alias with no conversion family (cloves, cans, etc.) — sum by unit
            count_totals[canon] += raw_amount
            continue

        family, factor = family_info
        family_totals[family] += raw_amount * factor

    if not has_amounts:
        return ""

    parts: list[str] = []

    for family, base_total in sorted(family_totals.items()):
        thresholds = _DISPLAY_THRESHOLDS[family]
        for threshold, disp_unit, divisor in thresholds:
            if base_total >= threshold:
                parts.append(f"{_fmt_number(base_total / divisor)} {disp_unit}")
                break

    for unit, total in sorted(count_totals.items()):
        parts.append(f"{_fmt_number(total)} {unit}")

    seen: set[str] = set()
    for p in truly_unknown:
        if p not in seen:
            seen.add(p)
            parts.append(p)

    if no_unit_total:
        parts.append(_fmt_number(no_unit_total))

    return ", ".join(parts)


@tool
def generate_shopping_list(plan_result: dict) -> dict:
    """
    Aggregate and deduplicate all ingredients across every recipe in a plan,
    combining quantities where units match. Works for day and week plans.

    Args:
        plan_result: The dict returned by build_meal_plan.
    """
    if "error" in plan_result:
        return {"error": plan_result["error"]}

    plan = plan_result.get("plan", {})
    days = plan if isinstance(plan, list) else [plan]
    _SLOTS = ("breakfast", "lunch", "lunch_side", "dinner", "dinner_side", "snack")

    # key: cleaned name → {display_name, amounts: [(amount, unit), ...]}
    grouped: dict[str, dict] = {}

    for day in days:
        for slot in _SLOTS:
            recipe = day.get(slot)
            if not recipe or not isinstance(recipe, dict):
                continue

            details = recipe.get("ingredient_details") or []
            if details:
                for d in details:
                    raw_name = d.get("name", "")
                    if not raw_name:
                        continue
                    key = _clean_name(raw_name)
                    if not key:
                        continue
                    if key not in grouped:
                        grouped[key] = {"display_name": key, "amounts": []}
                    grouped[key]["amounts"].append((d.get("amount"), d.get("unit")))
            else:
                # Fallback: name-only strings (legacy or missing ingredient_details)
                for ing in recipe.get("ingredients", []):
                    key = _clean_name(ing)
                    if key and key not in grouped:
                        grouped[key] = {"display_name": key, "amounts": []}

    items = []
    for key in sorted(grouped):
        entry = grouped[key]
        amount_str = _format_amount(entry["amounts"])
        items.append({
            "ingredient": entry["display_name"],
            "quantity": amount_str or None,
            "display": f"{amount_str} {entry['display_name']}".strip() if amount_str else entry["display_name"],
        })

    logger.info(
        "generate_shopping_list: %d unique ingredients across %d day(s)",
        len(items), len(days),
    )
    return {
        "items": items,
        "count": len(items),
        "days": len(days),
    }


_REQUIRED_SLOTS = ("breakfast", "lunch", "dinner")
_ALL_SLOTS = ("breakfast", "lunch", "lunch_side", "dinner", "dinner_side", "snack")


def _deterministic_audit(plan_data: dict | list, exclude: list[str]) -> tuple[bool, list[str]]:
    """
    Fast deterministic checks — no LLM required.
    Checks: required slots present, no duplicate meals, allergen/dislike violations.
    """
    days = plan_data if isinstance(plan_data, list) else [plan_data]
    # Build singular+plural exclusion terms once
    terms: list[str] = []
    for e in exclude:
        t = e.lower().strip()
        terms.append(t)
        if t.endswith("s"):
            terms.append(t[:-1])

    issues: list[str] = []
    for i, day in enumerate(days):
        label = f"Day {i + 1}" if len(days) > 1 else "Plan"

        missing = [s for s in _REQUIRED_SLOTS if not day.get(s)]
        if missing:
            issues.append(f"{label}: missing required slots {missing}")

        titles = [day[s]["title"] for s in _REQUIRED_SLOTS if day.get(s)]
        dupes = [t for t in set(titles) if titles.count(t) > 1]
        if dupes:
            issues.append(f"{label}: duplicate meals {dupes}")

        if terms:
            for slot in _ALL_SLOTS:
                meal = day.get(slot)
                if not meal:
                    continue
                combined = " ".join(meal.get("ingredients", [])).lower()
                hit = [t for t in terms if t in combined]
                if hit:
                    issues.append(
                        f"{label} {slot} '{meal['title']}': "
                        f"contains excluded ingredient(s) {hit}"
                    )

    return len(issues) == 0, issues


@tool
def audit_meal_plan(user_id: str, plan_result: dict) -> dict:
    """
    Validate a meal plan against hard constraints (required slots, no duplicates,
    dietary restrictions). Fast deterministic check — no LLM involved.

    Args:
        user_id: The user's unique identifier.
        plan_result: The dict returned by build_meal_plan.
    """
    if "error" in plan_result:
        return {"passed": False, "issues": [plan_result["error"]]}

    profile = _load_profile(user_id)
    exclude = list({*profile.allergies, *profile.disliked_ingredients})

    passed, issues = _deterministic_audit(plan_result["plan"], exclude)
    logger.info("audit_meal_plan user=%s passed=%s issues=%s", user_id, passed, issues)
    return {"passed": passed, "issues": issues}
