from __future__ import annotations

from typing import Literal, Optional
from pydantic import BaseModel, Field, ConfigDict


FloorType = Literal["combat", "puzzle", "rest"]


class Reward(BaseModel):
    model_config = ConfigDict(extra="forbid")

    gold: int = Field(default=0, ge=0)


class FailurePenalty(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hp_loss: int = Field(default=0, ge=0)


class Enemy(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    description: str
    hp: int = Field(gt=0)
    attack_bonus: int
    damage: str
    behavior: str
    reward: Reward


class Puzzle(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    type: str
    prompt: str
    answer: str
    max_attempts: int = Field(gt=0)
    success_reward: Reward
    failure_penalty: FailurePenalty


class FloorTemplate(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    floor_type: FloorType
    description_template: str
    weight: int = Field(gt=0)

    # combat-only
    enemy_pool: list[str] = Field(default_factory=list)

    # puzzle-only
    puzzle_pool: list[str] = Field(default_factory=list)

    # rest-only
    heal_amount: Optional[int] = Field(default=None, ge=0)


class Event(BaseModel):
    model_config = ConfigDict(extra="forbid")

    turn: int = Field(ge=0)
    kind: str
    payload: dict


class PartyState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    hp: int = Field(ge=0)
    max_hp: int = Field(gt=0)
    gold: int = Field(default=0, ge=0)
    inventory: list[str] = Field(default_factory=list)
    statuses: list[str] = Field(default_factory=list)


class EncounterState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    floor_id: str
    floor_type: FloorType
    description: str

    enemy: Optional[Enemy] = None
    puzzle: Optional[Puzzle] = None

    attempts_left: Optional[int] = Field(default=None, ge=0)
    heal_amount: Optional[int] = Field(default=None, ge=0)


class RunState(BaseModel):
    model_config = ConfigDict(extra="forbid")

    run_id: str
    seed: int
    floor_number: int = Field(ge=1)
    turn: int = Field(default=0, ge=0)

    party: PartyState
    encounter: EncounterState
    log: list[Event] = Field(default_factory=list)