import ast
from pathlib import Path
from typing import List

import pandas as pd

from .schemas import DayPlan, MealSlot, Recipe, RecipeSearchFilters


# Budget Bytes category → meal slots
_BB_CATEGORY_SLOTS: dict[str, list[MealSlot]] = {
    "main_dish": ["lunch", "dinner"],
    "side_dish": ["side"],
    "breakfast":  ["breakfast"],
    "snack":      ["snack"],
    "dessert":    ["snack"],
    "drink":      ["breakfast", "snack"],
}

# Legacy heuristic fallback thresholds (used when bb_category is not a known label)
_LEGACY_SNACK_CAL   = 300
_LEGACY_SNACK_ING   = 6
_LEGACY_BREAKFAST_CAL = 400


def assign_meal_slots(row: pd.Series) -> list[MealSlot]:
    """
    Assign meal slots from the scraped Budget Bytes category label.
    When the category is not a recognized BB label (e.g. legacy cluster labels),
    falls back to calorie/ingredient-count heuristics.
    """
    bb_cat = str(row.get("bb_category", "")).strip().lower()

    if bb_cat in _BB_CATEGORY_SLOTS:
        return list(_BB_CATEGORY_SLOTS[bb_cat])

    # Legacy fallback: derive from calories and ingredient count
    calories = row.get("llm_calories_per_serving", None)
    n_ing    = row.get("llm_ingredient_count", None)
    cal_ok   = calories is not None and not pd.isna(calories)
    ing_ok   = n_ing is not None and not pd.isna(n_ing)

    is_snack = (
        "snack" in bb_cat
        or (cal_ok and calories <= _LEGACY_SNACK_CAL and ing_ok and n_ing <= _LEGACY_SNACK_ING)
    )
    is_breakfast = cal_ok and calories <= _LEGACY_BREAKFAST_CAL and not is_snack

    slots: list[MealSlot] = []
    if is_snack:
        slots.append("snack")
    if is_breakfast:
        slots.append("breakfast")
    if not is_snack:
        slots.extend(["lunch", "dinner"])
    return slots if slots else ["lunch", "dinner"]


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
    "bb_category": "category",
    "ingredients": "ingredients",
    "steps": "steps",
}


def load_recipes(csv_path: str | Path) -> pd.DataFrame:
    """
    Load the raw recipe CSV and rename columns to match the Recipe schema.
    Accepts both the post-scrape recipes_with_steps.csv (has bb_category, steps)
    and the legacy recipes_enriched.csv (has recipe_category, no steps).
    """
    path = Path(csv_path)
    df = pd.read_csv(path)

    # Backfill legacy column names so old CSVs still load
    if "bb_category" not in df.columns and "recipe_category" in df.columns:
        df["bb_category"] = df["recipe_category"]
    if "steps" not in df.columns:
        df["steps"] = None

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
    def _parse_list(val) -> list:
        if isinstance(val, list):
            return val
        try:
            parsed = ast.literal_eval(val)
            return parsed if isinstance(parsed, list) else []
        except Exception:
            return []

    df["ingredients"] = df["ingredients"].apply(_parse_list)

    if "steps" in df.columns:
        df["steps"] = df["steps"].apply(lambda v: _parse_list(v) if pd.notna(v) else [])
    else:
        df["steps"] = [[] for _ in range(len(df))]

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


# Fraction of daily calories each slot should contribute
_SLOT_CAL_FRACTIONS: dict[str, float] = {
    "breakfast":   0.25,
    "lunch":       0.28,
    "lunch_side":  0.07,
    "dinner":      0.28,
    "dinner_side": 0.07,
    # snack gets whatever the day is short by
}

# Goal-based scoring weights: (calorie_closeness, protein, rating)
_GOAL_WEIGHTS: dict[str, tuple[float, float, float]] = {
    "fat_loss":    (0.35, 0.45, 0.20),
    "muscle_gain": (0.20, 0.55, 0.25),
    "maintenance": (0.35, 0.25, 0.40),
}

# Soft variety penalties per slot pick
_CATEGORY_REPEAT_PENALTY = 0.15
_CLUSTER_REPEAT_PENALTY  = 0.10


def _score_recipe(
    recipe: Recipe,
    slot_calorie_target: float | None,
    daily_protein_target: float | None,
    used_categories: set[str],
    used_clusters: set[int],
    goal: str = "maintenance",
) -> float:
    w_cal, w_protein, w_rating = _GOAL_WEIGHTS.get(goal, _GOAL_WEIGHTS["maintenance"])

    # Calorie closeness: 1.0 when exact, falls off linearly
    if slot_calorie_target and slot_calorie_target > 0:
        deviation = abs(recipe.calories - slot_calorie_target) / slot_calorie_target
        cal_score = max(0.0, 1.0 - deviation)
    else:
        cal_score = 0.5

    # Protein contribution relative to a per-slot share of the daily target
    if daily_protein_target and daily_protein_target > 0:
        protein_score = min(1.0, recipe.protein / (daily_protein_target * 0.35))
    else:
        protein_score = min(1.0, recipe.protein / 40.0)

    rating_score = (recipe.rating / 5.0) if recipe.rating > 0 else 0.5

    score = w_cal * cal_score + w_protein * protein_score + w_rating * rating_score

    # Soft variety penalties — lower score for categories/clusters already seen
    if recipe.category in used_categories:
        score -= _CATEGORY_REPEAT_PENALTY
    if recipe.cluster in used_clusters:
        score -= _CLUSTER_REPEAT_PENALTY

    return score


_WEEK_REPEAT_PENALTY = 0.35


def _best_candidate(
    candidates: List[Recipe],
    used_titles: set[str],
    slot_calorie_target: float | None,
    daily_protein_target: float | None,
    used_categories: set[str],
    used_clusters: set[int],
    goal: str,
    week_titles: set[str] | None = None,
) -> Recipe | None:
    eligible = [r for r in candidates if r.title not in used_titles]
    if not eligible:
        return None

    def _adjusted_score(r: Recipe) -> float:
        score = _score_recipe(
            r, slot_calorie_target, daily_protein_target,
            used_categories, used_clusters, goal,
        )
        # Strong penalty for titles already used earlier in the week
        if week_titles and r.title in week_titles:
            score -= _WEEK_REPEAT_PENALTY
        return score

    return max(eligible, key=_adjusted_score)


def build_day_plan(
    df: pd.DataFrame,
    filters: RecipeSearchFilters,
    include_snack: bool = False,
    include_side: bool = False,
    exclude_titles: set[str] | None = None,
    calorie_target: float | None = None,
    protein_target: float | None = None,
    goal: str = "maintenance",
    used_categories: set[str] | None = None,
    used_clusters: set[int] | None = None,
    week_titles: set[str] | None = None,
) -> DayPlan:
    """
    Build a day plan using scored selection.

    Hard constraints (filters) narrow the candidate pool first.
    Soft preferences (calorie closeness, protein, rating, variety) are handled
    by scoring — the highest-scoring eligible recipe wins each slot.

    Fallback: if a slot has no candidates, relax max_total_time first, then
    max_ingredient_count. Raises ValueError with the reason if still empty.

    Sides are only picked when include_side=True and the dataset has side-dish
    recipes. Snack is only added when include_snack=True AND the main meals fall
    short of 85% of the calorie or protein target (always added when no target).
    """
    used_titles: set[str] = set(exclude_titles or [])
    day_categories: set[str] = set(used_categories or [])
    day_clusters: set[int] = set(used_clusters or [])

    slot_cal_targets: dict[str, float] = {}
    if calorie_target:
        slot_cal_targets = {
            slot: calorie_target * frac
            for slot, frac in _SLOT_CAL_FRACTIONS.items()
        }

    def _pick(slot: MealSlot, slot_cal_target: float | None) -> Recipe:
        base = filters.model_copy(update={"limit": 50})
        candidates = search_meals(df, slot, base)
        wt = week_titles or set()

        recipe = _best_candidate(
            candidates, used_titles, slot_cal_target,
            protein_target, day_categories, day_clusters, goal, wt,
        )

        if recipe is None:
            relaxed = base.model_copy(update={"max_total_time": None})
            recipe = _best_candidate(
                search_meals(df, slot, relaxed), used_titles, slot_cal_target,
                protein_target, day_categories, day_clusters, goal, wt,
            )

        if recipe is None:
            relaxed = base.model_copy(update={"max_total_time": None, "max_ingredient_count": None})
            recipe = _best_candidate(
                search_meals(df, slot, relaxed), used_titles, slot_cal_target,
                protein_target, day_categories, day_clusters, goal, wt,
            )

        if recipe is None:
            raise ValueError(
                f"No recipe found for slot '{slot}' — try relaxing your cost or "
                "ingredient filters, or add more recipes to the dataset."
            )

        used_titles.add(recipe.title)
        day_categories.add(recipe.category)
        day_clusters.add(recipe.cluster)
        return recipe

    def _pick_optional(slot: MealSlot, slot_cal_target: float | None) -> Recipe | None:
        """Like _pick but returns None instead of raising when no candidates exist."""
        try:
            return _pick(slot, slot_cal_target)
        except ValueError:
            return None

    breakfast = _pick("breakfast", slot_cal_targets.get("breakfast"))
    lunch     = _pick("lunch",     slot_cal_targets.get("lunch"))
    dinner    = _pick("dinner",    slot_cal_targets.get("dinner"))

    lunch_side  = _pick_optional("side", slot_cal_targets.get("lunch_side"))  if include_side else None
    dinner_side = _pick_optional("side", slot_cal_targets.get("dinner_side")) if include_side else None

    snack = None
    if include_snack:
        if calorie_target and protein_target:
            current_cal = (
                breakfast.calories + lunch.calories + dinner.calories
                + (lunch_side.calories if lunch_side else 0.0)
                + (dinner_side.calories if dinner_side else 0.0)
            )
            current_protein = (
                breakfast.protein + lunch.protein + dinner.protein
                + (lunch_side.protein if lunch_side else 0.0)
                + (dinner_side.protein if dinner_side else 0.0)
            )
            needs_snack = (
                current_cal     < calorie_target * 0.85 or
                current_protein < protein_target * 0.85
            )
            if needs_snack:
                cal_gap = max(0.0, calorie_target - current_cal)
                snack = _pick("snack", cal_gap if cal_gap > 50 else None)
        else:
            snack = _pick("snack", None)

    return DayPlan(
        breakfast=breakfast,
        lunch=lunch,
        lunch_side=lunch_side,
        dinner=dinner,
        dinner_side=dinner_side,
        snack=snack,
    )


def build_week_plan(
    df: pd.DataFrame,
    filters: RecipeSearchFilters,
    n_days: int = 7,
    include_snack: bool = False,
    include_side: bool = False,
    calorie_target: float | None = None,
    protein_target: float | None = None,
    goal: str = "maintenance",
) -> List[DayPlan]:
    """
    Build a multi-day plan.

    Titles from the previous day are hard-excluded to prevent consecutive
    repeats. Categories and clusters used across the whole week are tracked
    and fed into scoring as soft variety penalties so the planner naturally
    diversifies without being blocked entirely.
    """
    plans: List[DayPlan] = []
    week_categories: set[str] = set()
    week_clusters: set[int]   = set()
    week_titles: set[str]     = set()

    for _ in range(n_days):
        # Hard-exclude only the previous day to avoid consecutive repeats
        prev_titles: set[str] = set()
        if plans:
            prev = plans[-1]
            prev_titles = {prev.breakfast.title, prev.lunch.title, prev.dinner.title}
            for opt in (prev.lunch_side, prev.dinner_side, prev.snack):
                if opt:
                    prev_titles.add(opt.title)

        plan = build_day_plan(
            df, filters,
            include_snack=include_snack,
            include_side=include_side,
            exclude_titles=prev_titles,
            calorie_target=calorie_target,
            protein_target=protein_target,
            goal=goal,
            used_categories=week_categories,
            used_clusters=week_clusters,
            week_titles=week_titles,
        )
        plans.append(plan)

        day_titles = {plan.breakfast.title, plan.lunch.title, plan.dinner.title}
        for opt in (plan.lunch_side, plan.dinner_side, plan.snack):
            if opt:
                day_titles.add(opt.title)
        week_titles     |= day_titles
        week_categories |= {plan.breakfast.category, plan.lunch.category, plan.dinner.category}
        week_clusters   |= {plan.breakfast.cluster, plan.lunch.cluster, plan.dinner.cluster}
        for opt in (plan.lunch_side, plan.dinner_side, plan.snack):
            if opt:
                week_categories.add(opt.category)
                week_clusters.add(opt.cluster)

    return plans