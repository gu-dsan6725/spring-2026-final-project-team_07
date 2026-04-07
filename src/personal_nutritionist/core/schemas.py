from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


class Recipe(BaseModel):
    model_config = ConfigDict(extra="forbid")

    title: str

    total_cost: float = Field(..., ge=0)
    cost_per_serving: float = Field(..., ge=0)

    rating: float = Field(..., ge=0, le=5)
    rating_count: int = Field(..., ge=0)

    servings: float = Field(..., gt=0)
    prep_time: int = Field(..., ge=0)
    cook_time: int = Field(..., ge=0)
    total_time: int = Field(..., ge=0)

    num_steps: int = Field(..., ge=0)
    step_length: int = Field(..., ge=0)
    ingredient_count: int = Field(..., ge=0)

    calories: float = Field(..., ge=0)
    protein: float = Field(..., ge=0)
    fat: float = Field(..., ge=0)
    carbs: float = Field(..., ge=0)

    cluster: int
    category: str

class RecipeSearchFilters(BaseModel):
    model_config = ConfigDict(extra="forbid")

    max_cost_per_serving: Optional[float] = Field(default=None, ge=0)
    max_total_time: Optional[int] = Field(default=None, ge=0)
    min_protein: Optional[float] = Field(default=None, ge=0)
    max_calories: Optional[float] = Field(default=None, ge=0)
    min_rating: Optional[float] = Field(default=None, ge=0, le=5)
    min_rating_count: Optional[int] = Field(default=None, ge=0)
    max_ingredient_count: Optional[int] = Field(default=None, ge=0)
    category: Optional[str] = None
    title_contains: Optional[str] = None
    limit: int = Field(default=20, ge=1, le=100)

class UserProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    user_id: str

    goal: Literal["fat_loss", "muscle_gain", "maintenance"]

    weight_lbs: Optional[float] = Field(default=None, gt=0)
    height_in: Optional[float] = Field(default=None, gt=0)
    age: Optional[int] = Field(default=None, gt=0)
    sex: Optional[Literal["male", "female"]] = None

    activity_level: Literal[
        "sedentary",
        "light",
        "moderate",
        "active",
        "very_active",
    ] = "moderate"

    target_calories: Optional[float] = Field(default=None, gt=0)
    target_protein: Optional[float] = Field(default=None, ge=0)

    max_cost_per_serving: Optional[float] = Field(default=None, ge=0)
    max_total_time: Optional[int] = Field(default=None, ge=0)
    max_ingredient_count: Optional[int] = Field(default=None, ge=0)

    preferred_categories: list[str] = Field(default_factory=list)
    disliked_ingredients: list[str] = Field(default_factory=list)
    allergies: list[str] = Field(default_factory=list)

    meals_per_day: int = Field(default=3, ge=1, le=6)