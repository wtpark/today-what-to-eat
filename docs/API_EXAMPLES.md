# FastAPI 호출 예시 V5

## 상태 확인

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

## 식재료 조회

```bash
curl -s http://127.0.0.1:8000/ingredients | python3 -m json.tool
```

## 메뉴 추천

```bash
curl -X POST http://127.0.0.1:8000/recommend \
  -H 'Content-Type: application/json' \
  -d '{
    "preferred_cuisine": "양식",
    "cuisine_preference_strength": "priority",
    "preferred_meal_type": "면",
    "previous_meal_cuisine": "한식",
    "previous_meal_type": "국·찌개",
    "previous_meal_avoidance": "exclude_cuisine",
    "max_cooking_minutes": 30,
    "appliances": ["프라이팬", "냄비", "에어프라이어"],
    "recommendation_mode": "balanced",
    "repeat_avoidance": "medium",
    "temporary_owned_seasoning_ids": ["salt", "pepper", "cooking_oil", "olive_oil"],
    "excluded_ingredient_ids": [],
    "allow_substitutions": true
  }'
```

## 직전 식사 처리 값

```text
none             상관없음
soft             가능하면 피하기
exclude_cuisine  같은 음식 계열 제외
exclude_type     같은 식사 형태 제외
exclude_either   계열 또는 형태 중 하나라도 같으면 제외
exclude_both     계열과 형태가 모두 같을 때만 제외
```

기존 V4의 `lunch_*` 필드도 호환 입력으로 받지만 신규 코드는 `previous_meal_*`를 사용한다.

## 조리 완료

```bash
curl -X POST http://127.0.0.1:8000/meals/complete \
  -H 'Content-Type: application/json' \
  -d '{
    "recipe_id": "kr_steamed_egg",
    "eaten_at": "2026-07-14T19:20:00+09:00",
    "meal_slot": "저녁",
    "usage": [
      {"inventory_id": 1, "remaining_quantity": 0}
    ],
    "note": ""
  }'
```

모든 재료의 사용량이 0이면 `400`을 반환한다.
