import random

from sage.agents.narrator import narrate
from sage.engine.loop import step
from sage.loaders import load_all_content
from sage.schemas import Event, PartyState, RunState
from sage.tools.floors import (
    build_combat_encounter,
    build_puzzle_encounter,
    build_rest_encounter,
)

DATA_DIR = "data/sample"
SEED = 42


def build_demo_encounters(enemies, puzzles, floors):
    rng = random.Random(SEED)
    combat_template = next(f for f in floors if f.floor_type == "combat")
    puzzle_template = next(f for f in floors if f.floor_type == "puzzle")
    rest_template = next(f for f in floors if f.floor_type == "rest")
    return (
        build_combat_encounter(combat_template, enemies, rng),
        build_puzzle_encounter(puzzle_template, puzzles, rng),
        build_rest_encounter(rest_template),
    )


def render(state, narration):
    print("\n" + "=" * 50)
    print(f"Floor {state.floor_number} — {state.encounter.floor_type.upper()}")
    print(f"HP: {state.party.hp}/{state.party.max_hp}  |  Gold: {state.party.gold}")
    print()
    print(f"[Narrator] {narration['description']}")
    print(f"[Last Event] {narration['last_event_summary']}")
    print(f"[Suggested Actions] {', '.join(narration['suggested_actions'])}")
    print()

    enc = state.encounter
    if enc.floor_type == "combat" and enc.enemy:
        print(f"Enemy: {enc.enemy.name} (HP: {enc.enemy.hp})")
    elif enc.floor_type == "puzzle" and enc.puzzle:
        print(f"Puzzle: {enc.puzzle.name}")
        print(f"Prompt: {enc.puzzle.prompt}")
        print(f"Attempts Left: {enc.attempts_left}")
    elif enc.floor_type == "rest":
        print(f"Heal Amount: {enc.heal_amount}")


def force_floor(state, encounter, floor_number):
    s = state.model_copy(deep=True)
    s.encounter = encounter
    s.floor_number = floor_number
    return s


def main():
    enemies, puzzles, floors = load_all_content(DATA_DIR)
    combat_enc, puzzle_enc, rest_enc = build_demo_encounters(enemies, puzzles, floors)

    # ── Floor 1: Combat ──────────────────────────────────────────────────────
    state = RunState(
        run_id="demo-run",
        seed=SEED,
        floor_number=1,
        turn=0,
        party=PartyState(hp=20, max_hp=20, gold=0, inventory=[], statuses=[]),
        encounter=combat_enc,
        log=[Event(turn=0, kind="run_started", payload={"run_id": "demo-run", "seed": SEED, "floor_number": 1})],
    )
    render(state, narrate(state))
    print("--- Auto-playing combat (attack each turn) ---")
    while state.encounter.floor_type == "combat":
        print(f"  > attack  (enemy HP: {state.encounter.enemy.hp})")
        state = step(state, "attack")
    print(f"  Victory! HP: {state.party.hp}  Gold: {state.party.gold}")

    # ── Floor 2: Puzzle ──────────────────────────────────────────────────────
    state = force_floor(state, puzzle_enc, 2)
    render(state, narrate(state))
    answer = puzzle_enc.puzzle.answer
    print(f"--- Auto-solving puzzle with answer: '{answer}' ---")
    state = step(state, answer)
    print(f"  Solved! HP: {state.party.hp}  Gold: {state.party.gold}")

    # ── Floor 3: Rest ────────────────────────────────────────────────────────
    state = force_floor(state, rest_enc, 3)
    render(state, narrate(state))
    print("--- Auto-resting ---")
    state = step(state, "")
    print(f"  Rested. HP: {state.party.hp}/{state.party.max_hp}")

    print("\n" + "=" * 50)
    print("Demo complete.")
    print(f"Final HP: {state.party.hp}/{state.party.max_hp}  |  Final Gold: {state.party.gold}")


if __name__ == "__main__":
    main()
