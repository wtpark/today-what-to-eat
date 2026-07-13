from __future__ import annotations

import json
from contextlib import asynccontextmanager
from datetime import date, datetime, timedelta
from typing import Any
from collections import Counter
from zoneinfo import ZoneInfo

from fastapi import FastAPI, HTTPException, Response, status

from .database import db_connection, db_transaction, get_db_path, initialize_database
from .repository import (
    get_inventory_item,
    get_master,
    list_inventory_raw,
    list_master_ingredients,
    list_recent_meals,
    list_recipes,
    list_seasonings,
)
from .schemas import (
    DemoLoadRequest,
    IngredientCreate,
    IngredientUpdate,
    MealCompleteRequest,
    RecommendationRequest,
    RepurchaseRequest,
    SeasoningUpdate,
)
from .scoring import enrich_inventory_priority, now_kst, recommend
from .substitutions import allowed_actual_ingredient_ids

KST = ZoneInfo("Asia/Seoul")


@asynccontextmanager
async def lifespan(_: FastAPI):
    initialize_database()
    yield


app = FastAPI(
    title="오늘 뭐먹지 API",
    version="1.1.0",
    description="냉장고 선입선출 기반 식재료 관리·메뉴 추천 API",
    lifespan=lifespan,
)


@app.get("/")
def root() -> dict[str, str]:
    return {"service": "오늘 뭐먹지 API", "docs": "/docs", "health": "/health"}


@app.get("/health")
def health() -> dict[str, Any]:
    try:
        with db_connection() as conn:
            conn.execute("SELECT 1").fetchone()
            ingredients = conn.execute("SELECT COUNT(*) FROM ingredient_master").fetchone()[0]
            recipes = conn.execute("SELECT COUNT(*) FROM recipes WHERE active = 1").fetchone()[0]
            inventory = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
            seed_row = conn.execute("SELECT value FROM seed_meta WHERE key = 'seed_version'").fetchone()
        return {
            "status": "ok",
            "database": "connected",
            "database_path": str(get_db_path()),
            "master_ingredients": ingredients,
            "recipes": recipes,
            "inventory_lots": inventory,
            "seed_version": seed_row[0] if seed_row else "unknown",
        }
    except Exception as exc:  # pragma: no cover - health should expose startup failures
        raise HTTPException(status_code=503, detail=f"database unavailable: {exc}") from exc


@app.get("/master/ingredients")
def get_master_ingredients() -> list[dict[str, Any]]:
    with db_connection() as conn:
        return list_master_ingredients(conn)


@app.get("/catalog/summary")
def get_catalog_summary() -> dict[str, Any]:
    with db_connection() as conn:
        ingredients = list_master_ingredients(conn)
        recipes = list_recipes(conn)
        seasonings = list_seasonings(conn)
    cuisine_counts = Counter(item["cuisine"] for item in recipes)
    meal_type_counts = Counter(item["meal_type"] for item in recipes)
    return {
        "ingredients": len(ingredients),
        "seasonings": len(seasonings),
        "recipes": len(recipes),
        "recipes_by_cuisine": dict(cuisine_counts),
        "recipes_by_meal_type": dict(meal_type_counts),
        "recipe_names_by_cuisine": {
            cuisine: [item["name"] for item in recipes if item["cuisine"] == cuisine]
            for cuisine in sorted(cuisine_counts)
        },
        "quick_recipes": [
            {"name": item["name"], "cook_time": item["cook_time"], "meal_type": item["meal_type"]}
            for item in recipes if item["cook_time"] <= 5
        ],
    }


@app.get("/ingredients")
def get_ingredients() -> dict[str, Any]:
    with db_connection() as conn:
        items = enrich_inventory_priority(list_inventory_raw(conn))
    summary = {
        "total": len(items),
        "use_first": sum(1 for x in items if x["action"] in ("먼저 사용", "사용자 지정 우선 사용")),
        "opened": sum(1 for x in items if x["opened"]),
        "missing_expiry": sum(1 for x in items if not x["expiry_date"]),
        "status_review": sum(1 for x in items if x.get("condition_status") == "needs_review"),
        "expired": sum(1 for x in items if x.get("expired")),
        "user_excluded": sum(1 for x in items if x.get("condition_status") == "excluded"),
        "zero_quantity": sum(1 for x in items if float(x.get("quantity", 0) or 0) <= 0),
        "recommendation_excluded": sum(1 for x in items if not x["recommendation_eligible"]),
    }
    # Backward-compatible aggregate key.
    summary["needs_review"] = summary["recommendation_excluded"]
    return {"summary": summary, "items": items}


@app.post("/ingredients", status_code=status.HTTP_201_CREATED)
def create_ingredient(payload: IngredientCreate) -> dict[str, Any]:
    with db_transaction() as conn:
        if not get_master(conn, payload.ingredient_id):
            raise HTTPException(status_code=404, detail="식재료 마스터를 찾을 수 없습니다.")
        cursor = conn.execute(
            """
            INSERT INTO inventory(
                ingredient_id, detail_name, quantity, unit, storage, purchase_date,
                expiry_date, opened, opened_date, priority_override,
                condition_status, condition_notes_json, note, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, CURRENT_TIMESTAMP)
            """,
            (
                payload.ingredient_id,
                payload.detail_name.strip(),
                payload.quantity,
                payload.unit.strip(),
                payload.storage,
                payload.purchase_date.isoformat(),
                payload.expiry_date.isoformat() if payload.expiry_date else None,
                int(payload.opened),
                payload.opened_date.isoformat() if payload.opened_date else None,
                int(payload.priority_override),
                payload.condition_status,
                json.dumps(payload.condition_notes, ensure_ascii=False),
                payload.note.strip(),
            ),
        )
        inventory_id = int(cursor.lastrowid)
        item = get_inventory_item(conn, inventory_id)
    return {"message": "식재료가 저장되었습니다.", "item": enrich_inventory_priority([item])[0]}


@app.put("/ingredients/{inventory_id}")
def update_ingredient(inventory_id: int, payload: IngredientUpdate) -> dict[str, Any]:
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="수정할 값이 없습니다.")

    with db_transaction() as conn:
        current = get_inventory_item(conn, inventory_id)
        if not current:
            raise HTTPException(status_code=404, detail="재고를 찾을 수 없습니다.")

        effective_purchase = updates.get("purchase_date") or date.fromisoformat(current["purchase_date"])
        effective_expiry = updates.get("expiry_date") if "expiry_date" in updates else (
            date.fromisoformat(current["expiry_date"]) if current.get("expiry_date") else None
        )
        effective_opened = updates.get("opened") if "opened" in updates else bool(current.get("opened"))
        effective_opened_date = updates.get("opened_date") if "opened_date" in updates else (
            date.fromisoformat(current["opened_date"]) if current.get("opened_date") else None
        )
        effective_quantity = float(updates.get("quantity", current["quantity"]))

        if effective_expiry and effective_expiry < effective_purchase:
            raise HTTPException(status_code=400, detail="표시기한은 구매일보다 빠를 수 없습니다.")
        if effective_opened and effective_opened_date and effective_opened_date < effective_purchase:
            raise HTTPException(status_code=400, detail="개봉일은 구매일보다 빠를 수 없습니다.")

        if effective_quantity == 0:
            conn.execute("DELETE FROM inventory WHERE id = ?", (inventory_id,))
            return {"message": "수량이 0이 되어 재고를 소진 처리했습니다.", "deleted": True, "item": None}

        if "opened" in updates and not effective_opened:
            updates["opened_date"] = None
        elif effective_opened and not effective_opened_date:
            updates["opened_date"] = effective_purchase

        # A normal state must not retain old warning notes.
        if updates.get("condition_status") == "normal":
            updates["condition_notes"] = []

        column_map = {
            "detail_name": "detail_name",
            "quantity": "quantity",
            "unit": "unit",
            "storage": "storage",
            "purchase_date": "purchase_date",
            "expiry_date": "expiry_date",
            "opened": "opened",
            "opened_date": "opened_date",
            "priority_override": "priority_override",
            "condition_status": "condition_status",
            "condition_notes": "condition_notes_json",
            "note": "note",
        }
        set_parts: list[str] = []
        values: list[Any] = []
        for field, value in updates.items():
            column = column_map[field]
            if field in {"opened", "priority_override"}:
                value = int(bool(value))
            elif field in {"purchase_date", "expiry_date", "opened_date"}:
                value = value.isoformat() if value else None
            elif field == "condition_notes":
                value = json.dumps(value or [], ensure_ascii=False)
            elif field in {"detail_name", "unit", "note"} and isinstance(value, str):
                value = value.strip()
            set_parts.append(f"{column} = ?")
            values.append(value)

        set_parts.append("updated_at = CURRENT_TIMESTAMP")
        values.append(inventory_id)
        conn.execute(f"UPDATE inventory SET {', '.join(set_parts)} WHERE id = ?", values)
        item = get_inventory_item(conn, inventory_id)
    return {"message": "재고 정보가 수정되었습니다.", "deleted": False, "item": enrich_inventory_priority([item])[0]}


@app.delete("/ingredients/{inventory_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_ingredient(inventory_id: int) -> Response:
    with db_transaction() as conn:
        cursor = conn.execute("DELETE FROM inventory WHERE id = ?", (inventory_id,))
        if cursor.rowcount == 0:
            raise HTTPException(status_code=404, detail="재고를 찾을 수 없습니다.")
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@app.post("/ingredients/{inventory_id}/repurchase", status_code=status.HTTP_201_CREATED)
def repurchase_ingredient(inventory_id: int, payload: RepurchaseRequest) -> dict[str, Any]:
    with db_transaction() as conn:
        source = get_inventory_item(conn, inventory_id)
        if not source:
            raise HTTPException(status_code=404, detail="기존 재고를 찾을 수 없습니다.")
        cursor = conn.execute(
            """
            INSERT INTO inventory(
                ingredient_id, detail_name, quantity, unit, storage, purchase_date,
                expiry_date, opened, opened_date, priority_override,
                condition_status, condition_notes_json, note, updated_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, 0, NULL, 0, 'normal', '[]', ?, CURRENT_TIMESTAMP)
            """,
            (
                source["ingredient_id"],
                payload.detail_name if payload.detail_name is not None else source["detail_name"],
                payload.quantity,
                payload.unit,
                source["storage"],
                payload.purchase_date.isoformat(),
                payload.expiry_date.isoformat() if payload.expiry_date else None,
                payload.note,
            ),
        )
        item = get_inventory_item(conn, int(cursor.lastrowid))
    return {"message": "같은 품목을 새 구매 묶음으로 등록했습니다.", "item": enrich_inventory_priority([item])[0]}


@app.get("/seasonings")
def get_seasonings() -> list[dict[str, Any]]:
    with db_connection() as conn:
        return list_seasonings(conn)


@app.put("/seasonings")
def update_seasonings(payload: SeasoningUpdate) -> dict[str, Any]:
    with db_transaction() as conn:
        valid_ids = {row[0] for row in conn.execute("SELECT id FROM seasonings").fetchall()}
        unknown = set(payload.owned_ids) - valid_ids
        if unknown:
            raise HTTPException(status_code=400, detail=f"알 수 없는 양념 ID: {sorted(unknown)}")
        conn.execute("UPDATE seasonings SET owned = 0, updated_at = CURRENT_TIMESTAMP")
        if payload.owned_ids:
            placeholders = ",".join("?" for _ in payload.owned_ids)
            conn.execute(
                f"UPDATE seasonings SET owned = 1, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                payload.owned_ids,
            )
        result = list_seasonings(conn)
    return {"message": "내 양념장 정보가 저장되었습니다.", "items": result}


@app.post("/recommend")
def create_recommendation(payload: RecommendationRequest) -> dict[str, Any]:
    request_data = payload.model_dump()
    with db_transaction() as conn:
        result = recommend(
            list_inventory_raw(conn),
            list_seasonings(conn),
            list_recipes(conn),
            list_recent_meals(conn, 100),
            request_data,
        )
        requested_at = now_kst().isoformat(timespec="seconds")
        for group_name, result_key in (("direct", "direct_results"), ("one_more", "one_more_results")):
            for item in result.get(result_key, []):
                conn.execute(
                    """
                    INSERT INTO recommendation_history(
                        requested_at, recipe_id, score, mode, result_group, selected, request_json
                    ) VALUES (?, ?, ?, ?, ?, 0, ?)
                    """,
                    (
                        requested_at,
                        item["recipe_id"],
                        item["score"],
                        payload.recommendation_mode,
                        group_name,
                        json.dumps(request_data, ensure_ascii=False, default=str),
                    ),
                )
    return result


@app.post("/meals/complete", status_code=status.HTTP_201_CREATED)
def complete_meal(payload: MealCompleteRequest) -> dict[str, Any]:
    with db_transaction() as conn:
        recipe = conn.execute("SELECT * FROM recipes WHERE id = ? AND active = 1", (payload.recipe_id,)).fetchone()
        if not recipe:
            raise HTTPException(status_code=404, detail="레시피를 찾을 수 없습니다.")

        canonical_ingredient_ids = {
            row[0]
            for row in conn.execute(
                "SELECT ingredient_id FROM recipe_ingredients WHERE recipe_id = ?",
                (payload.recipe_id,),
            ).fetchall()
        }
        allowed_ingredient_ids = allowed_actual_ingredient_ids(canonical_ingredient_ids)
        seen_inventory_ids: set[int] = set()
        usage_log = []
        for usage in payload.usage:
            if usage.inventory_id in seen_inventory_ids:
                raise HTTPException(status_code=400, detail="같은 재고가 사용 목록에 중복되었습니다.")
            seen_inventory_ids.add(usage.inventory_id)
            item = get_inventory_item(conn, usage.inventory_id)
            if not item:
                raise HTTPException(status_code=404, detail=f"재고 ID {usage.inventory_id}를 찾을 수 없습니다.")
            if item["ingredient_id"] not in allowed_ingredient_ids:
                raise HTTPException(status_code=400, detail=f"{item['ingredient_name']}은 선택한 메뉴의 재료가 아닙니다.")
            if usage.remaining_quantity > item["quantity"]:
                raise HTTPException(status_code=400, detail=f"{item['ingredient_name']}의 남은 수량이 현재 수량보다 큽니다.")
            used_quantity = round(float(item["quantity"]) - float(usage.remaining_quantity), 6)
            if used_quantity < 0:
                raise HTTPException(status_code=400, detail="사용량 계산이 올바르지 않습니다.")
            if used_quantity == 0:
                continue
            if usage.remaining_quantity == 0:
                conn.execute("DELETE FROM inventory WHERE id = ?", (usage.inventory_id,))
            else:
                conn.execute(
                    "UPDATE inventory SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
                    (usage.remaining_quantity, usage.inventory_id),
                )
            conn.execute(
                """
                INSERT INTO inventory_usage(
                    inventory_id, ingredient_id, recipe_id, before_quantity,
                    remaining_quantity, used_quantity, unit, used_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    usage.inventory_id,
                    item["ingredient_id"],
                    payload.recipe_id,
                    item["quantity"],
                    usage.remaining_quantity,
                    used_quantity,
                    item["unit"],
                    payload.eaten_at.astimezone(KST).isoformat(timespec="seconds") if payload.eaten_at.tzinfo else payload.eaten_at.replace(tzinfo=KST).isoformat(timespec="seconds"),
                ),
            )
            usage_log.append({"name": item["ingredient_name"], "used_quantity": used_quantity, "remaining_quantity": usage.remaining_quantity, "unit": item["unit"]})

        if not any(float(item["used_quantity"]) > 0 for item in usage_log):
            raise HTTPException(status_code=400, detail="최소 한 개의 재료 사용량을 입력해주세요.")

        eaten_at = payload.eaten_at.astimezone(KST) if payload.eaten_at.tzinfo else payload.eaten_at.replace(tzinfo=KST)
        conn.execute(
            """
            INSERT INTO meal_history(recipe_id, eaten_at, meal_slot, cuisine, meal_type, cooking_method, note)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.recipe_id,
                eaten_at.isoformat(timespec="seconds"),
                payload.meal_slot,
                recipe["cuisine"],
                recipe["meal_type"],
                recipe["cooking_method"],
                payload.note,
            ),
        )
        conn.execute(
            """
            UPDATE recommendation_history
            SET selected = 1
            WHERE id = (
                SELECT id FROM recommendation_history
                WHERE recipe_id = ?
                ORDER BY requested_at DESC, id DESC LIMIT 1
            )
            """,
            (payload.recipe_id,),
        )
    return {"message": "식사 기록과 냉장고 재고가 함께 갱신되었습니다.", "usage": usage_log}


@app.get("/meals/history")
def get_meal_history(limit: int = 50) -> list[dict[str, Any]]:
    with db_connection() as conn:
        return list_recent_meals(conn, min(max(limit, 1), 200))


@app.post("/demo/load", status_code=status.HTTP_201_CREATED)
def load_demo_data(payload: DemoLoadRequest) -> dict[str, Any]:
    now = now_kst().date()
    korean_samples = [
        ("soft_tofu", "찌개용 순두부", 1, "봉", "냉장", now - timedelta(days=2), now + timedelta(days=1), 0, None),
        ("pork", "찌개용 앞다리살", 350, "g", "냉장", now - timedelta(days=2), now + timedelta(days=2), 1, now - timedelta(days=1)),
        ("kimchi", "잘 익은 배추김치", 500, "g", "냉장", now - timedelta(days=12), now + timedelta(days=20), 1, now - timedelta(days=12)),
        ("onion", "", 2, "개", "실온", now - timedelta(days=7), None, 0, None),
        ("green_onion", "", 0.5, "단", "냉장", now - timedelta(days=4), now + timedelta(days=3), 1, now - timedelta(days=2)),
        ("cheongyang_chili", "", 5, "개", "냉장", now - timedelta(days=3), now + timedelta(days=5), 0, None),
        ("radish", "", 0.5, "개", "냉장", now - timedelta(days=6), now + timedelta(days=8), 1, now - timedelta(days=2)),
        ("dumpling", "냉동 고기만두", 12, "개", "냉동", now - timedelta(days=20), now + timedelta(days=70), 1, now - timedelta(days=5)),
        ("cooked_rice", "남은 밥", 2, "공기", "냉장", now - timedelta(days=1), now + timedelta(days=1), 1, now - timedelta(days=1)),
        ("egg", "", 8, "개", "냉장", now - timedelta(days=5), now + timedelta(days=10), 0, None),
    ]
    balanced_samples = [
        ("egg", "", 8, "개", "냉장", now - timedelta(days=4), now + timedelta(days=10), 0, None),
        ("cooked_rice", "남은 밥", 2, "공기", "냉장", now - timedelta(days=1), now + timedelta(days=1), 1, now - timedelta(days=1)),
        ("bread", "샌드위치용", 6, "장", "실온", now - timedelta(days=2), now + timedelta(days=3), 1, now - timedelta(days=2)),
        ("pasta", "스파게티면", 3, "인분", "실온", now - timedelta(days=20), None, 1, now - timedelta(days=20)),
        ("chicken", "닭다리살", 500, "g", "냉장", now - timedelta(days=2), now + timedelta(days=2), 1, now - timedelta(days=1)),
        ("pork", "볶음용", 350, "g", "냉장", now - timedelta(days=3), now + timedelta(days=2), 1, now - timedelta(days=1)),
        ("tofu", "", 1, "모", "냉장", now - timedelta(days=3), now + timedelta(days=1), 1, now - timedelta(days=1)),
        ("onion", "", 3, "개", "실온", now - timedelta(days=7), None, 0, None),
        ("potato", "", 4, "개", "실온", now - timedelta(days=8), None, 0, None),
        ("carrot", "", 2, "개", "냉장", now - timedelta(days=6), None, 0, None),
        ("mushroom", "", 250, "g", "냉장", now - timedelta(days=3), now + timedelta(days=3), 1, now - timedelta(days=1)),
        ("tomato_sauce", "파스타용", 500, "g", "냉장", now - timedelta(days=4), now + timedelta(days=7), 1, now - timedelta(days=3)),
        ("milk", "", 900, "mL", "냉장", now - timedelta(days=3), now + timedelta(days=4), 1, now - timedelta(days=2)),
        ("sliced_cheese", "", 6, "장", "냉장", now - timedelta(days=5), now + timedelta(days=15), 1, now - timedelta(days=2)),
        ("cabbage", "", 0.5, "통", "냉장", now - timedelta(days=4), now + timedelta(days=5), 1, now - timedelta(days=2)),
        ("tomato", "", 4, "개", "냉장", now - timedelta(days=3), now + timedelta(days=4), 0, None),
        ("canned_tuna", "", 2, "캔", "실온", now - timedelta(days=30), now + timedelta(days=180), 0, None),
        ("dumpling", "냉동만두", 12, "개", "냉동", now - timedelta(days=20), now + timedelta(days=70), 1, now - timedelta(days=5)),
        ("soft_tofu", "", 1, "봉", "냉장", now - timedelta(days=2), now + timedelta(days=1), 0, None),
        ("bibim_noodle_pack", "", 2, "봉", "실온", now - timedelta(days=15), now + timedelta(days=120), 0, None),
        ("naengmyeon_noodle", "", 2, "인분", "냉장", now - timedelta(days=4), now + timedelta(days=10), 0, None),
        ("naengmyeon_broth", "", 2, "봉", "냉장", now - timedelta(days=4), now + timedelta(days=20), 0, None),
        ("frozen_pork_cutlet", "", 2, "장", "냉동", now - timedelta(days=25), now + timedelta(days=90), 1, now - timedelta(days=7)),
    ]
    samples = balanced_samples if payload.profile == "balanced" else korean_samples
    balanced_pantry_ids = [
        "salt", "sugar", "pepper", "cooking_oil", "soy_sauce", "vinegar",
        "minced_garlic", "ketchup", "gochujang", "doenjang", "gochugaru",
        "oyster_sauce", "olive_oil", "butter", "mayonnaise", "curry_powder",
        "chicken_stock", "pancake_mix", "starch", "soup_soy",
    ]
    with db_transaction() as conn:
        existing = conn.execute("SELECT COUNT(*) FROM inventory").fetchone()[0]
        if payload.only_when_empty and existing:
            raise HTTPException(status_code=409, detail="냉장고에 이미 재고가 있어 데모 데이터를 추가하지 않았습니다.")
        for sample in samples:
            conn.execute(
                """
                INSERT INTO inventory(
                    ingredient_id, detail_name, quantity, unit, storage, purchase_date,
                    expiry_date, opened, opened_date, priority_override,
                    condition_status, condition_notes_json, note
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, 0, 'normal', '[]', '데모 데이터')
                """,
                (
                    sample[0], sample[1], sample[2], sample[3], sample[4], sample[5].isoformat(),
                    sample[6].isoformat() if sample[6] else None, sample[7],
                    sample[8].isoformat() if sample[8] else None,
                ),
            )
        if payload.load_balanced_pantry:
            conn.execute("UPDATE seasonings SET owned = 0, updated_at = CURRENT_TIMESTAMP")
            placeholders = ",".join("?" for _ in balanced_pantry_ids)
            conn.execute(
                f"UPDATE seasonings SET owned = 1, updated_at = CURRENT_TIMESTAMP WHERE id IN ({placeholders})",
                balanced_pantry_ids,
            )
    return {
        "message": f"{payload.profile} 데모 식재료 {len(samples)}개를 추가했습니다.",
        "count": len(samples),
        "profile": payload.profile,
        "pantry_loaded": payload.load_balanced_pantry,
    }
