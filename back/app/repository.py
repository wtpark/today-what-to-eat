from __future__ import annotations

import json
import sqlite3
from datetime import date, datetime
from typing import Any

from .constants import CONDITION_QUESTIONS


def row_to_dict(row: sqlite3.Row | None) -> dict[str, Any] | None:
    if row is None:
        return None
    return dict(row)


def list_master_ingredients(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM ingredient_master ORDER BY name").fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["aliases"] = json.loads(item.pop("aliases_json"))
        item["common_units"] = json.loads(item.pop("common_units_json"))
        item["source_ids"] = json.loads(item.pop("source_ids_json"))
        item["condition_questions"] = CONDITION_QUESTIONS.get(item["condition_profile"], [])
        result.append(item)
    return result


def get_master(conn: sqlite3.Connection, ingredient_id: str) -> dict[str, Any] | None:
    row = conn.execute("SELECT * FROM ingredient_master WHERE id = ?", (ingredient_id,)).fetchone()
    if not row:
        return None
    item = dict(row)
    item["aliases"] = json.loads(item.pop("aliases_json"))
    item["common_units"] = json.loads(item.pop("common_units_json"))
    item["source_ids"] = json.loads(item.pop("source_ids_json"))
    item["condition_questions"] = CONDITION_QUESTIONS.get(item["condition_profile"], [])
    return item


def list_inventory_raw(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT i.*, m.name AS ingredient_name, m.category, m.perishability_level,
               m.opened_window_days, m.freshness_window_days, m.condition_profile
        FROM inventory i
        JOIN ingredient_master m ON m.id = i.ingredient_id
        ORDER BY i.purchase_date ASC, i.id ASC
        """
    ).fetchall()
    result = []
    for row in rows:
        item = dict(row)
        item["condition_notes"] = json.loads(item.pop("condition_notes_json"))
        result.append(item)
    return result


def get_inventory_item(conn: sqlite3.Connection, inventory_id: int) -> dict[str, Any] | None:
    row = conn.execute(
        """
        SELECT i.*, m.name AS ingredient_name, m.category, m.perishability_level,
               m.opened_window_days, m.freshness_window_days, m.condition_profile
        FROM inventory i
        JOIN ingredient_master m ON m.id = i.ingredient_id
        WHERE i.id = ?
        """,
        (inventory_id,),
    ).fetchone()
    if not row:
        return None
    item = dict(row)
    item["condition_notes"] = json.loads(item.pop("condition_notes_json"))
    return item


def list_seasonings(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    rows = conn.execute("SELECT * FROM seasonings ORDER BY name").fetchall()
    return [dict(row) for row in rows]


def list_recipes(conn: sqlite3.Connection) -> list[dict[str, Any]]:
    recipe_rows = conn.execute("SELECT * FROM recipes WHERE active = 1 ORDER BY name").fetchall()
    recipes = []
    for row in recipe_rows:
        item = dict(row)
        item["tools"] = json.loads(item.pop("tools_json"))
        ingredient_rows = conn.execute(
            """
            SELECT ri.ingredient_id, m.name, ri.role, ri.weight
            FROM recipe_ingredients ri
            JOIN ingredient_master m ON m.id = ri.ingredient_id
            WHERE ri.recipe_id = ?
            ORDER BY CASE ri.role WHEN 'must' THEN 1 WHEN 'core' THEN 2 ELSE 3 END, m.name
            """,
            (item["id"],),
        ).fetchall()
        item["ingredients"] = [dict(r) for r in ingredient_rows]
        seasoning_rows = conn.execute(
            """
            SELECT rs.seasoning_id, s.name, rs.required
            FROM recipe_seasonings rs
            JOIN seasonings s ON s.id = rs.seasoning_id
            WHERE rs.recipe_id = ?
            ORDER BY rs.required DESC, s.name
            """,
            (item["id"],),
        ).fetchall()
        item["seasonings"] = [dict(r) for r in seasoning_rows]
        recipes.append(item)
    return recipes


def list_recent_meals(conn: sqlite3.Connection, limit: int = 50) -> list[dict[str, Any]]:
    rows = conn.execute(
        """
        SELECT mh.*, r.name AS recipe_name
        FROM meal_history mh
        JOIN recipes r ON r.id = mh.recipe_id
        ORDER BY mh.eaten_at DESC
        LIMIT ?
        """,
        (limit,),
    ).fetchall()
    return [dict(row) for row in rows]


def utcish_now_iso(now: datetime) -> str:
    return now.isoformat(timespec="seconds")
