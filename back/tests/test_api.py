from __future__ import annotations

import json
import os
from datetime import date
from pathlib import Path

os.environ["DB_PATH"] = str(Path(__file__).parent / "test_today_menu.db")

from fastapi.testclient import TestClient

from app.main import app
from app.scoring import enrich_inventory_priority, recommend

SEED_DIR = Path(__file__).parents[1] / "seed"
INGREDIENT_SEED = json.loads((SEED_DIR / "ingredients.json").read_text(encoding="utf-8"))
RECIPE_SEED = json.loads((SEED_DIR / "recipes.json").read_text(encoding="utf-8"))
SEASONING_SEED = json.loads((SEED_DIR / "seasonings.json").read_text(encoding="utf-8"))
EXPECTED_INGREDIENTS = len(INGREDIENT_SEED)
EXPECTED_RECIPES = len(RECIPE_SEED)


def setup_module():
    path = Path(os.environ["DB_PATH"])
    for suffix in ("", "-wal", "-shm"):
        candidate = Path(str(path) + suffix)
        if candidate.exists():
            candidate.unlink()


def recommendation_payload(**overrides):
    payload = {
        "preferred_cuisine": "상관없음",
        "cuisine_preference_strength": "priority",
        "preferred_meal_type": "상관없음",
        "previous_meal_cuisine": "입력하지 않음",
        "previous_meal_type": "입력하지 않음",
        "previous_meal_avoidance": "soft",
        "max_cooking_minutes": 30,
        "appliances": ["냄비", "프라이팬", "에어프라이어"],
        "recommendation_mode": "balanced",
        "repeat_avoidance": "medium",
        "temporary_owned_seasoning_ids": [],
        "excluded_ingredient_ids": [],
        "allow_substitutions": True,
    }
    payload.update(overrides)
    return payload


def test_full_flow_and_catalog_balance():
    with TestClient(app) as client:
        health = client.get("/health")
        assert health.status_code == 200
        assert health.json()["master_ingredients"] == EXPECTED_INGREDIENTS
        assert health.json()["recipes"] == EXPECTED_RECIPES
        assert health.json()["seed_version"].endswith("final")

        catalog = client.get("/catalog/summary").json()
        assert sum(catalog["recipes_by_cuisine"].values()) == EXPECTED_RECIPES
        assert catalog["recipes_by_meal_type"]["샐러드·가벼운 식사"] >= 4

        empty = client.post("/recommend", json=recommendation_payload())
        assert empty.status_code == 200
        assert empty.json()["status"] == "empty_inventory"

        demo = client.post(
            "/demo/load",
            json={"only_when_empty": True, "profile": "balanced", "load_balanced_pantry": True},
        )
        assert demo.status_code == 201

        inventory = client.get("/ingredients").json()
        assert inventory["summary"]["total"] >= 15
        assert "recommendation_excluded" in inventory["summary"]
        assert all("priority_score" in item and "ranking_priority_score" in item for item in inventory["items"])

        editable = inventory["items"][0]
        updated = client.put(
            f"/ingredients/{editable['id']}",
            json={"storage": "냉동", "purchase_date": "2026-07-01"},
        )
        assert updated.status_code == 200
        assert updated.json()["item"]["storage"] == "냉동"

        seasonings = client.get("/seasonings").json()
        owned_ids = [item["id"] for item in seasonings if item["owned"]]
        western = client.post(
            "/recommend",
            json=recommendation_payload(
                preferred_cuisine="양식",
                cuisine_preference_strength="strict",
                previous_meal_cuisine="한식",
                previous_meal_type="국·찌개",
                previous_meal_avoidance="exclude_cuisine",
                temporary_owned_seasoning_ids=owned_ids,
            ),
        )
        body = western.json()
        assert western.status_code == 200
        assert body["status"] == "ok"
        assert body["preferred_direct_results"] or body["preferred_one_more_results"]
        assert not body["alternative_results"]

        recipe = (body["preferred_direct_results"] or body["direct_results"])[0]
        empty_usage = client.post(
            "/meals/complete",
            json={
                "recipe_id": recipe["recipe_id"],
                "eaten_at": "2026-07-13T19:20:00+09:00",
                "meal_slot": "저녁",
                "usage": [],
            },
        )
        assert empty_usage.status_code == 422

        zero_usage = [
            {"inventory_id": lot["inventory_id"], "remaining_quantity": lot["quantity"]}
            for lot in recipe["matched_inventory"]
        ]
        assert client.post(
            "/meals/complete",
            json={
                "recipe_id": recipe["recipe_id"],
                "eaten_at": "2026-07-13T19:25:00+09:00",
                "meal_slot": "저녁",
                "usage": zero_usage,
            },
        ).status_code == 400

        positive_usage = list(zero_usage)
        positive_usage[0] = dict(positive_usage[0], remaining_quantity=0)
        complete = client.post(
            "/meals/complete",
            json={
                "recipe_id": recipe["recipe_id"],
                "eaten_at": "2026-07-13T19:30:00+09:00",
                "meal_slot": "저녁",
                "usage": positive_usage,
                "note": "테스트",
            },
        )
        assert complete.status_code == 201
        assert any(item["used_quantity"] > 0 for item in complete.json()["usage"])


def test_seed_catalog_has_quick_and_light_meals_and_no_alias_conflicts():
    with TestClient(app) as client:
        catalog = client.get("/catalog/summary").json()
        assert catalog["recipes_by_meal_type"]["샐러드·가벼운 식사"] >= 4
        names = [name for group in catalog["recipe_names_by_cuisine"].values() for name in group]
        for expected in ["떡볶이", "군만두", "계란찜", "초간단 물냉면", "참치 양배추 샐러드", "잡채", "레몬 연어 스테이크", "아보카도 에그 토스트"]:
            assert expected in names

    aliases: dict[str, str] = {}
    for item in INGREDIENT_SEED:
        for alias in [item["name"], *item.get("aliases", [])]:
            assert alias not in aliases, f"duplicate alias {alias}: {aliases.get(alias)} and {item['id']}"
            aliases[alias] = item["id"]


def test_previous_meal_exclusion_and_exact_meal_type_groups():
    with TestClient(app) as client:
        if client.get("/ingredients").json()["summary"]["total"] == 0:
            client.post("/demo/load", json={"only_when_empty": True, "profile": "balanced", "load_balanced_pantry": True})
        owned_ids = [x["id"] for x in client.get("/seasonings").json() if x["owned"]]
        response = client.post(
            "/recommend",
            json=recommendation_payload(
                preferred_cuisine="중식",
                preferred_meal_type="볶음·구이",
                previous_meal_cuisine="중식",
                previous_meal_type="밥·덮밥",
                previous_meal_avoidance="exclude_cuisine",
                temporary_owned_seasoning_ids=owned_ids,
            ),
        )
        body = response.json()
        assert body["request_summary"]["previous_meal_avoidance"] == "같은 음식 계열 제외"
        assert body.get("preferred_direct_results", []) == []
        assert all(x["meal_type"] == "볶음·구이" for x in body.get("alternative_exact_results", []))

        recipe_type_by_name = {recipe["name"]: recipe["meal_type"] for recipe in RECIPE_SEED}
        for suggestion in body.get("diagnostics", {}).get("unlock_suggestions", []):
            assert suggestion["recipe_names"]
            assert all(recipe_type_by_name[name] == "볶음·구이" for name in suggestion["recipe_names"])


def test_priority_rules_freshness_frozen_and_same_day_fifo():
    base = {
        "ingredient_id": "cabbage",
        "ingredient_name": "양배추",
        "category": "leafy_vegetable",
        "perishability_level": 3,
        "opened_window_days": 7,
        "freshness_window_days": 7,
        "condition_profile": "vegetable_leafy",
        "detail_name": "",
        "quantity": 1,
        "unit": "통",
        "purchase_date": "2026-07-07",
        "expiry_date": None,
        "opened": 0,
        "opened_date": None,
        "priority_override": 0,
        "condition_status": "normal",
        "condition_notes": [],
        "note": "",
    }
    refrigerated = dict(base, id=1001, storage="냉장")
    frozen = dict(base, id=1002, storage="냉동")
    override = dict(base, id=1003, storage="냉장", purchase_date="2026-07-14", priority_override=1)
    same_day = dict(base, id=1004, storage="냉장")
    scored = enrich_inventory_priority([refrigerated, frozen, override, same_day], today=date(2026, 7, 14))
    by_id = {item["id"]: item for item in scored}
    assert by_id[1002]["priority_score"] < by_id[1001]["priority_score"]
    assert by_id[1001]["freshness_due"] is True
    assert by_id[1001]["action"] == "먼저 사용"
    assert by_id[1003]["ranking_priority_score"] == 100
    assert by_id[1001]["priority_breakdown"]["선입선출·구매 경과"] == by_id[1004]["priority_breakdown"]["선입선출·구매 경과"]


def test_no_orphans_missing_core_units_and_context_substitution():
    substitutions = json.loads((SEED_DIR / "substitutions.json").read_text(encoding="utf-8"))
    ingredient_ids = {item["id"] for item in INGREDIENT_SEED}
    used_ids = {i["ingredient_id"] for recipe in RECIPE_SEED for i in recipe.get("ingredients", [])}
    substitute_ids = set()
    for canonical, options in substitutions.get("ingredients", {}).items():
        substitute_ids.add(canonical)
        substitute_ids.update(option["id"] for option in options)
    assert ingredient_ids - used_ids - substitute_ids == set()

    master = {item["id"]: item for item in INGREDIENT_SEED}
    def lot(ingredient_id: str, lot_id: int):
        m = master[ingredient_id]
        return {
            "id": lot_id,
            "ingredient_id": ingredient_id,
            "ingredient_name": m["name"],
            "category": m["category"],
            "perishability_level": m["perishability_level"],
            "opened_window_days": m["opened_window_days"],
            "freshness_window_days": m["freshness_window_days"],
            "condition_profile": m["condition_profile"],
            "detail_name": "",
            "quantity": 1,
            "unit": m.get("common_units", ["개"])[0],
            "storage": m["default_storage"],
            "purchase_date": date.today().isoformat(),
            "expiry_date": None,
            "opened": 0,
            "opened_date": None,
            "priority_override": 0,
            "condition_status": "normal",
            "condition_notes": [],
            "note": "",
        }

    all_owned = [dict(item, owned=1) for item in SEASONING_SEED]
    seasoning_names = {item["id"]: item["name"] for item in SEASONING_SEED}

    def hydrated_recipe(recipe_id: str):
        raw = next(dict(r) for r in RECIPE_SEED if r["id"] == recipe_id)
        raw["ingredients"] = [
            {**item, "name": master[item["ingredient_id"]]["name"]}
            for item in raw.get("ingredients", [])
        ]
        raw["seasonings"] = [
            {**item, "name": seasoning_names[item["seasoning_id"]]}
            for item in raw.get("seasonings", [])
        ]
        return raw

    # Noodle exists, but the recipe requires two core options; it must not appear in one-more.
    chow_result = recommend(
        [lot("chinese_noodle", 1)], all_owned,
        [hydrated_recipe("cn_chow_mein")], [],
        recommendation_payload(preferred_cuisine="중식", appliances=["프라이팬"], temporary_owned_seasoning_ids=[x["id"] for x in SEASONING_SEED]),
    )
    all_one_more = chow_result.get("one_more_results", [])
    assert all(item["recipe_id"] != "cn_chow_mein" for item in all_one_more)

    # Tomato sauce must not stand in for fresh tomato in a salad.
    salad_result = recommend(
        [lot("tofu", 10), lot("cabbage", 11), lot("tomato_sauce", 12)], all_owned,
        [hydrated_recipe("lt_tofu_salad")], [],
        recommendation_payload(preferred_cuisine="한식", preferred_meal_type="샐러드·가벼운 식사", appliances=[], temporary_owned_seasoning_ids=[x["id"] for x in SEASONING_SEED]),
    )
    salad = salad_result["direct_results"][0]
    assert not any("토마토소스" in text for text in salad["substitutions_used"])


def test_inventory_update_clears_notes_and_zero_quantity_deletes():
    with TestClient(app) as client:
        created = client.post(
            "/ingredients",
            json={
                "ingredient_id": "cabbage",
                "quantity": 1,
                "unit": "통",
                "storage": "냉장",
                "purchase_date": "2026-07-14",
                "condition_status": "needs_review",
                "condition_notes": ["심한 무름 또는 진물"],
            },
        ).json()["item"]
        normalized = client.put(
            f"/ingredients/{created['id']}", json={"condition_status": "normal"}
        )
        assert normalized.status_code == 200
        assert normalized.json()["item"]["condition_notes"] == []
        deleted = client.put(f"/ingredients/{created['id']}", json={"quantity": 0})
        assert deleted.status_code == 200
        assert deleted.json()["deleted"] is True
        assert all(x["id"] != created["id"] for x in client.get("/ingredients").json()["items"])



def test_exact_core_match_precedes_substitution_candidates():
    master = {item["id"]: item for item in INGREDIENT_SEED}
    seasoning_names = {item["id"]: item["name"] for item in SEASONING_SEED}

    def lot(ingredient_id: str, lot_id: int):
        item = master[ingredient_id]
        return {
            "id": lot_id,
            "ingredient_id": ingredient_id,
            "ingredient_name": item["name"],
            "category": item["category"],
            "perishability_level": item["perishability_level"],
            "opened_window_days": item["opened_window_days"],
            "freshness_window_days": item["freshness_window_days"],
            "condition_profile": item["condition_profile"],
            "detail_name": "",
            "quantity": 1,
            "unit": item.get("common_units", ["개"])[0],
            "storage": item["default_storage"],
            "purchase_date": date.today().isoformat(),
            "expiry_date": None,
            "opened": 0,
            "opened_date": None,
            "priority_override": 0,
            "condition_status": "normal",
            "condition_notes": [],
            "note": "",
        }

    def hydrated_recipe(recipe_id: str):
        raw = next(dict(item) for item in RECIPE_SEED if item["id"] == recipe_id)
        raw["ingredients"] = [
            {**entry, "name": master[entry["ingredient_id"]]["name"]}
            for entry in raw.get("ingredients", [])
        ]
        raw["seasonings"] = [
            {**entry, "name": seasoning_names[entry["seasoning_id"]]}
            for entry in raw.get("seasonings", [])
        ]
        return raw

    all_owned = [dict(item, owned=1) for item in SEASONING_SEED]
    owned_ids = [item["id"] for item in SEASONING_SEED]

    cases = [
        ("ws_cream_pasta", ["pasta", "milk"], ["냄비", "프라이팬"]),
        ("ws_mushroom_risotto", ["cooked_rice", "mushroom", "milk"], ["냄비"]),
        ("ws_cream_potato_soup", ["potato", "onion", "milk"], ["냄비"]),
    ]
    for case_index, (recipe_id, ingredient_ids, appliances) in enumerate(cases):
        inventory = [lot(ingredient_id, case_index * 10 + index + 1) for index, ingredient_id in enumerate(ingredient_ids)]
        result = recommend(
            inventory,
            all_owned,
            [hydrated_recipe(recipe_id)],
            [],
            recommendation_payload(
                preferred_cuisine="양식",
                preferred_meal_type="상관없음",
                max_cooking_minutes=60,
                appliances=appliances,
                temporary_owned_seasoning_ids=owned_ids,
            ),
        )
        direct_ids = {item["recipe_id"] for item in result.get("direct_results", [])}
        one_more_ids = {item["recipe_id"] for item in result.get("one_more_results", [])}
        assert recipe_id in direct_ids
        assert recipe_id not in one_more_ids
        recipe_result = next(item for item in result["direct_results"] if item["recipe_id"] == recipe_id)
        assert not any("생크림" in item.get("name", "") for item in recipe_result.get("missing_to_make", []))
        assert not any("생크림 대신 우유" in text for text in recipe_result.get("substitutions_used", []))

def test_tool_alternative_groups():
    with TestClient(app) as client:
        if client.get("/ingredients").json()["summary"]["total"] == 0:
            client.post("/demo/load", json={"only_when_empty": True, "profile": "balanced", "load_balanced_pantry": True})
        payload = recommendation_payload(
            preferred_cuisine="한식",
            cuisine_preference_strength="strict",
            preferred_meal_type="반찬",
            appliances=["냄비"],
            temporary_owned_seasoning_ids=["salt"],
        )
        response = client.post("/recommend", json=payload)
        names = [x["name"] for x in response.json().get("preferred_direct_results", [])]
        assert "계란찜" in names
