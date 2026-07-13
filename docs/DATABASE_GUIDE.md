# SQLite 데이터베이스 안내

## DB 위치

```text
컨테이너: /app/data/today_menu.db
Docker volume: today_menu_data
```

## 주요 테이블

- `ingredient_master`: 식재료 마스터
- `inventory`: 구매 묶음별 냉장고 재고
- `seasonings`: 양념 보유 상태
- `recipes`: 레시피 기본 정보
- `recipe_ingredients`: 레시피 재료 역할
- `recipe_seasonings`: 레시피 양념
- `recommendation_history`: 추천 이력
- `meal_history`: 실제 식사 이력
- `inventory_usage`: 조리 시 재료 사용량
- `seed_meta`: 시드 버전

## 최초 실행

FastAPI lifespan에서 다음을 수행한다.

```text
스키마 생성
→ 기존 DB 마이그레이션
→ 식재료·양념·레시피 UPSERT
→ 제거된 레시피 비활성화
→ 시드 버전 기록
```

## 조회

```bash
sudo docker exec today-menu-back python /app/scripts/inspect_db.py
```

직접 SQL:

```bash
sudo docker exec today-menu-back python - <<'PY'
import sqlite3
conn = sqlite3.connect('/app/data/today_menu.db')
for row in conn.execute('SELECT id, ingredient_id, quantity, unit FROM inventory'):
    print(row)
PY
```

## 백업

```bash
sudo docker cp today-menu-back:/app/data/today_menu.db ./today_menu_backup.db
```

## 사용자 데이터 초기화

```bash
sudo docker exec -it today-menu-back python /app/scripts/reset_user_data.py
```

화면 지시에 따라 `RESET`을 입력한다.

## 동시 접근

- WAL 모드
- `busy_timeout=5000`
- 짧은 트랜잭션
- 조리 완료는 하나의 트랜잭션으로 재고와 식사 기록을 함께 처리
