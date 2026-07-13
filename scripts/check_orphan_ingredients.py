from __future__ import annotations

import json
from pathlib import Path

BASE = Path(__file__).resolve().parents[1] / "back"
SEED = BASE / "seed"


def load(name: str):
    return json.loads((SEED / name).read_text(encoding="utf-8"))


def main() -> int:
    ingredients = load("ingredients.json")
    recipes = load("recipes.json")
    substitutions = load("substitutions.json")
    names = {item["id"]: item["name"] for item in ingredients}
    used = {
        item["ingredient_id"]
        for recipe in recipes
        for item in recipe.get("ingredients", [])
    }
    substitute_ids = set()
    for canonical, options in substitutions.get("ingredients", {}).items():
        substitute_ids.add(canonical)
        substitute_ids.update(option["id"] for option in options)
    orphans = sorted(set(names) - used - substitute_ids)
    if orphans:
        print("고아 식재료:", ", ".join(names[item] for item in orphans))
        return 1
    print(f"정상: 식재료 {len(ingredients)}개가 모두 레시피 또는 대체 규칙과 연결되어 있습니다.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
