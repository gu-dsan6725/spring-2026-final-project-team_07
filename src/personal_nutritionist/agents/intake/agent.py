import os

from dotenv import load_dotenv
from strands import Agent
from strands.models.anthropic import AnthropicModel

from personal_nutritionist.agents.intake.tools import (
    get_user_profile,
    update_goal,
    update_body_stats,
    update_activity_level,
    update_dietary_preferences,
    update_meal_constraints,
    recall_user_info,
    reset_user_profile,
)

load_dotenv()

SYSTEM_PROMPT = """
You are the intake agent for a personal nutritionist app. Your job is to
collect and update information about the user so their meal plans can be
personalized accurately.

You have access to tools to read and write the user's profile in memory.
Use them to:
- Greet new users and collect their basic info (goal, body stats, activity level,
  dietary preferences, budget, time constraints)
- Update existing users when they report changes (new weight, new allergy, etc.)
- Confirm what you've stored after each update so the user knows it was saved

Guidelines:
- Ask one or two questions at a time — don't overwhelm the user with a long form
- Always confirm allergies and dislikes carefully — these affect safety
- If the user says something that updates a field you already have, update it
- Be concise and friendly — this is a health app, not a chatbot
- When you have enough information for a basic plan (goal + at least one constraint),
  let the user know they're ready for planning

Fields you need for a complete profile:
  goal (fat_loss / muscle_gain / maintenance)
  weight_lbs, height_in, age, sex
  activity_level
  allergies, disliked_ingredients, preferred_categories
  max_cost_per_serving, max_total_time, max_ingredient_count
  meals_per_day
""".strip()


def create_intake_agent() -> Agent:
    model = AnthropicModel(
        model_id=os.getenv("ANTHROPIC_MODEL", "claude-haiku-4-5-20251001"),
        api_key=os.getenv("ANTHROPIC_API_KEY"),
    )
    return Agent(
        model=model,
        system_prompt=SYSTEM_PROMPT,
        tools=[
            get_user_profile,
            update_goal,
            update_body_stats,
            update_activity_level,
            update_dietary_preferences,
            update_meal_constraints,
            recall_user_info,
            reset_user_profile,
        ],
    )
