from __future__ import annotations

import json
import os
import sqlite3
from contextlib import contextmanager
from pathlib import Path
from typing import Iterator

BASE_DIR = Path(__file__).resolve().parents[1]
DEFAULT_DB_PATH = BASE_DIR / "data" / "today_menu.db"
SCHEMA_PATH = BASE_DIR / "sql" / "schema.sql"
SEED_DIR = BASE_DIR / "seed"
SEED_VERSION = "2026-07-14-final-fixed2"


def get_db_path() -> Path:
    path = Path(os.getenv("DB_PATH", str(DEFAULT_DB_PATH)))
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def connect() -> sqlite3.Connection:
    conn = sqlite3.connect(get_db_path(), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA synchronous = NORMAL")
    conn.execute("PRAGMA busy_timeout = 5000")
    return conn


@contextmanager
def db_connection() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        yield conn
    finally:
        conn.close()


@contextmanager
def db_transaction() -> Iterator[sqlite3.Connection]:
    conn = connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _load_json(filename: str):
    return json.loads((SEED_DIR / filename).read_text(encoding="utf-8"))


def _validate_seed_data() -> None:
    ingredients = _load_json("ingredients.json")
    seasonings = _load_json("seasonings.json")
    recipes = _load_json("recipes.json")
    substitutions = _load_json("substitutions.json")

    def ensure_unique(items: list[dict], label: str) -> None:
        ids = [item["id"] for item in items]
        names = [item["name"] for item in items]
        if len(ids) != len(set(ids)):
            raise ValueError(f"{label} ID가 중복되었습니다.")
        if len(names) != len(set(names)):
            raise ValueError(f"{label} 이름이 중복되었습니다.")

    ensure_unique(ingredients, "식재료")
    ensure_unique(seasonings, "양념")
    ensure_unique(recipes, "레시피")

    alias_owner: dict[str, str] = {}
    for item in ingredients:
        if int(item.get("freshness_window_days", 0)) < 1:
            raise ValueError(f"식재료 '{item['name']}'의 freshness_window_days가 올바르지 않습니다.")
        for alias in [item["name"], *item.get("aliases", [])]:
            owner = alias_owner.get(alias)
            if owner and owner != item["id"]:
                raise ValueError(f"식재료 별칭 '{alias}'가 여러 항목에 중복되었습니다.")
            alias_owner[alias] = item["id"]

    ingredient_ids = {item["id"] for item in ingredients}
    seasoning_ids = {item["id"] for item in seasonings}
    used_ingredient_ids: set[str] = set()
    for recipe in recipes:
        for item in recipe.get("ingredients", []):
            if item["ingredient_id"] not in ingredient_ids:
                raise ValueError(
                    f"레시피 '{recipe['name']}'가 없는 식재료 ID '{item['ingredient_id']}'를 참조합니다."
                )
            used_ingredient_ids.add(item["ingredient_id"])
        for item in recipe.get("seasonings", []):
            if item["seasoning_id"] not in seasoning_ids:
                raise ValueError(
                    f"레시피 '{recipe['name']}'가 없는 양념 ID '{item['seasoning_id']}'를 참조합니다."
                )

        tools = recipe.get("tools", [])
        if not isinstance(tools, list):
            raise ValueError(f"레시피 '{recipe['name']}'의 tools는 목록이어야 합니다.")
        for requirement in tools:
            if isinstance(requirement, str):
                if not requirement.strip():
                    raise ValueError(f"레시피 '{recipe['name']}'에 빈 조리기구가 있습니다.")
            elif isinstance(requirement, list):
                if not requirement or not all(isinstance(x, str) and x.strip() for x in requirement):
                    raise ValueError(f"레시피 '{recipe['name']}'의 대체 조리기구 그룹이 잘못되었습니다.")
            else:
                raise ValueError(f"레시피 '{recipe['name']}'의 조리기구 형식이 잘못되었습니다.")

    substitution_ingredient_ids: set[str] = set()
    for canonical, options in substitutions.get("ingredients", {}).items():
        if canonical not in ingredient_ids:
            raise ValueError(f"재료 대체 기준 ID '{canonical}'가 마스터에 없습니다.")
        substitution_ingredient_ids.add(canonical)
        for option in options:
            if option["id"] not in ingredient_ids:
                raise ValueError(f"재료 대체 ID '{option['id']}'가 마스터에 없습니다.")
            substitution_ingredient_ids.add(option["id"])
    for canonical, options in substitutions.get("seasonings", {}).items():
        if canonical not in seasoning_ids:
            raise ValueError(f"양념 대체 기준 ID '{canonical}'가 마스터에 없습니다.")
        for option in options:
            if option["id"] not in seasoning_ids:
                raise ValueError(f"양념 대체 ID '{option['id']}'가 마스터에 없습니다.")

    orphan_ids = sorted(ingredient_ids - used_ingredient_ids - substitution_ingredient_ids)
    if orphan_ids:
        orphan_names = [item["name"] for item in ingredients if item["id"] in orphan_ids]
        raise ValueError(
            "어떤 레시피나 대체 규칙에서도 사용되지 않는 고아 식재료가 있습니다: "
            + ", ".join(orphan_names)
        )

    meal_types = {item["meal_type"] for item in recipes}
    if "샐러드·가벼운 식사" not in meal_types:
        raise ValueError("샐러드·가벼운 식사 레시피가 최소 1개 필요합니다.")
    if not any(int(item["cook_time"]) <= 5 for item in recipes):
        raise ValueError("5분 이내 레시피가 최소 1개 필요합니다.")


def _column_names(conn: sqlite3.Connection, table: str) -> set[str]:
    return {row[1] for row in conn.execute(f"PRAGMA table_info({table})").fetchall()}


def _apply_schema_migrations(conn: sqlite3.Connection) -> None:
    ingredient_columns = _column_names(conn, "ingredient_master")
    if "freshness_window_days" not in ingredient_columns:
        conn.execute(
            "ALTER TABLE ingredient_master ADD COLUMN freshness_window_days INTEGER NOT NULL DEFAULT 14"
        )

    recipe_columns = _column_names(conn, "recipes")
    if "active" not in recipe_columns:
        conn.execute("ALTER TABLE recipes ADD COLUMN active INTEGER NOT NULL DEFAULT 1")


def initialize_database() -> None:
    _validate_seed_data()
    schema = SCHEMA_PATH.read_text(encoding="utf-8")
    with db_transaction() as conn:
        conn.executescript(schema)
        _apply_schema_migrations(conn)
        _seed_ingredients(conn)
        _seed_seasonings(conn)
        _seed_recipes(conn)
        _prune_removed_seed_rows(conn)
        conn.execute(
            """
            INSERT INTO seed_meta(key, value, updated_at)
            VALUES('seed_version', ?, CURRENT_TIMESTAMP)
            ON CONFLICT(key) DO UPDATE SET
                value=excluded.value,
                updated_at=CURRENT_TIMESTAMP
            """,
            (SEED_VERSION,),
        )


def _prune_removed_seed_rows(conn: sqlite3.Connection) -> None:
    ingredient_ids = [item["id"] for item in _load_json("ingredients.json")]
    seasoning_ids = [item["id"] for item in _load_json("seasonings.json")]

    ingredient_marks = ",".join("?" for _ in ingredient_ids)
    conn.execute(
        f"""
        DELETE FROM ingredient_master
        WHERE id NOT IN ({ingredient_marks})
          AND NOT EXISTS (SELECT 1 FROM inventory i WHERE i.ingredient_id = ingredient_master.id)
          AND NOT EXISTS (SELECT 1 FROM recipe_ingredients ri WHERE ri.ingredient_id = ingredient_master.id)
        """,
        ingredient_ids,
    )

    seasoning_marks = ",".join("?" for _ in seasoning_ids)
    conn.execute(
        f"""
        DELETE FROM seasonings
        WHERE id NOT IN ({seasoning_marks})
          AND NOT EXISTS (SELECT 1 FROM recipe_seasonings rs WHERE rs.seasoning_id = seasonings.id)
        """,
        seasoning_ids,
    )

def _seed_ingredients(conn: sqlite3.Connection) -> None:
    for item in _load_json("ingredients.json"):
        conn.execute(
            """
            INSERT INTO ingredient_master(
                id, name, aliases_json, category, default_storage,
                perishability_level, opened_window_days, freshness_window_days, condition_profile,
                common_units_json, source_ids_json, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                aliases_json=excluded.aliases_json,
                category=excluded.category,
                default_storage=excluded.default_storage,
                perishability_level=excluded.perishability_level,
                opened_window_days=excluded.opened_window_days,
                freshness_window_days=excluded.freshness_window_days,
                condition_profile=excluded.condition_profile,
                common_units_json=excluded.common_units_json,
                source_ids_json=excluded.source_ids_json,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                item["id"], item["name"], json.dumps(item.get("aliases", []), ensure_ascii=False),
                item["category"], item["default_storage"], item["perishability_level"],
                item["opened_window_days"], item.get("freshness_window_days", 14), item["condition_profile"],
                json.dumps(item.get("common_units", []), ensure_ascii=False),
                json.dumps(item.get("source_ids", []), ensure_ascii=False),
            ),
        )


def _seed_seasonings(conn: sqlite3.Connection) -> None:
    for item in _load_json("seasonings.json"):
        conn.execute(
            """
            INSERT INTO seasonings(id, name, owned, default_owned, updated_at)
            VALUES (?, ?, ?, ?, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                default_owned=excluded.default_owned,
                updated_at=CURRENT_TIMESTAMP
            """,
            (item["id"], item["name"], int(item.get("default_owned", False)), int(item.get("default_owned", False))),
        )


def _seed_recipes(conn: sqlite3.Connection) -> None:
    for item in _load_json("recipes.json"):
        conn.execute(
            """
            INSERT INTO recipes(
                id, name, cuisine, meal_type, cooking_method, cook_time,
                tools_json, min_core_count, image_path, source, source_recipe_id, active, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, CURRENT_TIMESTAMP)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                cuisine=excluded.cuisine,
                meal_type=excluded.meal_type,
                cooking_method=excluded.cooking_method,
                cook_time=excluded.cook_time,
                tools_json=excluded.tools_json,
                min_core_count=excluded.min_core_count,
                image_path=excluded.image_path,
                source=excluded.source,
                source_recipe_id=excluded.source_recipe_id,
                active=1,
                updated_at=CURRENT_TIMESTAMP
            """,
            (
                item["id"], item["name"], item["cuisine"], item["meal_type"],
                item["cooking_method"], item["cook_time"],
                json.dumps(item.get("tools", []), ensure_ascii=False),
                item.get("min_core_count", 0), item.get("image_path"),
                item.get("source", ""), item.get("source_recipe_id", item["id"]),
            ),
        )
        conn.execute("DELETE FROM recipe_ingredients WHERE recipe_id = ?", (item["id"],))
        conn.execute("DELETE FROM recipe_seasonings WHERE recipe_id = ?", (item["id"],))
        for ingredient in item.get("ingredients", []):
            conn.execute(
                """
                INSERT INTO recipe_ingredients(recipe_id, ingredient_id, role, weight)
                VALUES (?, ?, ?, ?)
                """,
                (item["id"], ingredient["ingredient_id"], ingredient["role"], ingredient.get("weight", 1)),
            )
        for seasoning in item.get("seasonings", []):
            conn.execute(
                """
                INSERT INTO recipe_seasonings(recipe_id, seasoning_id, required)
                VALUES (?, ?, ?)
                """,
                (item["id"], seasoning["seasoning_id"], int(seasoning.get("required", True))),
            )

    recipe_ids = [item["id"] for item in _load_json("recipes.json")]
    marks = ",".join("?" for _ in recipe_ids)
    conn.execute(f"UPDATE recipes SET active = 0, updated_at = CURRENT_TIMESTAMP WHERE id NOT IN ({marks})", recipe_ids)
