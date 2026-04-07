"""
Smoke test for the planning agent.

Prerequisites: run 02-get-user-profile-test.py first to confirm "tyler"
has a profile in Mem0, or 06-intake-agent-test.py to seed a test profile.

Tests:
  1. Ask for a single day plan — verify the agent derives targets and returns meals
  2. Ask for a 3-day plan — verify it switches to week plan logic

Output is tee'd to test-output/07-planning-agent-test.log
"""

import sys
from datetime import datetime
from pathlib import Path

from personal_nutritionist.agents.planning.agent import create_planning_agent

Path("test-output").mkdir(exist_ok=True)
_log = open("test-output/07-planning-agent-test.log", "w")


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
print(f"=== 07-planning-agent-test | {datetime.now().isoformat(timespec='seconds')} ===\n")

agent = create_planning_agent(user_id="intake_test_user")

turns = [
    "Build me a day plan.",
    "Now build me a 3-day plan with the same constraints.",
]

for msg in turns:
    print(f"USER: {msg}")
    agent(msg)
    print()
