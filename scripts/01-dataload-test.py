from pathlib import Path

from personal_nutritionist.core.recipes import load_recipes, search_recipes
from personal_nutritionist.core.schemas import RecipeSearchFilters

df = load_recipes(Path("data/recipes_final.csv"))

filters = RecipeSearchFilters(
    max_cost_per_serving=2.5,
    max_total_time=30,
    min_protein=20,
)

recipes = search_recipes(df, filters)

for r in recipes:
    print(r.title, r.protein, r.cost_per_serving)