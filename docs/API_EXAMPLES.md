# FastAPI 호출 예시

## 상태 확인

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

## 식재료 등록

```bash
curl -X POST http://127.0.0.1:8000/ingredients \
  -H 'Content-Type: application/json' \
  -d '{
    "ingredient_id": "tofu",
    "quantity": 1,
    "unit": "모",
    "storage": "냉장",
    "purchase_date": "2026-07-14",
    "expiry_date": "2026-07-17",
    "opened": false
  }'
```

## 메뉴 추천

```bash
curl -X POST http://127.0.0.1:8000/recommend \
  -H 'Content-Type: application/json' \
  -d '{
    "preferred_cuisine": "한식",
    "cuisine_preference_strength": "priority",
    "preferred_meal_type": "볶음·구이",
    "previous_meal_cuisine": "양식",
    "previous_meal_type": "면",
    "previous_meal_avoidance": "soft",
    "max_cooking_minutes": 30,
    "appliances": ["프라이팬", "냄비"],
    "recommendation_mode": "balanced",
    "repeat_avoidance": "medium",
    "allow_substitutions": true
  }'
```

## 조리 완료

조리 완료는 최근 12시간 안에 추천된 메뉴만 허용한다.

```bash
curl -X POST http://127.0.0.1:8000/meals/complete \
  -H 'Content-Type: application/json' \
  -d '{
    "recipe_id": "kr_spicy_pork",
    "eaten_at": "2026-07-14T19:30:00+09:00",
    "meal_slot": "저녁",
    "usage": [
      {"inventory_id": 1, "remaining_quantity": 100}
    ],
    "note": "저녁 식사"
  }'
```
