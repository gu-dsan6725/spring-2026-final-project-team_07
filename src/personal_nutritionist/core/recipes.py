import ast
from pathlib import Path
from typing import List

import pandas as pd

from .schemas import DayPlan, MealSlot, Recipe, RecipeSearchFilters


# Heuristic thresholds for meal-slot assignment
_BREAKFAST_CATEGORIES = {"low budget, simple"}
_SNACK_CATEGORIES = {"snacks"}
_BREAKFAST_MAX_CALORIES = 400
_SNACK_MAX_CALORIES = 300
_SNACK_MAX_INGREDIENTS = 6


def assign_meal_slots(row: pd.Series) -> list[MealSlot]:
    """
    Derive plausible meal slots from category, calories, and ingredient count.
    A recipe can belong to multiple slots (e.g. a light simple dish fits both
    breakfast and lunch).
    """
    slots: list[MealSlot] = []
    category = str(row.get("recipe_category", "")).lower()
    calories = row.get("llm_calories_per_serving", None)
    n_ingredients = row.get("llm_ingredient_count", None)

    is_snack_cat = any(s in category for s in _SNACK_CATEGORIES)
    is_breakfast_cat = any(s in category for s in _BREAKFAST_CATEGORIES)

    cal_ok = calories is not None and not pd.isna(calories)
    ing_ok = n_ingredients is not None and not pd.isna(n_ingredients)

    if is_snack_cat or (cal_ok and calories <= _SNACK_MAX_CALORIES and ing_ok and n_ingredients <= _SNACK_MAX_INGREDIENTS):
        slots.append("snack")

    if is_breakfast_cat or (cal_ok and calories <= _BREAKFAST_MAX_CALORIES and not is_snack_cat):
        slots.append("breakfast")

    # Everything that isn't snack-only fits lunch
    if not (is_snack_cat and not is_breakfast_cat):
        slots.append("lunch")

    # Dinner: anything that isn't a snack and isn't a tiny breakfast item
    if not is_snack_cat and not (is_breakfast_cat and cal_ok and calories <= 250):
        slots.append("dinner")

    # Deduplicate while preserving order
    seen: set[str] = set()
    result: list[MealSlot] = []
    for s in slots:
        if s not in seen:
            seen.add(s)
            result.append(s)  # type: ignore[arg-type]
    return result


RECIPE_COLUMN_MAP = {
    "title": "title",
    "total_cost_usd": "total_cost",
    "cost_per_serving_usd": "cost_per_serving",
    "rating_avg": "rating",
    "rating_vote": "rating_count",
    "servings": "servings",
    "prep_time_min": "prep_time",
    "cook_time_min": "cook_time",
    "total_time_min": "total_time",
    "num_steps": "num_steps",
    "step_len_char": "step_length",
    "llm_ingredient_count": "ingredient_count",
    "llm_calories_per_serving": "calories",
    "llm_protein_per_serving": "protein",
    "llm_fat_per_serving": "fat",
    "llm_carbs_per_serving": "carbs",
    "cluster_label": "cluster",
    "recipe_category": "category",
    "ingredients": "ingredients",
}


def load_recipes(csv_path: str | Path) -> pd.DataFrame:
    """
    Load the raw recipe CSV and rename columns to match the Recipe schema.
    """
    path = Path(csv_path)
    df = pd.read_csv(path)

    missing = [col for col in RECIPE_COLUMN_MAP if col not in df.columns]
    if missing:
        raise ValueError(f"Missing expected recipe columns: {missing}")

    # Derive meal slots before dropping extra columns
    df["meal_slots"] = df.apply(assign_meal_slots, axis=1)

    df = df[list(RECIPE_COLUMN_MAP.keys()) + ["meal_slots"]].rename(columns=RECIPE_COLUMN_MAP)

    # Drop rows missing critical fields
    critical_fields = ["title", "cost_per_serving", "total_time", "calories", "protein"]
    df = df.dropna(subset=critical_fields)

    # Parse ingredients from stored list representation back to list[str]
    def _parse_ingredients(val) -> list:
        if isinstance(val, list):
            return val
        try:
            parsed = ast.literal_eval(val)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    df["ingredients"] = df["ingredients"].apply(_parse_ingredients)

    return df


def recipe_from_row(row: pd.Series) -> Recipe:
    """
    Convert a dataframe row into a validated Recipe object.
    """
    return Recipe(**row.to_dict())


def search_recipes(
    df: pd.DataFrame,
    filters: RecipeSearchFilters,
) -> List[Recipe]:
    """
    Filter recipes deterministically and return validated Recipe objects.
    """
    results = df.copy()

    if filters.max_cost_per_serving is not None:
        results = results[results["cost_per_serving"] <= filters.max_cost_per_serving]

    if filters.max_total_time is not None:
        results = results[results["total_time"] <= filters.max_total_time]

    if filters.min_protein is not None:
        results = results[results["protein"] >= filters.min_protein]

    if filters.max_calories is not None:
        results = results[results["calories"] <= filters.max_calories]

    if filters.min_rating is not None:
        results = results[results["rating"] >= filters.min_rating]

    if filters.min_rating_count is not None:
        results = results[results["rating_count"] >= filters.min_rating_count]

    if filters.max_ingredient_count is not None:
        results = results[results["ingredient_count"] <= filters.max_ingredient_count]

    if filters.category:
        results = results[
            results["category"].str.contains(filters.category, case=False, na=False)
        ]

    if filters.title_contains:
        results = results[
            results["title"].str.contains(filters.title_contains, case=False, na=False)
        ]

    # Sort by a simple practical heuristic:
    # high protein, good ratings, cheaper cost
    results = results.sort_values(
        by=["protein", "rating", "rating_count", "cost_per_serving"],
        ascending=[False, False, False, True],
    )

    results = results.head(filters.limit)

    return [recipe_from_row(row) for _, row in results.iterrows()]


def search_meals(
    df: pd.DataFrame,
    slot: MealSlot,
    filters: RecipeSearchFilters,
) -> List[Recipe]:
    """
    Like search_recipes() but restricts results to recipes assigned to `slot`.
    """
    slot_df = df[df["meal_slots"].apply(lambda slots: slot in slots)]
    return search_recipes(slot_df, filters)


def build_day_plan(
    df: pd.DataFrame,
    filters: RecipeSearchFilters,
    include_snack: bool = False,
    exclude_titles: set[str] | None = None,
) -> DayPlan:
    """
    Assemble one breakfast, lunch, dinner (and optionally a snack), with no
    duplicate meals within the day. Pass exclude_titles to also block meals
    used on the previous day (for weekly planning).
    Raises ValueError if any required slot has no candidates.
    """
    used: set[str] = set(exclude_titles or [])

    def _pick(slot: MealSlot) -> Recipe:
        candidates = search_meals(df, slot, filters.model_copy(update={"limit": 50}))
        for recipe in candidates:
            if recipe.title not in used:
                used.add(recipe.title)
                return recipe
        raise ValueError(f"No unique recipe found for slot '{slot}' with the given filters.")

    return DayPlan(
        breakfast=_pick("breakfast"),
        lunch=_pick("lunch"),
        dinner=_pick("dinner"),
        snack=_pick("snack") if include_snack else None,
    )


def build_week_plan(
    df: pd.DataFrame,
    filters: RecipeSearchFilters,
    n_days: int = 7,
    include_snack: bool = False,
) -> List[DayPlan]:
    """
    Build a multi-day plan with no duplicate meals within a day and no meal
    repeated on consecutive days.
    """
    plans: List[DayPlan] = []
    prev_titles: set[str] = set()

    for _ in range(n_days):
        plan = build_day_plan(df, filters, include_snack=include_snack, exclude_titles=prev_titles)
        plans.append(plan)
        prev_titles = {plan.breakfast.title, plan.lunch.title, plan.dinner.title}
        if plan.snack:
            prev_titles.add(plan.snack.title)

    return plans