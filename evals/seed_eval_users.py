"""
Seed eval user profiles in Mem0 for multi-user evaluation scenarios.

Run once before executing the eval suite (safe to re-run — resets each user):
    PYTHONPATH=src uv run python evals/seed_eval_users.py

Calorie targets (Mifflin-St Jeor) are documented inline so eval scorers
can reference them without re-computing.
"""

import logging
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from dotenv import load_dotenv
load_dotenv()

from personal_nutritionist.core.memory import add_memory, delete_all_memories

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# User definitions
# Each entry maps field name → (value, human_text) matching intake tool format.
# List fields (allergies, disliked_ingredients) use comma-separated strings.
# ---------------------------------------------------------------------------

EVAL_USERS = [
    # eval_muscle_f — 24F, 130 lbs, 65 in, light, muscle_gain  → ~2,093 kcal target
    {
        "user_id": "eval_muscle_f",
        "fields": [
            ("goal",                "muscle_gain",  "User's nutrition goal is muscle_gain."),
            ("weight_lbs",          130.0,           "User weighs 130 lbs."),
            ("height_in",           65.0,            "User's height is 65 inches."),
            ("age",                 24,              "User is 24 years old."),
            ("sex",                 "female",        "User's sex is female."),
            ("activity_level",      "light",         "User's activity level is light."),
            ("disliked_ingredients","mushrooms",     "User dislikes these ingredients: mushrooms."),
            ("max_cost_per_serving",5.0,             "User's maximum cost per serving is $5.00."),
            ("max_total_time",      45,              "User wants meals that take no more than 45 minutes."),
            ("meals_per_day",       3,               "User eats 3 meals per day."),
        ],
    },
    # eval_budget_m — 35M, 185 lbs, 72 in, moderate, fat_loss, $1.50 cap → ~2,309 kcal target
    {
        "user_id": "eval_budget_m",
        "fields": [
            ("goal",                "fat_loss",  "User's nutrition goal is fat_loss."),
            ("weight_lbs",          185.0,        "User weighs 185 lbs."),
            ("height_in",           72.0,         "User's height is 72 inches."),
            ("age",                 35,           "User is 35 years old."),
            ("sex",                 "male",       "User's sex is male."),
            ("activity_level",      "moderate",   "User's activity level is moderate."),
            ("max_cost_per_serving",1.50,         "User's maximum cost per serving is $1.50."),
            ("max_total_time",      30,           "User wants meals that take no more than 30 minutes."),
            ("meals_per_day",       3,            "User eats 3 meals per day."),
        ],
    },
    # eval_quick_f — 30F, 145 lbs, 64 in, moderate, fat_loss, 15 min max → ~1,612 kcal target
    {
        "user_id": "eval_quick_f",
        "fields": [
            ("goal",                "fat_loss",  "User's nutrition goal is fat_loss."),
            ("weight_lbs",          145.0,        "User weighs 145 lbs."),
            ("height_in",           64.0,         "User's height is 64 inches."),
            ("age",                 30,           "User is 30 years old."),
            ("sex",                 "female",     "User's sex is female."),
            ("activity_level",      "moderate",   "User's activity level is moderate."),
            ("max_cost_per_serving",3.0,          "User's maximum cost per serving is $3.00."),
            ("max_total_time",      15,           "User wants meals that take no more than 15 minutes."),
            ("meals_per_day",       3,            "User eats 3 meals per day."),
        ],
    },
    # eval_athlete_m — 22M, 190 lbs, 75 in, very_active, muscle_gain → ~3,950 kcal target
    {
        "user_id": "eval_athlete_m",
        "fields": [
            ("goal",                "muscle_gain", "User's nutrition goal is muscle_gain."),
            ("weight_lbs",          190.0,          "User weighs 190 lbs."),
            ("height_in",           75.0,           "User's height is 75 inches."),
            ("age",                 22,             "User is 22 years old."),
            ("sex",                 "male",         "User's sex is male."),
            ("activity_level",      "very_active",  "User's activity level is very_active."),
            ("max_cost_per_serving",4.0,            "User's maximum cost per serving is $4.00."),
            ("max_total_time",      60,             "User wants meals that take no more than 60 minutes."),
            ("meals_per_day",       3,              "User eats 3 meals per day."),
        ],
    },
    # eval_senior_m — 65M, 165 lbs, 69 in, sedentary, maintenance → ~1,829 kcal target
    {
        "user_id": "eval_senior_m",
        "fields": [
            ("goal",                "maintenance", "User's nutrition goal is maintenance."),
            ("weight_lbs",          165.0,          "User weighs 165 lbs."),
            ("height_in",           69.0,           "User's height is 69 inches."),
            ("age",                 65,             "User is 65 years old."),
            ("sex",                 "male",         "User's sex is male."),
            ("activity_level",      "sedentary",    "User's activity level is sedentary."),
            ("max_cost_per_serving",3.0,            "User's maximum cost per serving is $3.00."),
            ("max_total_time",      30,             "User wants meals that take no more than 30 minutes."),
            ("meals_per_day",       3,              "User eats 3 meals per day."),
        ],
    },
    # eval_peanut_f — 28F, 150 lbs, 66 in, moderate, fat_loss, peanut allergy → ~1,712 kcal target
    {
        "user_id": "eval_peanut_f",
        "fields": [
            ("goal",                "fat_loss",   "User's nutrition goal is fat_loss."),
            ("weight_lbs",          150.0,         "User weighs 150 lbs."),
            ("height_in",           66.0,          "User's height is 66 inches."),
            ("age",                 28,            "User is 28 years old."),
            ("sex",                 "female",      "User's sex is female."),
            ("activity_level",      "moderate",    "User's activity level is moderate."),
            ("allergies",           "peanuts",     "User is allergic to: peanuts."),
            ("max_cost_per_serving",3.0,           "User's maximum cost per serving is $3.00."),
            ("max_total_time",      30,            "User wants meals that take no more than 30 minutes."),
            ("meals_per_day",       3,             "User eats 3 meals per day."),
        ],
    },
    # eval_3day_m — 25M, 170 lbs, 70 in, active, muscle_gain → ~3,290 kcal target
    {
        "user_id": "eval_3day_m",
        "fields": [
            ("goal",                "muscle_gain", "User's nutrition goal is muscle_gain."),
            ("weight_lbs",          170.0,          "User weighs 170 lbs."),
            ("height_in",           70.0,           "User's height is 70 inches."),
            ("age",                 25,             "User is 25 years old."),
            ("sex",                 "male",         "User's sex is male."),
            ("activity_level",      "active",       "User's activity level is active."),
            ("max_cost_per_serving",4.0,            "User's maximum cost per serving is $4.00."),
            ("max_total_time",      45,             "User wants meals that take no more than 45 minutes."),
            ("meals_per_day",       3,              "User eats 3 meals per day."),
        ],
    },
    # eval_budget_3day_f — 40F, 160 lbs, 67 in, light, fat_loss, $1.75 cap → ~1,464 kcal target
    {
        "user_id": "eval_budget_3day_f",
        "fields": [
            ("goal",                "fat_loss",  "User's nutrition goal is fat_loss."),
            ("weight_lbs",          160.0,        "User weighs 160 lbs."),
            ("height_in",           67.0,         "User's height is 67 inches."),
            ("age",                 40,           "User is 40 years old."),
            ("sex",                 "female",     "User's sex is female."),
            ("activity_level",      "light",      "User's activity level is light."),
            ("max_cost_per_serving",1.75,         "User's maximum cost per serving is $1.75."),
            ("max_total_time",      30,           "User wants meals that take no more than 30 minutes."),
            ("meals_per_day",       3,            "User eats 3 meals per day."),
        ],
    },
    # eval_multi_m — 26M, 170 lbs, 69 in, moderate, fat_loss, peanut allergy + broccoli dislike → ~2,199 kcal
    {
        "user_id": "eval_multi_m",
        "fields": [
            ("goal",                 "fat_loss",   "User's nutrition goal is fat_loss."),
            ("weight_lbs",           170.0,         "User weighs 170 lbs."),
            ("height_in",            69.0,          "User's height is 69 inches."),
            ("age",                  26,            "User is 26 years old."),
            ("sex",                  "male",        "User's sex is male."),
            ("activity_level",       "moderate",    "User's activity level is moderate."),
            ("allergies",            "peanuts",     "User is allergic to: peanuts."),
            ("disliked_ingredients", "broccoli",    "User dislikes these ingredients: broccoli."),
            ("max_cost_per_serving", 2.50,          "User's maximum cost per serving is $2.50."),
            ("max_total_time",       25,            "User wants meals that take no more than 25 minutes."),
            ("meals_per_day",        3,             "User eats 3 meals per day."),
        ],
    },
    # eval_shopping_m — 33M, 180 lbs, 71 in, moderate, fat_loss → ~2,265 kcal target
    {
        "user_id": "eval_shopping_m",
        "fields": [
            ("goal",                "fat_loss",  "User's nutrition goal is fat_loss."),
            ("weight_lbs",          180.0,        "User weighs 180 lbs."),
            ("height_in",           71.0,         "User's height is 71 inches."),
            ("age",                 33,           "User is 33 years old."),
            ("sex",                 "male",       "User's sex is male."),
            ("activity_level",      "moderate",   "User's activity level is moderate."),
            ("max_cost_per_serving",2.50,         "User's maximum cost per serving is $2.50."),
            ("max_total_time",      30,           "User wants meals that take no more than 30 minutes."),
            ("meals_per_day",       3,            "User eats 3 meals per day."),
        ],
    },
]


def seed_user(user_id: str, fields: list[tuple]) -> None:
    logger.info("Seeding %s — resetting existing memories...", user_id)
    delete_all_memories(user_id)
    time.sleep(1)  # brief pause after delete

    for field, value, text in fields:
        add_memory(user_id, text, metadata={"field": field, "value": value})
        time.sleep(0.3)  # avoid Mem0 rate limits

    logger.info("Seeded %s with %d fields", user_id, len(fields))


def main() -> None:
    logger.info("Seeding %d eval users...", len(EVAL_USERS))
    for user in EVAL_USERS:
        seed_user(user["user_id"], user["fields"])
        time.sleep(1)
    logger.info("Done. All eval users seeded.")


if __name__ == "__main__":
    main()
