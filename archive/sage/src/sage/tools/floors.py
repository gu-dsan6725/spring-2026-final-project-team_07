from __future__ import annotations

import random

from sage.schemas import EncounterState, Enemy, FloorTemplate, Puzzle


def choose_floor_template(
    floors: list[FloorTemplate],
    rng: random.Random,
) -> FloorTemplate:
    """
    Select a floor template using weighted random choice.
    """
    weights = [floor.weight for floor in floors]
    return rng.choices(floors, weights=weights, k=1)[0]


def build_combat_encounter(
    floor: FloorTemplate,
    enemies: dict[str, Enemy],
    rng: random.Random,
) -> EncounterState:
    """
    Instantiate a combat floor by selecting one enemy from the floor's enemy pool.
    """
    enemy_id = rng.choice(floor.enemy_pool)
    enemy = enemies[enemy_id]

    return EncounterState(
        floor_id=floor.id,
        floor_type="combat",
        description=floor.description_template,
        enemy=enemy,
    )


def build_puzzle_encounter(
    floor: FloorTemplate,
    puzzles: dict[str, Puzzle],
    rng: random.Random,
) -> EncounterState:
    """
    Instantiate a puzzle floor by selecting one puzzle from the floor's puzzle pool.
    """
    puzzle_id = rng.choice(floor.puzzle_pool)
    puzzle = puzzles[puzzle_id]

    return EncounterState(
        floor_id=floor.id,
        floor_type="puzzle",
        description=floor.description_template,
        puzzle=puzzle,
        attempts_left=puzzle.max_attempts,
    )


def build_rest_encounter(
    floor: FloorTemplate,
) -> EncounterState:
    """
    Instantiate a rest floor.
    """
    return EncounterState(
        floor_id=floor.id,
        floor_type="rest",
        description=floor.description_template,
        heal_amount=floor.heal_amount,
    )


def generate_floor(
    floors: list[FloorTemplate],
    enemies: dict[str, Enemy],
    puzzles: dict[str, Puzzle],
    seed: int,
    floor_number: int,
) -> EncounterState:
    """
    Generate one concrete floor encounter deterministically from loaded content.
    """
    rng = random.Random(f"{seed}-{floor_number}")

    floor_template = choose_floor_template(floors, rng)

    if floor_template.floor_type == "combat":
        return build_combat_encounter(floor_template, enemies, rng)

    if floor_template.floor_type == "puzzle":
        return build_puzzle_encounter(floor_template, puzzles, rng)

    if floor_template.floor_type == "rest":
        return build_rest_encounter(floor_template)

    raise ValueError(f"Unsupported floor type: {floor_template.floor_type}")