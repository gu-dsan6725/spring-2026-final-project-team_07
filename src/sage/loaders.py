from __future__ import annotations

import json
from pathlib import Path

from sage.schemas import Enemy, Puzzle, FloorTemplate


def _load_json(path: str | Path):
    path = Path(path)
    with path.open("r", encoding="utf-8") as f:
        return json.load(f)


def load_enemies(path: str | Path) -> dict[str, Enemy]:
    raw_data = _load_json(path)
    enemies = [Enemy.model_validate(item) for item in raw_data]
    return {enemy.id: enemy for enemy in enemies}


def load_puzzles(path: str | Path) -> dict[str, Puzzle]:
    raw_data = _load_json(path)
    puzzles = [Puzzle.model_validate(item) for item in raw_data]
    return {puzzle.id: puzzle for puzzle in puzzles}


def load_floors(path: str | Path) -> list[FloorTemplate]:
    raw_data = _load_json(path)
    return [FloorTemplate.model_validate(item) for item in raw_data]


def validate_floor_references(
    floors: list[FloorTemplate],
    enemies: dict[str, Enemy],
    puzzles: dict[str, Puzzle],
) -> None:
    """
    Ensures that all enemy_pool and puzzle_pool references in floor templates
    point to real entries in the corresponding content dictionaries.
    Raises ValueError if anything is invalid.
    """
    for floor in floors:
        if floor.floor_type == "combat":
            if not floor.enemy_pool:
                raise ValueError(f"Combat floor '{floor.id}' has empty enemy_pool")

            missing_enemies = [enemy_id for enemy_id in floor.enemy_pool if enemy_id not in enemies]
            if missing_enemies:
                raise ValueError(
                    f"Combat floor '{floor.id}' references missing enemies: {missing_enemies}"
                )

        elif floor.floor_type == "puzzle":
            if not floor.puzzle_pool:
                raise ValueError(f"Puzzle floor '{floor.id}' has empty puzzle_pool")

            missing_puzzles = [puzzle_id for puzzle_id in floor.puzzle_pool if puzzle_id not in puzzles]
            if missing_puzzles:
                raise ValueError(
                    f"Puzzle floor '{floor.id}' references missing puzzles: {missing_puzzles}"
                )

        elif floor.floor_type == "rest":
            if floor.heal_amount is None:
                raise ValueError(f"Rest floor '{floor.id}' is missing heal_amount")


def load_all_content(data_dir: str | Path) -> tuple[dict[str, Enemy], dict[str, Puzzle], list[FloorTemplate]]:
    data_dir = Path(data_dir)

    enemies = load_enemies(data_dir / "enemies.json")
    puzzles = load_puzzles(data_dir / "puzzles.json")
    floors = load_floors(data_dir / "floors.json")

    validate_floor_references(floors, enemies, puzzles)

    return enemies, puzzles, floors