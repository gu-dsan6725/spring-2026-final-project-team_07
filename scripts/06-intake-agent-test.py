"""
Smoke test for the intake agent.

Simulates a new user conversation:
  1. Reset any existing test memories to start fresh
  2. Send a few messages collecting a basic profile
  3. Ask the agent to recall what it knows to verify writes landed in Mem0

Output is tee'd to test-output/06-intake-agent-test.log
"""

import sys
from datetime import datetime
from pathlib import Path

from personal_nutritionist.agents.intake.agent import create_intake_agent
from personal_nutritionist.agents.intake.tools import reset_user_profile

Path("test-output").mkdir(exist_ok=True)
_log = open("test-output/06-intake-agent-test.log", "w")


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
print(f"=== 06-intake-agent-test | {datetime.now().isoformat(timespec='seconds')} ===\n")

USER_ID = "intake_test_user"

# --- clean slate ---
reset_user_profile(USER_ID)
print(f"Reset memories for '{USER_ID}'\n")

agent = create_intake_agent()

turns = [
    f"Hi, my name is {USER_ID}. I want to lose fat.",
    "I'm 180 lbs, 5'10\" (70 inches), 28 years old, male. I'm moderately active.",
    "I'm allergic to peanuts. I dislike broccoli. I prefer Comfort Meals.",
    "My budget is $3 per serving, 30 minutes max, and I eat 3 meals a day.",
    "Can you tell me everything you have stored about me so far?",
]

for msg in turns:
    print(f"USER: {msg}")
    agent(msg)
    print()
