"""
Smoke test for the orchestrator.

Tests three things:
  1. Profile routing — ask for a profile summary (should call update_user_profile)
  2. Day plan — triggers the full plan-audit loop
  3. Plan adjustment — ask for a cheaper plan (should rebuild with override_filters)

Prerequisites: run 06-intake-agent-test.py first to seed intake_test_user.

Output is tee'd to test-output/09-orchestrator-test.log
"""

import sys
from datetime import datetime
from pathlib import Path

from personal_nutritionist.agents.orchestrator.agent import create_orchestrator

Path("test-output").mkdir(exist_ok=True)
_log = open("test-output/09-orchestrator-test.log", "w")


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
print(f"=== 09-orchestrator-test | {datetime.now().isoformat(timespec='seconds')} ===\n")

agent = create_orchestrator(user_id="intake_test_user")

turns = [
    "What does my profile look like?",
    "Build me a day plan.",
    "Can you rebuild it but with a max budget of $2 per serving?",
]

for msg in turns:
    print(f"USER: {msg}")
    agent(msg)
    print()
