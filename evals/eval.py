"""
Braintrust Evaluations for the Personal Nutritionist Orchestrator.

Runs single-turn evaluations against a pre-seeded user profile (intake_test_user).
All scorers are deterministic (no LLM judge) to keep costs low.

Usage:
    PYTHONPATH=src uv run python evals/eval.py
    PYTHONPATH=src uv run python evals/eval.py --no-send-logs
    PYTHONPATH=src uv run python evals/eval.py --debug
"""

import argparse
import json
import logging
import os
import re
import time
from pathlib import Path
from typing import Any, Optional

from braintrust import Eval
from dotenv import load_dotenv

load_dotenv()

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

DEFAULT_DATASET_PATH    = Path(__file__).parent / "dataset.json"
DEFAULT_OUTPUT_PATH     = Path(__file__).parent / "eval_metrics.json"
CHECKPOINT_PATH         = Path(__file__).parent / "eval_checkpoint.json"
BRAINTRUST_PROJECT_NAME = "personal-nutritionist-evals"
EVAL_USER_ID            = "intake_test_user"


# ---------------------------------------------------------------------------
# Checkpoint helpers — save/restore per-case results so a failed run can resume
# ---------------------------------------------------------------------------

def _load_checkpoint() -> dict[str, dict]:
    """Load cached results from a previous run, keyed by input text."""
    if CHECKPOINT_PATH.exists():
        with open(CHECKPOINT_PATH) as f:
            data = json.load(f)
        logger.info("Loaded checkpoint with %d cached results from %s", len(data), CHECKPOINT_PATH)
        return data
    return {}


def _save_checkpoint(cache: dict[str, dict]) -> None:
    """Persist the current results cache to disk."""
    with open(CHECKPOINT_PATH, "w") as f:
        json.dump(cache, f, indent=2)


# ---------------------------------------------------------------------------
# Agent runner
# ---------------------------------------------------------------------------

def _run_agent_on_input(input_text: str, user_id: str = EVAL_USER_ID) -> dict:
    """Run the orchestrator on a single input and return output + metadata."""
    from personal_nutritionist.agents.orchestrator.agent import create_orchestrator

    agent = create_orchestrator(user_id=user_id)

    logger.info("Running orchestrator [%s]: %s", user_id, input_text[:80])
    start = time.time()
    response = agent(input_text)
    elapsed = time.time() - start

    output_text = str(response)
    tools_used = _extract_tools_used(agent)

    logger.info("Done in %.1fs, tools=%s", elapsed, tools_used)
    return {"output": output_text, "tools_used": tools_used, "latency_seconds": elapsed}


def _extract_tools_used(agent: Any) -> list[str]:
    """Pull tool names from the agent's message history."""
    tools_used = []
    for message in getattr(agent, "messages", []):
        if not isinstance(message, dict):
            continue
        for block in message.get("content", []):
            if not isinstance(block, dict):
                continue
            tool_use = block.get("toolUse")
            if tool_use and isinstance(tool_use, dict):
                name = tool_use.get("name", "")
                if name and name not in tools_used:
                    tools_used.append(name)
    return tools_used


# ---------------------------------------------------------------------------
# Custom scorers
# ---------------------------------------------------------------------------

def tool_selection_scorer(
    input: str, output: str,
    expected: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """Check the agent called the expected tools (recall-based, mild precision penalty)."""
    if not metadata:
        return None
    expected_tools = metadata.get("expected_tools", [])
    tools_used     = metadata.get("tools_used", [])
    if not expected_tools:
        return None

    expected_set = set(expected_tools)
    used_set     = set(tools_used)
    correct      = expected_set & used_set
    recall       = len(correct) / len(expected_set)
    extra        = used_set - expected_set
    score        = max(0.0, recall - len(extra) * 0.1)

    return {
        "name": "ToolSelection",
        "score": score,
        "metadata": {
            "expected": sorted(expected_set),
            "used":     sorted(used_set),
            "correct":  sorted(correct),
            "extra":    sorted(extra),
        },
    }


def latency_scorer(
    input: str, output: str,
    expected: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """Score response time: <15s=1.0, <30s=0.75, <60s=0.5, <120s=0.25, else=0."""
    if not metadata:
        return None
    latency = metadata.get("latency_seconds")
    if latency is None:
        return None

    if latency < 15:
        score = 1.0
    elif latency < 30:
        score = 0.75
    elif latency < 60:
        score = 0.5
    elif latency < 120:
        score = 0.25
    else:
        score = 0.0

    return {"name": "Latency", "score": score, "metadata": {"latency_seconds": round(latency, 2)}}


def no_error_scorer(
    input: str, output: str,
    expected: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """Fail if the response contains multiple strong error indicators."""
    if not output:
        return {"name": "NoError", "score": 0, "metadata": {"reason": "empty output"}}

    patterns = ["traceback", "exception", "timed out", "500 error", "api error"]
    found = [p for p in patterns if p in output.lower()]
    is_error = len(found) >= 1

    return {"name": "NoError", "score": 0 if is_error else 1, "metadata": {"found": found}}


def scope_awareness_scorer(
    input: str, output: str,
    expected: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """Out-of-scope requests should be declined; in-scope requests should not."""
    if not metadata or not output:
        return None

    category    = metadata.get("category", "")
    output_lower = output.lower()
    decline_phrases = [
        "i can't", "i cannot", "i'm not able", "i don't have the ability",
        "i don't have access", "i'm unable", "outside my capabilities",
        "beyond my capabilities", "don't have a tool", "no tool",
        "not able to book", "not able to order", "unable to book",
        "unable to order", "unfortunately", "not something i can",
        "focused on nutrition", "focused on meal", "only able to",
        "not designed to",
    ]
    is_declining = any(p in output_lower for p in decline_phrases)

    if category == "out_of_scope":
        return {
            "name": "ScopeAwareness",
            "score": 1 if is_declining else 0,
            "metadata": {"expected": "decline", "declined": is_declining},
        }

    if is_declining:
        return {
            "name": "ScopeAwareness",
            "score": 0,
            "metadata": {"expected": "answer", "declined": True},
        }
    return {
        "name": "ScopeAwareness",
        "score": 1,
        "metadata": {"expected": "answer", "declined": False},
    }


def plan_completeness_scorer(
    input: str, output: str,
    expected: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """Check plan output contains calories, protein, meal names, and cost."""
    if not metadata or metadata.get("category") not in (
        "meal_planning", "dietary_restriction", "shopping_list"
    ):
        return None

    checks = {
        "has_breakfast": "breakfast" in output.lower(),
        "has_lunch":     "lunch"     in output.lower(),
        "has_dinner":    "dinner"    in output.lower(),
        "has_calories":  bool(re.search(r"\d[\d,]* ?(calories|kcal|cal)\b", output, re.I)),
        "has_protein":   bool(re.search(r"\d+\.?\d* ?g ?(protein|of protein)", output, re.I)),
        "has_cost":      bool(re.search(r"\$\d+\.?\d*", output)),
    }
    score = sum(checks.values()) / len(checks)
    return {"name": "PlanCompleteness", "score": score, "metadata": checks}


def calorie_target_scorer(
    input: str, output: str,
    expected: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """
    Extract the total/daily calories from the output text and check they
    land within ±15% of the user's 2,279 kcal target.
    """
    if not metadata or metadata.get("category") not in ("meal_planning", "dietary_restriction"):
        return None

    # Look for patterns like "2,194 calories", "Total Calories: 2,210", "2194 kcal"
    match = re.search(
        r"(?:total|daily)[^\n]*?(\d[\d,]+)\s*(?:calories|kcal|cal)\b",
        output, re.IGNORECASE,
    )
    if not match:
        # Fallback: first standalone 4-digit calorie-like number near a keyword
        match = re.search(r"(\d[\d,]+)\s*(?:calories|kcal|cal)\b", output, re.IGNORECASE)

    if not match:
        return {"name": "CalorieTarget", "score": 0.0, "metadata": {"reason": "no calorie value found"}}

    actual = float(match.group(1).replace(",", ""))
    target = 2279.0
    lo, hi = target * 0.85, target * 1.15

    if lo <= actual <= hi:
        score = 1.0
    elif actual < lo:
        score = max(0.0, 1.0 - (lo - actual) / lo)
    else:
        score = max(0.0, 1.0 - (actual - hi) / hi)

    return {
        "name": "CalorieTarget",
        "score": round(score, 3),
        "metadata": {
            "actual":  actual,
            "target":  target,
            "range":   [round(lo), round(hi)],
            "in_range": lo <= actual <= hi,
        },
    }


def allergen_safety_scorer(
    input: str, output: str,
    expected: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """
    For dietary_restriction tests, check the plan doesn't mention peanut
    butter or other peanut-containing ingredients in a meal context.
    Checks the ingredient listings in the output, not general text.
    """
    if not metadata or metadata.get("category") != "dietary_restriction":
        return None

    # Target specific ingredient strings, not generic mentions of "peanut"
    allergen_patterns = [r"peanut butter", r"peanut oil", r"\bpeanuts?\b(?!.{0,20}free)"]
    found = []
    for pattern in allergen_patterns:
        matches = re.findall(pattern, output, re.IGNORECASE)
        found.extend(matches)

    passed = len(found) == 0
    return {
        "name": "AllergenSafety",
        "score": 1.0 if passed else 0.0,
        "metadata": {"allergens_found": found},
    }


def shopping_list_scorer(
    input: str, output: str,
    expected: Optional[str] = None,
    metadata: Optional[dict] = None,
) -> Optional[dict]:
    """Check shopping list output contains aggregated ingredients with quantities."""
    if not metadata or metadata.get("category") != "shopping_list":
        return None

    checks = {
        "mentions_shopping_list": bool(re.search(
            r"shopping list|ingredients (to buy|needed|list)", output, re.I
        )),
        "has_quantities": bool(re.search(
            r"\d+\.?\d* ?(cup|tbsp|tsp|oz|lb|g|clove|can|slice|pint|qt)\b",
            output, re.I,
        )),
        "has_multiple_items": len(re.findall(r"(?m)^[-•*]\s|\n-\s", output)) >= 5
                              or output.lower().count("\n") >= 8,
    }
    score = sum(checks.values()) / len(checks)
    return {"name": "ShoppingList", "score": score, "metadata": checks}


# ---------------------------------------------------------------------------
# Task / data wrappers (Braintrust pattern)
# ---------------------------------------------------------------------------

def _create_wrapped_task(dataset: list[dict], sleep_seconds: int = 45):
    """
    Pre-run every test case and cache results so scorers can access
    runtime metadata (tools_used, latency) via the metadata dict.
    """
    # Seed cache from checkpoint so completed cases are not re-run
    results_cache: dict[str, dict] = _load_checkpoint()

    def data():
        cases = []
        for case in dataset:
            input_text = case["input"]
            user_id    = case.get("user_id", EVAL_USER_ID)

            if input_text in results_cache:
                logger.info("Checkpoint hit — skipping: %s", input_text[:60])
                result = results_cache[input_text]
            else:
                logger.info("Running: %s", input_text[:60])
                result = _run_agent_on_input(input_text, user_id=user_id)
                results_cache[input_text] = result
                _save_checkpoint(results_cache)  # persist immediately after each case
                if sleep_seconds > 0:
                    logger.info("Sleeping %ds before next case...", sleep_seconds)
                    time.sleep(sleep_seconds)

            cases.append({
                "input":    input_text,
                "expected": case.get("expected_output", ""),
                "metadata": {
                    "category":        case.get("category", ""),
                    "difficulty":      case.get("difficulty", ""),
                    "expected_tools":  case.get("expected_tools", []),
                    "user_id":         user_id,
                    "tools_used":      result["tools_used"],
                    "latency_seconds": result["latency_seconds"],
                },
            })
        return cases

    def task(input: str) -> str:
        if input in results_cache:
            return results_cache[input]["output"]
        result = _run_agent_on_input(input)
        return result["output"]

    return task, data


# ---------------------------------------------------------------------------
# Summary + export
# ---------------------------------------------------------------------------

def _print_eval_summary(eval_result: Any, dataset: list[dict]) -> None:
    results = eval_result.results
    if not results:
        logger.warning("No results to summarise")
        return

    category_lookup = {c["input"]: c.get("category", "unknown") for c in dataset}
    scorer_scores: dict[str, list[float]] = {}
    category_scores: dict[str, list[float]] = {}
    error_cases = []

    for r in results:
        input_text = str(r.input) if r.input else ""
        category   = category_lookup.get(input_text, "unknown")

        if r.error:
            error_cases.append({"input": input_text[:80], "error": str(r.error)})
            continue

        for scorer_name, score_val in r.scores.items():
            if score_val is None:
                continue
            scorer_scores.setdefault(scorer_name, []).append(score_val)
            category_scores.setdefault(f"{category}/{scorer_name}", []).append(score_val)

    print("\n" + "=" * 80)
    print("PERSONAL NUTRITIONIST — EVALUATION SUMMARY")
    print("=" * 80)
    print(f"Total cases: {len(results)}  |  Errors: {len(error_cases)}")
    print()

    print(f"{'Scorer':<30} {'Avg':>8} {'Min':>8} {'Max':>8} {'N':>6}")
    print("-" * 60)
    for name in sorted(scorer_scores):
        s = scorer_scores[name]
        print(f"{name:<30} {sum(s)/len(s):>8.2%} {min(s):>8.2f} {max(s):>8.2f} {len(s):>6}")

    print("\n— Per-category breakdown —")
    for cat in sorted({c["category"] for c in dataset}):
        print(f"\n  [{cat}]")
        for name in sorted(scorer_scores):
            key = f"{cat}/{name}"
            if key in category_scores:
                s = category_scores[key]
                print(f"    {name:<28} {sum(s)/len(s):>7.2%}  (n={len(s)})")

    if error_cases:
        print("\n— Errors —")
        for e in error_cases:
            print(f"  {e['input']}\n  → {e['error']}\n")

    print("=" * 80 + "\n")


def _export_eval_metrics(
    eval_result: Any,
    dataset: list[dict],
    output_path: str = str(DEFAULT_OUTPUT_PATH),
) -> None:
    results = eval_result.results
    if not results:
        return

    category_lookup = {c["input"]: c.get("category", "unknown") for c in dataset}
    scorer_scores: dict[str, list[float]] = {}
    per_case = []

    for r in results:
        input_text = str(r.input) if r.input else ""
        entry = {
            "input":    input_text[:120],
            "category": category_lookup.get(input_text, "unknown"),
            "scores":   {},
            "error":    str(r.error) if r.error else None,
        }
        if not r.error:
            for name, val in r.scores.items():
                if val is not None:
                    entry["scores"][name] = round(val, 4)
                    scorer_scores.setdefault(name, []).append(val)
        per_case.append(entry)

    overall = {
        name: {
            "average": round(sum(s) / len(s), 4),
            "min":     round(min(s), 4),
            "max":     round(max(s), 4),
            "count":   len(s),
        }
        for name, s in sorted(scorer_scores.items())
    }

    metrics = {
        "total_cases": len(results),
        "errors":      sum(1 for r in results if r.error),
        "overall_scores": overall,
        "per_case":    per_case,
    }

    with open(output_path, "w") as f:
        json.dump(metrics, f, indent=2)
    logger.info("Metrics exported to %s", output_path)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Run Personal Nutritionist evals")
    p.add_argument("--dataset",      default=str(DEFAULT_DATASET_PATH))
    p.add_argument("--output",       default=str(DEFAULT_OUTPUT_PATH))
    p.add_argument("--no-send-logs",      action="store_true")
    p.add_argument("--experiment-name",   default=None)
    p.add_argument("--clear-checkpoint",  action="store_true",
                   help="Delete the checkpoint file and run all cases from scratch")
    p.add_argument("--sleep",             type=int, default=45,
                   help="Seconds to sleep between eval cases (default: 45)")
    p.add_argument("--debug",             action="store_true")
    return p.parse_args()


def main() -> None:
    args = _parse_args()
    if args.debug:
        logging.getLogger().setLevel(logging.DEBUG)

    if args.clear_checkpoint and CHECKPOINT_PATH.exists():
        CHECKPOINT_PATH.unlink()
        logger.info("Checkpoint cleared")

    dataset_path = Path(args.dataset)
    if not dataset_path.exists():
        raise FileNotFoundError(f"Dataset not found: {dataset_path}")

    with open(dataset_path) as f:
        dataset = json.load(f)
    logger.info("Loaded %d test cases", len(dataset))

    task_fn, data_fn = _create_wrapped_task(dataset, sleep_seconds=args.sleep)

    scorers = [
        tool_selection_scorer,
        latency_scorer,
        no_error_scorer,
        scope_awareness_scorer,
        plan_completeness_scorer,
        calorie_target_scorer,
        allergen_safety_scorer,
        shopping_list_scorer,
    ]

    eval_kwargs: dict = {"data": data_fn, "task": task_fn, "scores": scorers}
    if args.experiment_name:
        eval_kwargs["experiment_name"] = args.experiment_name
    if args.no_send_logs:
        eval_kwargs["no_send_logs"] = True

    logger.info("Starting Braintrust eval — project: %s", BRAINTRUST_PROJECT_NAME)
    t0 = time.time()
    eval_result = Eval(BRAINTRUST_PROJECT_NAME, **eval_kwargs)

    _print_eval_summary(eval_result, dataset)
    _export_eval_metrics(eval_result, dataset, output_path=args.output)

    elapsed = time.time() - t0
    logger.info("Completed in %.0fs (%.1f min)", elapsed, elapsed / 60)


if __name__ == "__main__":
    main()
