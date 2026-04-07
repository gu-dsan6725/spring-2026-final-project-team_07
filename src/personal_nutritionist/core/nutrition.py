from personal_nutritionist.core.schemas import UserProfile


ACTIVITY_MULTIPLIERS = {
    "sedentary": 1.2,
    "light": 1.375,
    "moderate": 1.55,
    "active": 1.725,
    "very_active": 1.9,
}


def estimate_calorie_target(profile: UserProfile) -> float:
    """
    Estimate a daily calorie target using Mifflin-St Jeor and a simple
    goal-based adjustment.

    Requires:
    - weight_lbs
    - height_in
    - age
    - sex
    - activity_level
    """
    required_fields = {
        "weight_lbs": profile.weight_lbs,
        "height_in": profile.height_in,
        "age": profile.age,
        "sex": profile.sex,
    }
    missing = [name for name, value in required_fields.items() if value is None]
    if missing:
        raise ValueError(f"Missing required fields for calorie estimate: {missing}")

    weight_kg = profile.weight_lbs * 0.453592
    height_cm = profile.height_in * 2.54

    if profile.sex == "male":
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * profile.age + 5
    else:
        bmr = 10 * weight_kg + 6.25 * height_cm - 5 * profile.age - 161

    multiplier = ACTIVITY_MULTIPLIERS[profile.activity_level]
    tdee = bmr * multiplier

    if profile.goal == "fat_loss":
        target = tdee - 500
    elif profile.goal == "muscle_gain":
        target = tdee + 250
    else:
        target = tdee

    return round(max(target, 1200), 0)


def estimate_protein_target(profile: UserProfile) -> float:
    """
    Estimate a daily protein target in grams using simple goal-based rules.
    """
    if profile.weight_lbs is None:
        raise ValueError("Missing required field for protein estimate: weight_lbs")

    if profile.goal == "fat_loss":
        grams_per_lb = 0.9
    elif profile.goal == "muscle_gain":
        grams_per_lb = 1.0
    else:
        grams_per_lb = 0.8

    return round(profile.weight_lbs * grams_per_lb, 0)