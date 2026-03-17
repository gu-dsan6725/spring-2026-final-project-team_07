from __future__ import annotations

from sage.loaders import load_all_content
from sage.schemas import EncounterState, Event, PartyState, RunState
from sage.tools.floors import generate_floor


def new_run(
    run_id: str,
    seed: int,
    data_dir: str = "data/sample",
) -> RunState:
    enemies, puzzles, floors = load_all_content(data_dir)

    first_encounter = generate_floor(
        floors=floors,
        enemies=enemies,
        puzzles=puzzles,
        seed=seed,
        floor_number=1,
    )

    return RunState(
        run_id=run_id,
        seed=seed,
        floor_number=1,
        turn=0,
        party=PartyState(
            hp=20,
            max_hp=20,
            gold=0,
            inventory=[],
            statuses=[],
        ),
        encounter=first_encounter,
        log=[
            Event(
                turn=0,
                kind="run_started",
                payload={
                    "run_id": run_id,
                    "seed": seed,
                    "floor_number": 1,
                },
            )
        ],
    )


def advance_floor(
    state: RunState,
    data_dir: str = "data/sample",
) -> RunState:
    enemies, puzzles, floors = load_all_content(data_dir)

    next_floor_number = state.floor_number + 1
    next_encounter = generate_floor(
        floors=floors,
        enemies=enemies,
        puzzles=puzzles,
        seed=state.seed,
        floor_number=next_floor_number,
    )

    new_state = state.model_copy(deep=True)
    new_state.floor_number = next_floor_number
    new_state.encounter = next_encounter
    new_state.log.append(
        Event(
            turn=new_state.turn,
            kind="floor_advanced",
            payload={"floor_number": next_floor_number},
        )
    )
    return new_state


def resolve_combat_action(state: RunState, action: str) -> RunState:
    new_state = state.model_copy(deep=True)
    new_state.turn += 1

    enemy = new_state.encounter.enemy
    if enemy is None:
        raise ValueError("Combat encounter missing enemy")

    if action.strip().lower() != "attack":
        new_state.log.append(
            Event(
                turn=new_state.turn,
                kind="invalid_action",
                payload={"action": action, "reason": "Only 'attack' is supported in milestone version"},
            )
        )
        return new_state

    enemy.hp -= 5

    new_state.log.append(
        Event(
            turn=new_state.turn,
            kind="combat_action",
            payload={
                "action": "attack",
                "enemy_id": enemy.id,
                "enemy_hp_remaining": max(enemy.hp, 0),
            },
        )
    )

    if enemy.hp <= 0:
        new_state.party.gold += enemy.reward.gold
        new_state.log.append(
            Event(
                turn=new_state.turn,
                kind="combat_victory",
                payload={
                    "enemy_id": enemy.id,
                    "gold_awarded": enemy.reward.gold,
                },
            )
        )
        return advance_floor(new_state)

    new_state.party.hp = max(0, new_state.party.hp - 2)
    new_state.log.append(
        Event(
            turn=new_state.turn,
            kind="enemy_counterattack",
            payload={
                "enemy_id": enemy.id,
                "damage_taken": 2,
                "player_hp_remaining": new_state.party.hp,
            },
        )
    )

    return new_state


def resolve_puzzle_action(state: RunState, action: str) -> RunState:
    new_state = state.model_copy(deep=True)
    new_state.turn += 1

    puzzle = new_state.encounter.puzzle
    if puzzle is None:
        raise ValueError("Puzzle encounter missing puzzle")

    guess = action.strip().lower()
    correct_answer = puzzle.answer.strip().lower()

    new_state.encounter.attempts_left = (new_state.encounter.attempts_left or 0) - 1

    if guess == correct_answer:
        new_state.party.gold += puzzle.success_reward.gold
        new_state.log.append(
            Event(
                turn=new_state.turn,
                kind="puzzle_solved",
                payload={
                    "puzzle_id": puzzle.id,
                    "guess": guess,
                    "gold_awarded": puzzle.success_reward.gold,
                },
            )
        )
        return advance_floor(new_state)

    new_state.log.append(
        Event(
            turn=new_state.turn,
            kind="puzzle_failed_attempt",
            payload={
                "puzzle_id": puzzle.id,
                "guess": guess,
                "attempts_left": new_state.encounter.attempts_left,
            },
        )
    )

    if (new_state.encounter.attempts_left or 0) <= 0:
        hp_loss = puzzle.failure_penalty.hp_loss
        new_state.party.hp = max(0, new_state.party.hp - hp_loss)
        new_state.log.append(
            Event(
                turn=new_state.turn,
                kind="puzzle_failed",
                payload={
                    "puzzle_id": puzzle.id,
                    "hp_loss": hp_loss,
                    "player_hp_remaining": new_state.party.hp,
                },
            )
        )
        return advance_floor(new_state)

    return new_state


def resolve_rest_floor(state: RunState) -> RunState:
    new_state = state.model_copy(deep=True)
    new_state.turn += 1

    heal_amount = new_state.encounter.heal_amount or 0
    old_hp = new_state.party.hp
    new_state.party.hp = min(new_state.party.max_hp, new_state.party.hp + heal_amount)

    new_state.log.append(
        Event(
            turn=new_state.turn,
            kind="rest",
            payload={
                "heal_amount": heal_amount,
                "hp_before": old_hp,
                "hp_after": new_state.party.hp,
            },
        )
    )

    return advance_floor(new_state)


def step(state: RunState, action: str) -> RunState:
    floor_type = state.encounter.floor_type

    if floor_type == "combat":
        return resolve_combat_action(state, action)

    if floor_type == "puzzle":
        return resolve_puzzle_action(state, action)

    if floor_type == "rest":
        return resolve_rest_floor(state)

    raise ValueError(f"Unsupported floor type: {floor_type}")