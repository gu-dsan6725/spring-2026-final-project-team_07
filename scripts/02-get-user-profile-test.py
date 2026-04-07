from personal_nutritionist.agents.planning.tools import get_user_profile
from personal_nutritionist.core.schemas import UserProfile

profile_dict = get_user_profile("tyler")
profile = UserProfile(**profile_dict)

print(profile)
print(profile.goal)
print(profile.max_cost_per_serving)