# SQLite 및 데이터 저장 설명

## 1. SQLite를 사용하는 이유

이 프로젝트는 단일 사용자 과제용 서비스이므로 별도 DB 서버 없이 파일 하나로 동작하는 SQLite가 적합합니다.

- 설치가 단순함
- Python `sqlite3` 기본 모듈 사용
- EC2에서 별도 DB 서비스 불필요
- Docker volume으로 데이터 유지 가능
- SQL 테이블과 관계를 명확하게 보여줄 수 있음

## 2. 실제 DB 위치

Docker 컨테이너 내부:

```text
/app/data/today_menu.db
```

Docker named volume:

```text
today_menu_data
```

호스트의 일반 프로젝트 폴더에 DB 파일이 직접 보이지 않는 것이 정상입니다.

## 3. 초기화 코드

FastAPI 시작 시 `back/app/database.py`의 `initialize_database()`가 실행됩니다.

```text
schema.sql 실행
→ ingredient_master UPSERT
→ seasonings UPSERT
→ recipes UPSERT
→ recipe_ingredients 재구성
→ recipe_seasonings 재구성
→ seed_meta 버전 저장
```

사용자 데이터 테이블인 `inventory`, `meal_history`, `inventory_usage`는 초기화 때 삭제하지 않습니다.

## 4. 주요 테이블

### ingredient_master

식재료 종류의 기준 정보입니다.

```text
돼지고기
두부
양파
경성치즈
순두부
```

보관 기본값, 식품군 민감도, 개봉 관리 구간, 표시기한 미입력 시 사용할 관리 구간, 상태 질문 프로필을 저장합니다.

### inventory

사용자가 실제로 구매한 냉장고 재고입니다.

같은 돼지고기라도 구매일이 다르면 별도 행으로 저장합니다.

```text
ID 17 / 돼지고기 300g / 7월 10일 구매
ID 23 / 돼지고기 500g / 7월 13일 구매
```

이 구조를 `inventory lot`, 즉 구매 묶음이라고 볼 수 있습니다.

### seasonings

사용자가 보유한 양념 여부를 저장합니다.

```text
간장 owned=1
굴소스 owned=0
```

### recipes

메뉴명, 음식 계열, 식사 형태, 조리시간, 도구를 저장합니다.

### recipe_ingredients

레시피와 식재료의 다대다 관계를 저장합니다.

역할:

```text
must       필수 재료
core       대체 가능한 핵심 재료
supporting 있으면 좋은 보조 재료
```

### recipe_seasonings

레시피에 필요한 양념과 필수 여부를 저장합니다.

### recommendation_history

추천 요청 결과를 저장합니다. 추천됐다고 실제로 먹은 것은 아니므로 식사 이력과 분리합니다.

### meal_history

`이 메뉴로 먹었어요`를 누른 실제 식사만 저장합니다. 반복 방지에는 이 테이블만 사용합니다.

### inventory_usage

조리 전 수량, 조리 후 남은 수량, 사용량을 기록합니다.

## 5. SQLite 내부 확인

### 방법 A: 컨테이너 Python 사용

테이블 목록:

```bash
sudo docker exec today-menu-back python -c "import sqlite3; c=sqlite3.connect('/app/data/today_menu.db'); print(c.execute(\"SELECT name FROM sqlite_master WHERE type='table' ORDER BY name\").fetchall())"
```

재고 확인:

```bash
sudo docker exec today-menu-back python -c "import sqlite3; c=sqlite3.connect('/app/data/today_menu.db'); print(c.execute('SELECT id, ingredient_id, quantity, unit, purchase_date FROM inventory').fetchall())"
```

레시피 개수:

```bash
sudo docker exec today-menu-back python -c "import sqlite3; c=sqlite3.connect('/app/data/today_menu.db'); print(c.execute('SELECT COUNT(*) FROM recipes').fetchone())"
```

### 방법 B: 제공 스크립트

```bash
sudo docker exec today-menu-back python /app/scripts/inspect_db.py
```

컨테이너 이미지에는 `back/scripts`가 `/app/scripts`로 복사됩니다.

사용자 데이터만 초기화하려면:

```bash
sudo docker exec -it today-menu-back python /app/scripts/reset_user_data.py
```

확인 문구로 `RESET`을 입력해야 실행됩니다. 마스터·레시피·양념 목록은 유지됩니다.

## 6. 자주 쓰는 SQL

재고 전체:

```sql
SELECT
    i.id,
    m.name,
    i.quantity,
    i.unit,
    i.purchase_date,
    i.expiry_date,
    i.condition_status
FROM inventory i
JOIN ingredient_master m ON m.id = i.ingredient_id
ORDER BY i.purchase_date;
```

최근 식사:

```sql
SELECT
    mh.eaten_at,
    r.name,
    mh.meal_slot,
    mh.cuisine,
    mh.meal_type
FROM meal_history mh
JOIN recipes r ON r.id = mh.recipe_id
ORDER BY mh.eaten_at DESC;
```

음식 계열별 레시피 수:

```sql
SELECT cuisine, COUNT(*)
FROM recipes
GROUP BY cuisine
ORDER BY cuisine;
```

## 7. DB 백업

```bash
sudo docker cp today-menu-back:/app/data/today_menu.db ./today_menu_backup.db
```

복원하려면 실행 중인 컨테이너를 중지하고 DB 파일을 다시 복사해야 합니다.

## 8. DB 초기화

사용자 데이터까지 모두 삭제:

```bash
sudo docker compose down -v
sudo docker compose up -d --build
```

이후 FastAPI가 새 DB와 시드 데이터를 자동으로 만듭니다.

## 9. 동시성 설정

각 SQLite 연결에서 다음을 적용합니다.

```sql
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;
PRAGMA busy_timeout = 5000;
```

- 외래키 무결성 적용
- WAL 모드로 읽기/쓰기 충돌 완화
- 잠금 발생 시 최대 5초 대기
- 조리 완료 재고 차감은 하나의 트랜잭션으로 처리


## V5 마이그레이션과 이력 보존

기존 DB에 다음 컬럼이 없으면 시작 시 자동 추가합니다.

```text
ingredient_master.freshness_window_days
recipes.active
```

시드에서 제거된 레시피는 식사 이력의 외래키를 보존하기 위해 삭제하지 않고 `active=0`으로 변경합니다. 추천 조회는 활성 레시피만 사용합니다.
