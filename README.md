# 오늘 뭐먹지 V5

냉장고 재고를 구매 묶음별로 저장하고, 선입선출·표시기한·개봉 상태·현재 취향·직전/최근 식사·보유 양념·조리 조건을 함께 반영해 메뉴를 추천하는 웹앱입니다.

- Frontend: Streamlit
- Backend: FastAPI
- Database: SQLite
- Deployment: Docker Compose + AWS EC2

## V5 핵심 변화

- 식재료 69개, 양념 32개, 활성 레시피 73개
- 표시기한 입력 체크 즉시 날짜 입력란 표시
- 표시기한이 없는 식재료는 `freshness_window_days` 관리 구간으로 우선도 보완
- 개봉 즉시 기본 우선도 5점 부여 후 경과일에 따라 추가 반영
- 같은 날 구매한 같은 재료는 동일 FIFO 점수 적용
- 사용자 지정 `우선 사용`을 실제 메뉴 추천 순위에 반영
- 직전 식사 입력과 최근 식사 기록의 중복 감점 방지
- 직전 식사 회피 조건을 명확한 6단계로 정리
- 선택 음식 계열·식사 형태 완전 일치 결과와 완화 결과 분리
- 핵심 재료가 실제로 2개 부족한 메뉴를 `하나만 더`로 잘못 표시하던 문제 수정
- 대체 재료를 `동등 대체`와 `간이 대체`로 분리하고 조리 문맥 제한
- 샐러드에서 토마토를 토마토소스로 대체하는 등 부자연스러운 대체 차단
- 조리 완료 시 최소 한 재료의 실제 사용량을 요구
- 수량을 0으로 수정하면 해당 재고 자동 삭제
- 상태를 정상으로 변경하면 이전 상태 메모 자동 제거
- 냉장고 요약에서 상태 확인·표시기한 경과·사용자 제외·수량 없음 분리
- 사용 이력이 있는 레시피는 삭제하지 않고 `active=0`으로 비활성화
- 중복 검색 별칭 검증 및 충돌 제거
- 불필요한 믹서기 선택지 제거

## 데이터 출처

식재료와 레시피는 추천 기능 검증을 위해 프로젝트 내부에서 직접 구조화한 시드 데이터입니다.

```text
source = curated_project_v5
```

공공데이터 API를 실시간 호출하거나 외부 레시피를 그대로 복사한 데이터가 아닙니다. 발표에서는 **프로젝트용 정제 시드 데이터**라고 설명해야 합니다.

## 소비 우선도 정책

식품 안전 확률이 아니라 재고의 상대적 소비 순서를 정하는 서비스 정책 점수입니다.

- 포장지 표시기한이 있으면 실제 입력 날짜를 최우선 사용
- 표시기한이 없으면 식재료별 관리 구간과 구매일로 최대 40점 추정
- 개봉 시 5점, 개봉 후 경과에 따라 최대 20점
- 동일 품목 내 구매일 기반 FIFO 및 구매 경과 최대 20점
- 식품군 소비 민감도 최대 10점
- 냉동은 구성 점수에 0.35 보정
- 표시기한 경과·상태 확인 필요·사용자 제외 재료는 추천에서 제외

`freshness_window_days`는 섭취 가능 기한이 아니라 표시기한이 없는 식재료를 정렬하기 위한 **앱 내부 관리 구간**입니다.

## 프로젝트 구조

```text
today-what-to-eat-v5/
├─ front/
│  ├─ app.py
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ .streamlit/config.toml
├─ back/
│  ├─ app/
│  ├─ seed/
│  ├─ scripts/
│  ├─ sql/schema.sql
│  ├─ tests/
│  ├─ Dockerfile
│  └─ requirements.txt
├─ docs/
├─ scripts/
├─ docker-compose.yml
└─ README.md
```

## Docker 실행

```bash
sudo docker compose config
sudo docker compose build --no-cache
sudo docker compose up -d
sudo docker compose ps
```

브라우저:

```text
http://현재_EC2_퍼블릭_IP
```

FastAPI 상태:

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

정상 V5 예시:

```json
{
  "status": "ok",
  "database": "connected",
  "master_ingredients": 69,
  "recipes": 73,
  "seed_version": "2026-07-14-v5"
}
```

## 기존 V4 DB 자동 마이그레이션

FastAPI 시작 시 기존 SQLite DB에 다음 컬럼이 없으면 자동으로 추가합니다.

```text
ingredient_master.freshness_window_days
recipes.active
```

기존 사용자 재고·양념 설정·식사 이력은 유지됩니다. 시드에서 빠진 레시피도 이력 보존을 위해 물리 삭제하지 않고 `active=0`으로 비활성화합니다.

## 테스트

```bash
cd back
PYTHONPATH=. pytest -q
```

현재 자동 테스트 결과:

```text
7 passed
```

추가로 전체 Python 문법 검사, JSON 파싱, V4 → V5 SQLite 마이그레이션을 확인했습니다. 현재 제작 환경에서는 Docker 엔진과 실제 브라우저 렌더링을 실행하지 못했으므로 EC2에서 최종 빌드 확인이 필요합니다.

## 주의사항

- `/demo/load`는 과제 시연용 공개 엔드포인트입니다. 실제 서비스에서는 인증이 필요합니다.
- 식재료 종류 자체를 잘못 선택한 경우 해당 재고를 삭제하고 다시 등록합니다.
- 레시피별 정확한 필요량·인분·단위 환산은 공공 레시피 계량 데이터를 확보한 뒤 후속 발전 과제로 진행합니다.
- 현재는 개인 시연을 전제로 하나의 SQLite 냉장고를 사용합니다.
- `sudo docker compose down -v`는 사용자 재고·양념·식사 기록까지 삭제하므로 일반 업데이트에서는 실행하지 않습니다.

## 문서

- [V5 변경 사항](docs/CHANGELOG_V5.md)
- [추천 점수 정책](docs/SCORING_POLICY.md)
- [데이터 카탈로그](docs/DATA_CATALOG.md)
- [SQLite와 SQL 설명](docs/DATABASE_GUIDE.md)
- [FastAPI 호출 예시](docs/API_EXAMPLES.md)
- [EC2 배포 안내](docs/EC2_DEPLOY.md)
- [후속 발전 과제](docs/NEXT_TASKS.md)
