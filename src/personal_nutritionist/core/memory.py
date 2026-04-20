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
    response = client.get_all(filters={"user_id": user_id})
    memories = response.get("results", response) if isinstance(response, dict) else response
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
    Reconstruct a UserProfile-compatible dict from stored memories.

    Reads structured values from metadata["value"] — set by the intake tools
    on every write. Falls back to text parsing for any legacy memories that
    predate the metadata approach.

    Returns a partial dict — only fields with stored memories are included.
    The caller is responsible for supplying defaults for missing fields.
    """
    memories = get_memory(user_id)
    profile: dict = {"user_id": user_id}

    # Fields that UserProfile expects as list[str] — Mem0 serializes these back
    # as plain strings even when we stored a list, so we re-split on commas.
    _LIST_FIELDS = {"allergies", "disliked_ingredients", "preferred_categories"}

    # --- primary path: read exact values stored in metadata ---
    for m in memories:
        meta = m.get("metadata") or {}
        field = meta.get("field")
        value = meta.get("value")
        if field and value is not None:
            if field in _LIST_FIELDS and isinstance(value, str):
                value = [v.strip() for v in value.split(",") if v.strip()]
            profile[field] = value

    # --- fallback: text parsing for memories without metadata values ---
    text_memories = [
        m.get("memory", "")
        for m in memories
        if not (m.get("metadata") or {}).get("value")
    ]

    def _search_text(keyword: str) -> str | None:
        for t in text_memories:
            if keyword.lower() in t.lower():
                return t
        return None

    if "goal" not in profile:
        hit = _search_text("goal")
        if hit:
            for g in ("fat_loss", "muscle_gain", "maintenance"):
                if g in hit:
                    profile["goal"] = g
                    break

    if "weight_lbs" not in profile:
        hit = _search_text("weighs")
        if hit:
            try:
                profile["weight_lbs"] = float("".join(c for c in hit.split("weighs")[1] if c.isdigit() or c == "."))
            except Exception:
                pass

    if "height_in" not in profile:
        hit = _search_text("height")
        if hit:
            try:
                profile["height_in"] = float("".join(c for c in hit.split("height")[1] if c.isdigit() or c == "."))
            except Exception:
                pass

    if "age" not in profile:
        hit = _search_text("years old")
        if hit:
            try:
                import re
                m = re.search(r"(\d+)\s*years old", hit)
                if m:
                    profile["age"] = int(m.group(1))
            except Exception:
                pass

    if "sex" not in profile:
        hit = _search_text("sex")
        if hit:
            for s in ("male", "female"):
                if s in hit.lower():
                    profile["sex"] = s
                    break

    if "activity_level" not in profile:
        hit = _search_text("activity")
        if hit:
            for level in ("sedentary", "light", "moderate", "active", "very_active"):
                if level in hit.lower():
                    profile["activity_level"] = level
                    break

    if "max_cost_per_serving" not in profile:
        hit = _search_text("cost per serving")
        if hit:
            try:
                import re
                m = re.search(r"\$?([\d.]+)", hit)
                if m:
                    profile["max_cost_per_serving"] = float(m.group(1))
            except Exception:
                pass

    if "max_total_time" not in profile:
        hit = _search_text("minutes")
        if hit:
            try:
                import re
                m = re.search(r"(\d+)\s*minutes", hit)
                if m:
                    profile["max_total_time"] = int(m.group(1))
            except Exception:
                pass

    if "meals_per_day" not in profile:
        hit = _search_text("meals per day")
        if hit:
            try:
                import re
                m = re.search(r"(\d+)\s*meals per day", hit)
                if m:
                    profile["meals_per_day"] = int(m.group(1))
            except Exception:
                pass

    logger.info("profile_from_memories user=%s fields=%s", user_id, list(profile.keys()))
    return profile


def replace_memory_field(
    user_id: str,
    field: str,
    content: str,
    value,
) -> dict:
    """
    Replace any existing memory for a given metadata field, then write the new one.
    Use instead of add_memory for fields that should have exactly one value (e.g. allergies).
    If value is an empty list or None, only deletes — does not write a new memory.
    """
    memories = get_memory(user_id)
    for m in memories:
        if (m.get("metadata") or {}).get("field") == field:
            try:
                delete_memory(m["id"])
            except Exception:
                pass

    is_empty = value is None or value == [] or value == ""
    if is_empty:
        logger.info("replace_memory_field user=%s field=%s — cleared", user_id, field)
        return {"status": "cleared"}

    result = add_memory(user_id, content, metadata={"field": field, "value": value})
    logger.info("replace_memory_field user=%s field=%s value=%s", user_id, field, value)
    return result


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
