import json
from sage.loaders import load_all_content
from sage.tools.floors import generate_floor


def main():
    enemies, puzzles, floors = load_all_content("data/sample")

    encounter = generate_floor(
        floors=floors,
        enemies=enemies,
        puzzles=puzzles,
        seed=123,
        floor_number=1,
    )

    print(json.dumps(encounter.model_dump(), indent=2))


if __name__ == "__main__":
    main()