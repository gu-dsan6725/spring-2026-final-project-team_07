import json
import logging

from strands import tool

from personal_nutritionist.core.schemas import UserProfile

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# get_user_profile()
@tool
def get_user_profile(user_id: str) -> dict:
    profile = UserProfile(
        user_id=user_id,
        goal="fat_loss",
        weight_lbs=190,
        height_in=70,
        age=30,
        sex="male",
        activity_level="moderate",
        max_cost_per_serving=2.50,
        max_total_time=30,
        max_ingredient_count=10,
        preferred_categories=["Comfort Meals", "Low budget, Simple"],
        disliked_ingredients=["tuna"],
        allergies=[],
        meals_per_day=3,
    )
    return profile.model_dump()

# estimate_calorie_target(...)
# estimate_protein_target(...)
# search_meals(...)
# build_day_plan(...) or build_week_plan(...)
# generate_grocery_list(...)