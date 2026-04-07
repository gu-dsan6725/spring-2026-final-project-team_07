from personal_nutritionist.agents.planning.tools import build_day_plan_tool
from personal_nutritionist.agents.audit.tools import audit_day_plan, audit_week_plan

filters = {"max_cost_per_serving": 2.5, "max_total_time": 30}
TARGET_CALORIES = 2000.0
TARGET_PROTEIN = 150.0
DAILY_BUDGET = 10.0
WEEKLY_BUDGET = 50.0
N_DAYS = 3


def print_audit(label: str, issues: list[dict]) -> None:
    print(f"\n=== {label} ===")
    for issue in issues:
        status = "PASS" if issue["passed"] else "FAIL"
        print(f"  [{status}] {issue['check']}: {issue['message']}")


# --- Day plan audit ---
plan = build_day_plan_tool(filters, include_snack=True)

print("Day Plan:")
print(f"  Breakfast: {plan['breakfast']['title']}")
print(f"  Lunch:     {plan['lunch']['title']}")
print(f"  Dinner:    {plan['dinner']['title']}")
print(f"  Snack:     {plan['snack']['title'] if plan['snack'] else 'None'}")
print(f"  Calories:  {plan['totals']['calories']:.0f} kcal")
print(f"  Protein:   {plan['totals']['protein']:.1f}g")
print(f"  Cost:      ${plan['totals']['cost']:.2f}")

day_result = audit_day_plan(
    plan,
    target_calories=TARGET_CALORIES,
    target_protein=TARGET_PROTEIN,
    daily_cost_budget=DAILY_BUDGET,
)
print_audit("Day Audit", day_result["issues"])
print(f"\nDay audit passed: {day_result['passed']}")

# --- Week plan audit ---
week = [build_day_plan_tool(filters, include_snack=True) for _ in range(N_DAYS)]

week_result = audit_week_plan(
    week,
    target_calories=TARGET_CALORIES,
    target_protein=TARGET_PROTEIN,
    weekly_cost_budget=WEEKLY_BUDGET,
)
print_audit(f"Week Audit ({N_DAYS} days)", week_result["issues"])
print(f"\nWeek audit passed: {week_result['passed']}")
