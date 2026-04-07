"""
Memory operations for the Personal Nutritionist using Mem0.

Thin wrapper around the Mem0 MemoryClient. All agents and tools interact
with memory through these functions — never importing MemoryClient directly.
This keeps the memory backend swappable in one place.

Memory is scoped per user_id. Each stored fact is a plain string so the
LLM can read it naturally. Structured fields (allergies, goal, etc.) are
stored as individual memories so Mem0 can deduplicate and update them.
"""

import logging
import os
from typing import Any

from dotenv import load_dotenv
from mem0 import MemoryClient

load_dotenv()

logger = logging.getLogger(__name__)

_client: MemoryClient | None = None


def _get_client() -> MemoryClient:
    """Return the shared MemoryClient, initializing it on first call."""
    global _client
    if _client is None:
        api_key = os.getenv("MEM0_API_KEY")
        if not api_key:
            raise ValueError(
                "MEM0_API_KEY not set. Add it to your .env file. "
                "Get a free key at https://app.mem0.ai/dashboard"
            )
        _client = MemoryClient(api_key=api_key)
        logger.info("Mem0 MemoryClient initialized")
    return _client


def add_memory(user_id: str, content: str, metadata: dict[str, Any] | None = None) -> dict:
    """
    Store a new memory for the user.

    Use for facts the intake agent collects: goal, allergies, preferences,
    dietary restrictions, budget, etc.

    Args:
        user_id: Unique user identifier.
        content: Plain-text fact to store (e.g. "User is allergic to shellfish").
        metadata: Optional key-value tags (e.g. {"field": "allergy"}).

    Returns:
        Mem0 response dict.
    """
    client = _get_client()
    messages = [{"role": "user", "content": content}]
    kwargs: dict[str, Any] = {"user_id": user_id}
    if metadata:
        kwargs["metadata"] = metadata
    result = client.add(messages, **kwargs)
    logger.info("add_memory user=%s content='%s...'", user_id, content[:60])
    return result


def get_memory(user_id: str) -> list[dict]:
    """
    Retrieve all stored memories for the user.

    Returns:
        List of memory dicts, each with at least a "memory" key.
    """
    client = _get_client()
    memories = client.get_all(user_id=user_id)
    logger.info("get_memory user=%s returned %s memories", user_id, len(memories))
    return memories


def search_memory(user_id: str, query: str, limit: int = 5) -> list[dict]:
    """
    Semantic search over the user's memories.

    Use when the agent needs to recall something specific (e.g. "what are
    this user's allergies?") without loading all memories.

    Args:
        user_id: Unique user identifier.
        query: Natural-language query.
        limit: Max results to return.

    Returns:
        List of relevant memory dicts ranked by relevance.
    """
    client = _get_client()
    response = client.search(query, filters={"user_id": user_id}, limit=limit)
    results = response.get("results", response) if isinstance(response, dict) else response
    logger.info(
        "search_memory user=%s query='%s' returned %s results",
        user_id, query, len(results),
    )
    return results


def delete_memory(memory_id: str) -> dict:
    """
    Delete a specific memory by its Mem0 ID.

    Use when a user explicitly corrects or removes a stored fact.

    Args:
        memory_id: The Mem0 memory ID (from a get_memory or search_memory result).

    Returns:
        Mem0 response dict.
    """
    client = _get_client()
    result = client.delete(memory_id)
    logger.info("delete_memory id=%s", memory_id)
    return result


def profile_from_memories(user_id: str) -> dict:
    """
    Reconstruct a UserProfile-compatible dict from stored memories using
    targeted semantic searches per field.

    Returns a partial dict — only fields with stored memories are included.
    The caller is responsible for supplying defaults for missing fields.
    """
    client = _get_client()

    def _first(query: str) -> str | None:
        response = client.search(query, filters={"user_id": user_id}, limit=1)
        results = response.get("results", response) if isinstance(response, dict) else response
        return results[0].get("memory") if results else None

    def _list_field(query: str) -> list[str]:
        result = _first(query)
        if not result:
            return []
        # Strip common prefixes and split on commas
        for prefix in [
            "User's preferred meal categories are: ",
            "User dislikes these ingredients: ",
            "User is allergic to: ",
        ]:
            if result.startswith(prefix):
                items = result[len(prefix):].rstrip(".")
                return [i.strip() for i in items.split(",") if i.strip()]
        return []

    profile: dict = {"user_id": user_id}

    goal = _first("nutrition goal")
    if goal:
        for g in ("fat_loss", "muscle_gain", "maintenance"):
            if g in goal:
                profile["goal"] = g
                break

    weight = _first("user weighs")
    if weight:
        try:
            profile["weight_lbs"] = float("".join(c for c in weight.split("weighs")[1] if c.isdigit() or c == "."))
        except Exception:
            pass

    height = _first("user height inches")
    if height:
        try:
            profile["height_in"] = float("".join(c for c in height.split("height is")[1] if c.isdigit() or c == "."))
        except Exception:
            pass

    age = _first("user age years old")
    if age:
        try:
            profile["age"] = int("".join(c for c in age.split("is")[1] if c.isdigit()))
        except Exception:
            pass

    sex = _first("user sex")
    if sex:
        for s in ("male", "female"):
            if s in sex:
                profile["sex"] = s
                break

    activity = _first("activity level")
    if activity:
        for level in ("sedentary", "light", "moderate", "active", "very_active"):
            if level in activity:
                profile["activity_level"] = level
                break

    cost = _first("maximum cost per serving")
    if cost:
        try:
            profile["max_cost_per_serving"] = float("".join(c for c in cost if c.isdigit() or c == "."))
        except Exception:
            pass

    time = _first("meals take no more than minutes")
    if time:
        try:
            profile["max_total_time"] = int("".join(c for c in time if c.isdigit()))
        except Exception:
            pass

    ingredients = _first("at most ingredients")
    if ingredients:
        try:
            profile["max_ingredient_count"] = int("".join(c for c in ingredients if c.isdigit()))
        except Exception:
            pass

    meals_per_day = _first("meals per day")
    if meals_per_day:
        try:
            profile["meals_per_day"] = int("".join(c for c in meals_per_day if c.isdigit()))
        except Exception:
            pass

    preferred = _list_field("preferred meal categories")
    if preferred:
        profile["preferred_categories"] = preferred

    dislikes = _list_field("dislikes ingredients")
    if dislikes:
        profile["disliked_ingredients"] = dislikes

    allergies = _list_field("allergic to")
    if allergies:
        profile["allergies"] = allergies

    logger.info("profile_from_memories user=%s fields=%s", user_id, list(profile.keys()))
    return profile


def delete_all_memories(user_id: str) -> dict:
    """
    Delete all memories for a user.

    Use for testing or when a user wants to reset their profile.

    Args:
        user_id: Unique user identifier.

    Returns:
        Mem0 response dict.
    """
    client = _get_client()
    result = client.delete_all(user_id=user_id)
    logger.info("delete_all_memories user=%s", user_id)
    return result
