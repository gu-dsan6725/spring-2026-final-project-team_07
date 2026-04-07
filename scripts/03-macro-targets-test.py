from personal_nutritionist.agents.planning.tools import (
    get_user_profile,
    estimate_calorie_target,
    estimate_protein_target,
)

profile = get_user_profile("tyler")

calories = estimate_calorie_target(profile)
protein = estimate_protein_target(profile)

print("Profile:", profile)
print("Calories:", calories)
print("Protein:", protein)