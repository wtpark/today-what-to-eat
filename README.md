# 오늘 뭐먹지

냉장고에 저장한 식재료, 선입선출 우선도, 현재 취향, 직전·최근 식사, 보유 양념과 조리 조건을 함께 반영하는 **규칙 기반 메뉴 추천 웹 애플리케이션**입니다.

> 이 프로젝트는 생성형 AI나 머신러닝 모델이 아니라, 공개된 기준과 프로젝트 정책으로 구성한 설명 가능한 가중치 추천 시스템입니다.

## 핵심 기능

- 식재료를 구매 묶음 단위로 등록·수정·삭제
- SQLite와 Docker volume을 이용한 영구 저장
- 표시기한, 개봉 경과, 구매 순서, 식품군 특성을 반영한 소비 우선도
- 냉장 보관보다 냉동 보관의 우선도를 낮추는 보정
- 식품군별 상태 질문과 추천 제외 처리
- 보유 양념장 영구 저장
- 음식 계열, 식사 형태, 조리시간, 조리기구 기반 추천
- 직전 식사와 내부 완료 이력을 이용한 반복 메뉴 감소
- 정확 일치 우선, 동등 대체 후순위의 순서 독립 재료 매칭
- 완전 일치 / 같은 계열 다른 형태 / 대체 계열 / 하나 더 필요한 메뉴 분리
- 추천 이유와 항목별 점수 공개
- 사용자 지정 우선 재료를 활용하는 메뉴를 별도 최우선 그룹으로 표시
- `이 메뉴로 먹었어요`에서 실제 사용량 입력 후 재고 차감 및 완료 카드 표시
- 빈 냉장고, 추천 후보 없음, 오래된 추천 결과 등의 예외 처리

## 아키텍처

```text
사용자 브라우저
  ↓ HTTP :80
Streamlit 프론트엔드
  ↓ Docker 내부 HTTP (http://back:8000)
FastAPI 백엔드
  ↓
SQLite 데이터베이스 + Docker volume
```

```text
식재료 등록/수정 → FastAPI CRUD → SQLite 저장
메뉴 추천 요청 → FastAPI 추천 엔진 → JSON 응답 → Streamlit 결과 표시
조리 완료 → 재료별 사용량 입력 → 재고 차감 → 같은 화면에서 반영 결과 표시
```

## 기술 스택

- Python
- Streamlit
- FastAPI
- Pydantic
- SQLite
- Docker / Docker Compose
- AWS EC2
- Git / GitHub

## 데이터

- 식재료 마스터: **69개**
- 양념: **32개**
- 레시피: **73개**
  - 한식 31개
  - 중식 12개
  - 일식 12개
  - 양식 18개

레시피와 식재료 데이터는 기능 검증을 위해 직접 구조화한 프로젝트 내부 시드이며, 레시피의 `source` 값은 `curated_internal_seed`입니다. 외부 공공데이터를 실시간으로 호출하지 않으므로 EC2 시연 중 외부 API 장애에 영향을 받지 않습니다.

## 추천 방식

추천 점수는 식품 안전 확률이 아니라 메뉴 후보 간 상대 순위를 정하는 정책 점수입니다.

균형 모드 기준:

| 항목 | 배점 |
|---|---:|
| 우선 재료 활용 | 35 |
| 재료·양념 충족 | 25 |
| 현재 취향 | 20 |
| 최근 식사 다양성 | 10 |
| 조리 편의성 | 10 |

추천 전 다음 조건은 점수 계산 전에 필터링합니다.

- 상태 확인 또는 사용자 제외 식재료
- 표시기한이 지난 식재료
- 필수 조리기구 부족
- 조리 가능 시간 초과
- 필수 재료가 둘 이상 부족한 메뉴

재료 매칭은 다음 순서를 사용합니다.

1. 모든 조건의 정확히 같은 재료를 먼저 배정
2. 남은 조건에만 동등 대체 재료 배정
3. 간이 대체는 완전 충족으로 계산하지 않고 경고 또는 부족 후보로 처리
4. 하나의 실제 재료는 여러 조건에 중복 배정하지 않음

세부 기준은 [추천 점수 정책](docs/SCORING_POLICY.md)을 참고하세요.

## 프로젝트 구조

```text
today-what-to-eat-final-fixed2/
├─ front/
│  ├─ app.py
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ .streamlit/config.toml
├─ back/
│  ├─ app/
│  ├─ seed/
│  ├─ sql/
│  ├─ scripts/
│  ├─ tests/
│  ├─ Dockerfile
│  ├─ requirements.txt
│  └─ requirements-dev.txt
├─ docs/
├─ scripts/
├─ docker-compose.yml
├─ LICENSE
└─ README.md
```

루트 `scripts/`는 호스트에서 실행하는 점검 도구이고, `back/scripts/`는 Docker 컨테이너 내부에서 사용하는 도구입니다.

## Docker로 실행

```bash
sudo docker compose build
sudo docker compose up -d
sudo docker compose ps
```

정상 상태:

```text
today-menu-back-fixed2    Up (healthy)
today-menu-front-fixed2   Up
```

상태 확인:

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
curl -I http://127.0.0.1
```

정상 핵심 응답:

```json
{
  "status": "ok",
  "database": "connected",
  "master_ingredients": 69,
  "recipes": 73,
  "seed_version": "2026-07-14-final-fixed2",
  "app_build": "final-fixed2"
}
```

브라우저:

```text
http://현재_EC2_퍼블릭_IP
```

상세 배포 절차는 [AWS EC2 배포 안내](docs/EC2_DEPLOY.md)를 참고하세요.

## 테스트

```bash
cd back
python -m pip install -r requirements-dev.txt
PYTHONPATH=. pytest -q
```

최종 자동 테스트는 다음을 포함합니다.

- 시드 자동 초기화
- 고아 식재료와 별칭 중복 검사
- 소비 우선도와 냉동 보정
- 직전 식사 제외와 식사 형태 그룹
- 대체 조리기구
- 크림 파스타·리소토·감자수프 정확 매칭 회귀 테스트
- 상태 정상화와 수량 0 삭제
- 사용자 지정 우선 재료 전용 추천 그룹
- 조리 완료 실제 사용량 검증

호스트 점검:

```bash
python3 scripts/check_orphan_ingredients.py
```

컨테이너 DB 확인:

```bash
sudo docker exec today-menu-back-fixed2 python /app/scripts/inspect_db.py
```

## 주요 API

```text
GET    /health
GET    /master/ingredients
GET    /ingredients
POST   /ingredients
PUT    /ingredients/{id}
DELETE /ingredients/{id}
GET    /seasonings
PUT    /seasonings
POST   /recommend
POST   /meals/complete
GET    /meals/history        # 최근 메뉴 반복 방지용 내부 이력 조회
POST   /demo/load
```

`/demo/load`는 과제 시연 편의를 위한 공개 엔드포인트입니다. 실제 서비스에서는 관리자 인증이나 접근 제한이 필요합니다.

`/meals/history`는 별도 사용자 화면을 제공하지 않으며, 같은 메뉴가 연속 추천되는 것을 줄이기 위한 내부 완료 이력으로만 사용합니다.

## 제한사항과 발전 방향

- 현재 재료 존재 여부 중심이며, 레시피 1인분 필요량과 단위 환산은 지원하지 않음
- 단일 사용자·단일 냉장고 구조
- 추천 당시 재고 스냅샷을 별도 `recommendation_id`로 저장하지 않음
- 식재료별 관리 구간은 소비 순서를 위한 정책값이며 식품 안전 기한이 아님
- 레시피 이미지는 포함하지 않음
- 공공 레시피 API 연동과 자동 정규화는 후속 과제

## 라이선스

MIT License. 자세한 내용은 [LICENSE](LICENSE)를 참고하세요.
