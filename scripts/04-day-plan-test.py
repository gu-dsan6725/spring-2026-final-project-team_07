from personal_nutritionist.agents.planning.tools import (
    get_user_profile,
    search_meals_tool,
    build_day_plan_tool,
)

profile = get_user_profile("tyler")

filters_dict = {
    "max_cost_per_serving": profile["max_cost_per_serving"],
    "max_total_time": profile["max_total_time"],
    "max_ingredient_count": profile["max_ingredient_count"],
}

breakfasts = search_meals_tool("breakfast", filters_dict)
lunches = search_meals_tool("lunch", filters_dict)
dinners = search_meals_tool("dinner", filters_dict)

print(f"Found {len(breakfasts)} breakfasts, {len(lunches)} lunches, {len(dinners)} dinners")
print()

plan = build_day_plan_tool(filters_dict, include_snack=True)

print("Breakfast:", plan["breakfast"]["title"])
print("Lunch:    ", plan["lunch"]["title"])
print("Dinner:   ", plan["dinner"]["title"])
print("Snack:    ", plan["snack"]["title"] if plan["snack"] else "None")
print()
print("Calories:", plan["totals"]["calories"])
print("Protein: ", plan["totals"]["protein"])
print("Cost:    ", round(plan["totals"]["cost"], 2))
