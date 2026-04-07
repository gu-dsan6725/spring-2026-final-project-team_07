from __future__ import annotations

import json
from litellm import completion

from sage.config import (
    NARRATOR_MODEL,
    NARRATOR_TEMPERATURE,
    NARRATOR_MAX_TOKENS,
)
from sage.schemas import RunState


SYSTEM_PROMPT = """
You are the narrator for SAGE, a stateful tower-run game system.

Your job:
- Describe the current floor clearly and briefly
- Summarize the most recent event
- Suggest 2-4 sensible player actions

Rules:
- Do not invent state that is not present
- Do not change game state
- Keep descriptions concise
- If there is a combat encounter, mention the enemy
- If there is a puzzle encounter, mention the puzzle prompt
- If there is a rest floor, mention healing/safety

Return valid JSON with exactly these keys:
{
  "description": "...",
  "last_event_summary": "...",
  "suggested_actions": ["...", "..."]
}
""".strip()


def _build_user_prompt(state: RunState) -> str:
    recent_event = state.log[-1].model_dump() if state.log else None
    payload = {
        "floor_number": state.floor_number,
        "turn": state.turn,
        "party": state.party.model_dump(),
        "encounter": state.encounter.model_dump(),
        "recent_event": recent_event,
    }
    return json.dumps(payload, indent=2)


def narrate(state: RunState) -> dict:
    response = completion(
        model=NARRATOR_MODEL,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": _build_user_prompt(state)},
        ],
        temperature=NARRATOR_TEMPERATURE,
        max_tokens=NARRATOR_MAX_TOKENS,
        seed=42,
        response_format={"type": "json_object"},
    )

    content = response.choices[0].message.content
    result = json.loads(content)

    return {
        "description": result["description"],
        "last_event_summary": result["last_event_summary"],
        "suggested_actions": result["suggested_actions"],
        "usage": getattr(response, "usage", None),
    }