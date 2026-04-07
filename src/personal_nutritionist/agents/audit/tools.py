import json
import logging

from strands import tool

# Configure logging with basicConfig
logging.basicConfig(
    level=logging.INFO,  # Set the log level to INFO
    # Define log message format
    format="%(asctime)s,p%(process)s,{%(filename)s:%(lineno)d},%(levelname)s,%(message)s",
)
logger = logging.getLogger(__name__)

# check_allergen_conflicts(...)
# check_dislike_conflicts(...)
# check_macro_consistency(...)
# check_budget_feasibility(...)
# check_prep_time_feasibility(...)
# check_plan_variety(...)