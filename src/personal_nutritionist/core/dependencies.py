import os
from pathlib import Path

import pandas as pd

from personal_nutritionist.core.recipes import load_recipes

_RECIPES_CSV = Path(os.getenv("RECIPES_CSV", "data/recipes_with_steps.csv"))

_recipe_df: pd.DataFrame | None = None


def get_recipe_df() -> pd.DataFrame:
    """
    Return the recipe DataFrame, loading and caching it on first access.
    Set the RECIPES_CSV environment variable to override the default path.
    """
    global _recipe_df
    if _recipe_df is None:
        _recipe_df = load_recipes(_RECIPES_CSV)
    return _recipe_df
