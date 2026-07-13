# AWS Learner Lab EC2 배포 안내 V5

## 1. 로컬 GitHub 업로드

압축 해제한 V5 폴더에서:

```bash
git init
git branch -M main
git remote add origin https://github.com/wtpark/today-what-to-eat.git
git add .
git commit -m "feat: finalize recommendation logic and inventory UX"
git push -u origin main --force
```

remote가 이미 있으면:

```bash
git remote set-url origin https://github.com/wtpark/today-what-to-eat.git
git push -u origin main --force
```

## 2. EC2 강제 동기화

기존 이력이 갈라졌으므로 일반 `git pull` 대신 다음을 사용한다.

```bash
cd ~/today-what-to-eat
git fetch origin
git reset --hard origin/main
git clean -fd
```

## 3. 컨테이너 재빌드

```bash
sudo docker compose down
sudo docker compose build --no-cache
sudo docker compose up -d
sudo docker compose ps
```

`--no-cache`는 `docker compose build` 옵션이다. `docker compose up -d --build --no-cache`로 실행하지 않는다.

## 4. 상태 확인

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
curl -I http://127.0.0.1
```

정상 핵심 값:

```json
{
  "status": "ok",
  "database": "connected",
  "master_ingredients": 69,
  "recipes": 73,
  "seed_version": "2026-07-14-v5"
}
```

V4 Docker volume을 유지해도 새 컬럼이 자동 추가되고 기존 사용자 데이터는 보존된다.

## 5. 외부 접속

보안 그룹:

```text
HTTP / TCP / 80 / 0.0.0.0/0
SSH / TCP / 22 / 본인 접속 범위
```

브라우저:

```text
http://현재_퍼블릭_IP
```

Learner Lab에서 인스턴스를 중지했다 다시 시작하면 퍼블릭 IP가 바뀔 수 있다.

## 6. 연결 증명

추천 버튼을 누른 뒤:

```bash
sudo docker compose logs back --tail 50
```

다음 로그를 확인한다.

```text
POST /recommend HTTP/1.1 200 OK
```

추가 확인:

```bash
curl http://127.0.0.1:8000/openapi.json | head
```

## 7. 일반 업데이트에서 금지할 명령

```bash
sudo docker compose down -v
```

`-v`는 냉장고 재고, 양념 체크, 식사 이력을 모두 삭제한다. 완전 초기화가 필요할 때만 사용한다.

## 8. 배포 직후 수동 확인

1. 식재료 추가에서 표시기한 체크 시 날짜 입력란이 즉시 나타나는지
2. 표시기한 없는 채소에 관리 구간 설명이 표시되는지
3. 메뉴 결과가 완전 일치와 다른 식사 형태로 구분되는지
4. 우선 사용으로 지정한 재료가 추천 이유와 순위에 반영되는지
5. 조리 완료에서 실제 사용량 없이 제출할 수 없는지
