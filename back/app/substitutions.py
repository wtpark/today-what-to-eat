from __future__ import annotations

import json
from pathlib import Path
from typing import Any

SEED_DIR = Path(__file__).resolve().parents[1] / "seed"
SUBSTITUTION_PATH = SEED_DIR / "substitutions.json"


def _load() -> dict[str, Any]:
    return json.loads(SUBSTITUTION_PATH.read_text(encoding="utf-8"))


_DATA = _load()
INGREDIENT_SUBSTITUTIONS: dict[str, list[dict[str, Any]]] = _DATA.get("ingredients", {})
SEASONING_SUBSTITUTIONS: dict[str, list[dict[str, Any]]] = _DATA.get("seasonings", {})


def _allowed_in_context(option: dict[str, Any], recipe: dict[str, Any] | None) -> bool:
    if not recipe:
        return True
    allowed_methods = option.get("allowed_cooking_methods")
    if allowed_methods and recipe.get("cooking_method") not in allowed_methods:
        return False
    excluded_methods = option.get("excluded_cooking_methods", [])
    if recipe.get("cooking_method") in excluded_methods:
        return False
    allowed_meal_types = option.get("allowed_meal_types")
    if allowed_meal_types and recipe.get("meal_type") not in allowed_meal_types:
        return False
    if recipe.get("meal_type") in option.get("excluded_meal_types", []):
        return False
    allowed_cuisines = option.get("allowed_cuisines")
    if allowed_cuisines and recipe.get("cuisine") not in allowed_cuisines:
        return False
    return True


def _candidates(
    required_id: str,
    mapping: dict[str, list[dict[str, Any]]],
    recipe: dict[str, Any] | None = None,
) -> list[dict[str, Any]]:
    result = [{"id": required_id, "quality": 1.0, "tier": "exact", "warning": None}]
    for raw in mapping.get(required_id, []):
        if not _allowed_in_context(raw, recipe):
            continue
        result.append(
            {
                "id": raw["id"],
                "quality": float(raw.get("quality", 0.8)),
                "tier": raw.get("tier", "equivalent"),
                "warning": raw.get("warning"),
            }
        )
    return result


def ingredient_candidates(required_id: str, recipe: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _candidates(required_id, INGREDIENT_SUBSTITUTIONS, recipe)


def seasoning_candidates(required_id: str, recipe: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    return _candidates(required_id, SEASONING_SUBSTITUTIONS, recipe)


def allowed_actual_ingredient_ids(recipe_ingredient_ids: set[str]) -> set[str]:
    allowed: set[str] = set()
    for ingredient_id in recipe_ingredient_ids:
        # Completion validation is intentionally broad because the selected recommendation
        # already contains the context-filtered actual inventory IDs.
        allowed.update(item["id"] for item in _candidates(ingredient_id, INGREDIENT_SUBSTITUTIONS))
    return allowed
