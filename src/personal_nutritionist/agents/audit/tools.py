import logging
from collections import Counter

from strands import tool

from personal_nutritionist.core.schemas import (
    AuditIssue,
    AuditResult,
    WeekPlanAuditResult,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# Tolerances
_CALORIE_TOLERANCE = 0.15   # ±15% of target
_PROTEIN_TOLERANCE = 0.10   # ±10% of target
_MAX_REPEAT_FRACTION = 0.4  # at most 40% of days may repeat the same meal


def _check_slots_present(day: dict) -> AuditIssue:
    missing = [s for s in ("breakfast", "lunch", "dinner") if not day.get(s)]
    return AuditIssue(
        check="required_slots_present",
        passed=len(missing) == 0,
        message="All required slots present." if not missing else f"Missing slots: {missing}",
    )


def _check_no_duplicates(day: dict) -> AuditIssue:
    meals = {s: day[s]["title"] for s in ("breakfast", "lunch", "dinner") if day.get(s)}
    if day.get("snack"):
        meals["snack"] = day["snack"]["title"]
    titles = list(meals.values())
    dupes = [t for t, n in Counter(titles).items() if n > 1]
    return AuditIssue(
        check="no_duplicate_meals",
        passed=len(dupes) == 0,
        message="No duplicate meals." if not dupes else f"Duplicate meals: {dupes}",
    )


def _check_slot_assignments(day: dict) -> AuditIssue:
    violations = []
    slot_map = {"breakfast": "breakfast", "lunch": "lunch", "dinner": "dinner", "snack": "snack"}
    for slot, key in slot_map.items():
        meal = day.get(key)
        if meal and slot not in meal.get("meal_slots", []):
            violations.append(f"{meal['title']} not eligible for {slot}")
    return AuditIssue(
        check="meal_slot_eligibility",
        passed=len(violations) == 0,
        message="All meals eligible for their slots." if not violations else "; ".join(violations),
    )


def _check_calories(totals: dict, target: float, tolerance: float) -> AuditIssue:
    actual = totals.get("calories", 0.0)
    lo, hi = target * (1 - tolerance), target * (1 + tolerance)
    passed = lo <= actual <= hi
    return AuditIssue(
        check="calorie_target",
        passed=passed,
        message=(
            f"Calories {actual:.0f} within ±{tolerance*100:.0f}% of target {target:.0f}."
            if passed
            else f"Calories {actual:.0f} outside target range [{lo:.0f}, {hi:.0f}]."
        ),
    )


def _check_protein(totals: dict, target: float, tolerance: float) -> AuditIssue:
    actual = totals.get("protein", 0.0)
    lo, hi = target * (1 - tolerance), target * (1 + tolerance)
    passed = lo <= actual <= hi
    return AuditIssue(
        check="protein_target",
        passed=passed,
        message=(
            f"Protein {actual:.1f}g within ±{tolerance*100:.0f}% of target {target:.1f}g."
            if passed
            else f"Protein {actual:.1f}g outside target range [{lo:.1f}g, {hi:.1f}g]."
        ),
    )


def _check_cost(totals: dict, budget: float) -> AuditIssue:
    actual = totals.get("cost", 0.0)
    return AuditIssue(
        check="daily_cost_budget",
        passed=actual <= budget,
        message=(
            f"Daily cost ${actual:.2f} within budget ${budget:.2f}."
            if actual <= budget
            else f"Daily cost ${actual:.2f} exceeds budget ${budget:.2f}."
        ),
    )


@tool
def audit_day_plan(
    plan: dict,
    target_calories: float,
    target_protein: float,
    daily_cost_budget: float,
    calorie_tolerance: float = _CALORIE_TOLERANCE,
    protein_tolerance: float = _PROTEIN_TOLERANCE,
) -> dict:
    """
    Audit a single day plan dict (as returned by build_day_plan_tool).

    Checks:
    - breakfast, lunch, dinner all present
    - no duplicate meals within the day
    - each meal is eligible for its assigned slot
    - total calories within tolerance of target
    - total protein within tolerance of target
    - total cost within daily budget

    Args:
        plan: Day plan dict with breakfast/lunch/dinner/snack and totals.
        target_calories: Daily calorie target.
        target_protein: Daily protein target in grams.
        daily_cost_budget: Maximum daily spend across all meals.
        calorie_tolerance: Fractional tolerance (default 0.15 = ±15%).
        protein_tolerance: Fractional tolerance (default 0.10 = ±10%).
    """
    totals = plan.get("totals", {})
    issues = [
        _check_slots_present(plan),
        _check_no_duplicates(plan),
        _check_slot_assignments(plan),
        _check_calories(totals, target_calories, calorie_tolerance),
        _check_protein(totals, target_protein, protein_tolerance),
        _check_cost(totals, daily_cost_budget),
    ]
    result = AuditResult.from_issues(issues)
    logger.info("audit_day_plan passed=%s issues=%s", result.passed, len(issues))
    return result.model_dump()


@tool
def audit_week_plan(
    week: list[dict],
    target_calories: float,
    target_protein: float,
    weekly_cost_budget: float,
    calorie_tolerance: float = _CALORIE_TOLERANCE,
    protein_tolerance: float = _PROTEIN_TOLERANCE,
    max_repeat_fraction: float = _MAX_REPEAT_FRACTION,
) -> dict:
    """
    Audit a list of day plan dicts representing a full week.

    Per-day checks (via audit_day_plan logic):
    - required slots present, no duplicates, slot eligibility

    Week-level checks:
    - all days meet minimum calorie/protein thresholds (target minus tolerance)
    - average daily calories within tolerance of target
    - average daily protein within tolerance of target
    - total weekly cost within weekly budget
    - no single meal title repeated on more than max_repeat_fraction of days

    Args:
        week: List of day plan dicts (one per day).
        target_calories: Daily calorie target.
        target_protein: Daily protein target in grams.
        weekly_cost_budget: Maximum total spend across all days.
        calorie_tolerance: Fractional tolerance for calorie checks.
        protein_tolerance: Fractional tolerance for protein checks.
        max_repeat_fraction: Max fraction of days a single meal may repeat.
    """
    # Run per-day structural checks
    day_results = []
    for day in week:
        issues = [
            _check_slots_present(day),
            _check_no_duplicates(day),
            _check_slot_assignments(day),
        ]
        day_results.append(AuditResult.from_issues(issues))

    n_days = len(week)
    all_totals = [d.get("totals", {}) for d in week]
    avg_calories = sum(t.get("calories", 0) for t in all_totals) / n_days if n_days else 0
    avg_protein = sum(t.get("protein", 0) for t in all_totals) / n_days if n_days else 0
    total_cost = sum(t.get("cost", 0) for t in all_totals)

    # Week-level checks
    week_issues: list[AuditIssue] = []

    # All days meet minimum calorie threshold
    cal_floor = target_calories * (1 - calorie_tolerance)
    days_below = [
        i + 1 for i, t in enumerate(all_totals) if t.get("calories", 0) < cal_floor
    ]
    week_issues.append(AuditIssue(
        check="all_days_min_calories",
        passed=len(days_below) == 0,
        message=(
            f"All days meet minimum {cal_floor:.0f} kcal."
            if not days_below
            else f"Days {days_below} fall below minimum {cal_floor:.0f} kcal."
        ),
    ))

    # All days meet minimum protein threshold
    pro_floor = target_protein * (1 - protein_tolerance)
    days_low_protein = [
        i + 1 for i, t in enumerate(all_totals) if t.get("protein", 0) < pro_floor
    ]
    week_issues.append(AuditIssue(
        check="all_days_min_protein",
        passed=len(days_low_protein) == 0,
        message=(
            f"All days meet minimum {pro_floor:.1f}g protein."
            if not days_low_protein
            else f"Days {days_low_protein} fall below minimum {pro_floor:.1f}g protein."
        ),
    ))

    # Average calories within tolerance
    cal_lo, cal_hi = target_calories * (1 - calorie_tolerance), target_calories * (1 + calorie_tolerance)
    week_issues.append(AuditIssue(
        check="avg_calorie_target",
        passed=cal_lo <= avg_calories <= cal_hi,
        message=(
            f"Avg daily calories {avg_calories:.0f} within target range [{cal_lo:.0f}, {cal_hi:.0f}]."
            if cal_lo <= avg_calories <= cal_hi
            else f"Avg daily calories {avg_calories:.0f} outside target range [{cal_lo:.0f}, {cal_hi:.0f}]."
        ),
    ))

    # Average protein within tolerance
    pro_lo, pro_hi = target_protein * (1 - protein_tolerance), target_protein * (1 + protein_tolerance)
    week_issues.append(AuditIssue(
        check="avg_protein_target",
        passed=pro_lo <= avg_protein <= pro_hi,
        message=(
            f"Avg daily protein {avg_protein:.1f}g within target range [{pro_lo:.1f}g, {pro_hi:.1f}g]."
            if pro_lo <= avg_protein <= pro_hi
            else f"Avg daily protein {avg_protein:.1f}g outside target range [{pro_lo:.1f}g, {pro_hi:.1f}g]."
        ),
    ))

    # Total weekly cost within budget
    week_issues.append(AuditIssue(
        check="weekly_cost_budget",
        passed=total_cost <= weekly_cost_budget,
        message=(
            f"Total weekly cost ${total_cost:.2f} within budget ${weekly_cost_budget:.2f}."
            if total_cost <= weekly_cost_budget
            else f"Total weekly cost ${total_cost:.2f} exceeds budget ${weekly_cost_budget:.2f}."
        ),
    ))

    # Meal variety — no title on more than max_repeat_fraction of days
    all_titles: list[str] = []
    for day in week:
        for slot in ("breakfast", "lunch", "dinner", "snack"):
            meal = day.get(slot)
            if meal:
                all_titles.append(meal["title"])
    max_repeats = max_repeat_fraction * n_days
    over_repeated = [t for t, n in Counter(all_titles).items() if n > max_repeats]
    week_issues.append(AuditIssue(
        check="meal_variety",
        passed=len(over_repeated) == 0,
        message=(
            "Meal variety is acceptable."
            if not over_repeated
            else f"Meals repeated too frequently (>{max_repeat_fraction*100:.0f}% of days): {over_repeated}"
        ),
    ))

    result = WeekPlanAuditResult.from_parts(day_results, week_issues)
    logger.info(
        "audit_week_plan passed=%s days=%s week_issues=%s",
        result.passed, n_days, len(week_issues),
    )
    return result.model_dump()
