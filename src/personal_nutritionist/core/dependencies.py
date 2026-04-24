import os
from pathlib import Path
from typing import Any

import pandas as pd

from personal_nutritionist.core.recipes import load_recipes

_RECIPES_CSV = Path(os.getenv("RECIPES_CSV", "data/recipes_with_steps.csv"))

_recipe_df: pd.DataFrame | None = None

_CATEGORY_SLOTS: dict[str, list[str]] = {
    "main_dish": ["lunch", "dinner"],
    "side_dish": ["side"],
    "breakfast":  ["breakfast"],
    "snack":      ["snack"],
    "dessert":    ["snack"],
    "drink":      ["breakfast", "snack"],
}


def _infer_meal_slots(category: Any) -> list[str]:
    cat = str(category or "").strip().lower()
    return _CATEGORY_SLOTS.get(cat, ["lunch", "dinner"])


def get_recipe_df(user_id: str | None = None) -> pd.DataFrame:
    """
    Return the recipe DataFrame for a user: base CSV minus their exclusions,
    plus any custom recipes they've added. Pass user_id=None for the raw CSV.
    """
    global _recipe_df
    if _recipe_df is None:
        _recipe_df = load_recipes(_RECIPES_CSV)

    if user_id is None:
        return _recipe_df

    from personal_nutritionist.core.database import get_excluded, get_custom_recipes

    excluded = get_excluded(user_id)
    df = _recipe_df[~_recipe_df["title"].isin(excluded)].copy() if excluded else _recipe_df.copy()

    custom = get_custom_recipes(user_id)
    if custom:
        custom_df = pd.DataFrame(custom).reindex(columns=df.columns)
        # Assign meal_slots from category for any custom recipe that has none
        def _fix_slots(row):
            slots = row.get("meal_slots")
            if not slots or (isinstance(slots, float)):
                return _infer_meal_slots(row.get("category"))
            return slots
        custom_df["meal_slots"] = [
            _fix_slots(r) for r in custom
        ]
        df = pd.concat([df, custom_df], ignore_index=True)

    return df
