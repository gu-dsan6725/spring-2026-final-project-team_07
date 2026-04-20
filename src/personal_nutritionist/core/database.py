import json
import os
import sqlite3
from pathlib import Path

_DB_PATH = Path(os.getenv("COOKBOOK_DB", "data/cookbook.db"))


def _connect() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(_DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def _init_db() -> None:
    with _connect() as conn:
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS excluded_recipes (
                user_id TEXT NOT NULL,
                title   TEXT NOT NULL,
                PRIMARY KEY (user_id, title)
            );
            CREATE TABLE IF NOT EXISTS custom_recipes (
                user_id     TEXT NOT NULL,
                title       TEXT NOT NULL,
                recipe_json TEXT NOT NULL,
                PRIMARY KEY (user_id, title)
            );
        """)


_init_db()


# ── Exclusions ─────────────────────────────────────────────────────────────────

def remove_from_cookbook(user_id: str, title: str) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO excluded_recipes (user_id, title) VALUES (?, ?)",
            (user_id, title),
        )


def restore_to_cookbook(user_id: str, title: str) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM excluded_recipes WHERE user_id = ? AND title = ?",
            (user_id, title),
        )


def get_excluded(user_id: str) -> set[str]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT title FROM excluded_recipes WHERE user_id = ?", (user_id,)
        ).fetchall()
    return {row["title"] for row in rows}


def remove_all_from_cookbook(user_id: str, titles: list[str]) -> None:
    with _connect() as conn:
        conn.executemany(
            "INSERT OR IGNORE INTO excluded_recipes (user_id, title) VALUES (?, ?)",
            [(user_id, t) for t in titles],
        )


def restore_all_to_cookbook(user_id: str) -> None:
    with _connect() as conn:
        conn.execute("DELETE FROM excluded_recipes WHERE user_id = ?", (user_id,))


# ── Custom recipes ─────────────────────────────────────────────────────────────

def add_custom_recipe(user_id: str, recipe: dict) -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO custom_recipes (user_id, title, recipe_json) VALUES (?, ?, ?)",
            (user_id, recipe["title"], json.dumps(recipe)),
        )


def edit_custom_recipe(user_id: str, title: str, updates: dict) -> bool:
    """Update fields on an existing custom recipe. Returns False if not found."""
    with _connect() as conn:
        row = conn.execute(
            "SELECT recipe_json FROM custom_recipes WHERE user_id = ? AND title = ?",
            (user_id, title),
        ).fetchone()
        if row is None:
            return False
        recipe = json.loads(row["recipe_json"])
        recipe.update({k: v for k, v in updates.items() if v is not None})
        recipe["title"] = updates.get("title", recipe["title"])
        new_title = recipe["title"]
        conn.execute(
            "DELETE FROM custom_recipes WHERE user_id = ? AND title = ?",
            (user_id, title),
        )
        conn.execute(
            "INSERT INTO custom_recipes (user_id, title, recipe_json) VALUES (?, ?, ?)",
            (user_id, new_title, json.dumps(recipe)),
        )
    return True


def remove_custom_recipe(user_id: str, title: str) -> None:
    with _connect() as conn:
        conn.execute(
            "DELETE FROM custom_recipes WHERE user_id = ? AND title = ?",
            (user_id, title),
        )


def get_custom_recipes(user_id: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT recipe_json FROM custom_recipes WHERE user_id = ?", (user_id,)
        ).fetchall()
    return [json.loads(row["recipe_json"]) for row in rows]
