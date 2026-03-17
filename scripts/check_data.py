from sage.loaders import load_all_content


def main():
    enemies, puzzles, floors = load_all_content("data/sample")

    print(f"Loaded {len(enemies)} enemies")
    print(f"Loaded {len(puzzles)} puzzles")
    print(f"Loaded {len(floors)} floor templates")

    print("\nEnemy IDs:")
    for enemy_id in enemies:
        print(f"  - {enemy_id}")

    print("\nPuzzle IDs:")
    for puzzle_id in puzzles:
        print(f"  - {puzzle_id}")

    print("\nFloor templates:")
    for floor in floors:
        print(f"  - {floor.id} ({floor.floor_type})")


if __name__ == "__main__":
    main()