from pathlib import Path
from typing import List

import pandas as pd

from .schemas import Recipe, RecipeSearchFilters


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

    df = df[list(RECIPE_COLUMN_MAP.keys())].rename(columns=RECIPE_COLUMN_MAP)

    # Drop rows missing critical fields
    critical_fields = ["title", "cost_per_serving", "total_time", "calories", "protein"]
    df = df.dropna(subset=critical_fields)

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