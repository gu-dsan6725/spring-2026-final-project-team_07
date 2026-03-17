from sage.engine.loop import new_run
from sage.agents.narrator import narrate


def main():
    state = new_run(run_id="narrator-demo", seed=123)
    result = narrate(state)

    print("\nDescription:")
    print(result["description"])

    print("\nLast event summary:")
    print(result["last_event_summary"])

    print("\nSuggested actions:")
    for action in result["suggested_actions"]:
        print("-", action)

    print("\nUsage:")
    print(result["usage"])


if __name__ == "__main__":
    main()