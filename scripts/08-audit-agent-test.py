"""
Smoke test for the audit agent.

Builds a real day plan using the planning tools, then asks the audit agent
to validate it against tyler's targets. Also injects a known-bad plan to
confirm the agent catches failures.

Output is tee'd to test-output/08-audit-agent-test.log
"""

import json
import sys
from datetime import datetime
from pathlib import Path

from personal_nutritionist.agents.audit.agent import create_audit_agent
from personal_nutritionist.agents.planning.tools import build_day_plan_tool

Path("test-output").mkdir(exist_ok=True)
_log = open("test-output/08-audit-agent-test.log", "w")


class _Tee:
    def __init__(self, *streams):
        self.streams = streams

    def write(self, data):
        for s in self.streams:
            s.write(data)

    def flush(self):
        for s in self.streams:
            s.flush()


sys.stdout = _Tee(sys.__stdout__, _log)
print(f"=== 08-audit-agent-test | {datetime.now().isoformat(timespec='seconds')} ===\n")

# --- build a real plan to audit ---
filters = {"max_cost_per_serving": 3.0, "max_total_time": 30}
plan = build_day_plan_tool(filters, include_snack=False)

print("Plan to audit:")
print(f"  Breakfast: {plan['breakfast']['title']}")
print(f"  Lunch:     {plan['lunch']['title']}")
print(f"  Dinner:    {plan['dinner']['title']}")
print(f"  Calories:  {plan['totals']['calories']:.0f} kcal")
print(f"  Protein:   {plan['totals']['protein']:.1f}g")
print(f"  Cost:      ${plan['totals']['cost']:.2f}")
print()

agent = create_audit_agent(user_id="intake_test_user")

# --- test 1: real plan against tyler's profile ---
msg1 = f"Audit this day plan:\n\n{json.dumps(plan, indent=2)}"
print(f"USER: {msg1}\n")
agent(msg1)
print()

# --- test 2: inject a plan that should fail (zero calories/protein/cost) ---
bad_plan = {
    "breakfast": {"title": "Air Sandwich", "calories": 0, "protein": 0, "cost_per_serving": 0.0},
    "lunch":     {"title": "Water Soup",   "calories": 0, "protein": 0, "cost_per_serving": 0.0},
    "dinner":    {"title": "Sad Salad",    "calories": 0, "protein": 0, "cost_per_serving": 0.0},
    "snack": None,
    "totals": {"calories": 0, "protein": 0, "cost": 0.0},
}

msg2 = f"Audit this day plan:\n\n{json.dumps(bad_plan, indent=2)}"
print(f"USER: {msg2}\n")
agent(msg2)
print()
