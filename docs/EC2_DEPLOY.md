# AWS Learner Lab EC2 배포 안내

## 1. GitHub 업로드

```bash
git add .
git commit -m "feat: complete today-what-to-eat app"
git push origin main
```

## 2. EC2 준비

- Learner Lab 시작
- EC2 인스턴스 실행
- 보안 그룹 인바운드 HTTP 80 확인
- 현재 퍼블릭 IPv4 확인

## 3. 프로젝트 받기

최초 배포:

```bash
cd ~
git clone https://github.com/wtpark/today-what-to-eat.git
cd today-what-to-eat
```

업데이트:

```bash
cd ~/today-what-to-eat
git pull --ff-only origin main
```

로컬 이력이 충돌하는 경우에만 변경사항을 백업한 뒤 문제 해결용으로 다음을 사용한다.

```bash
git fetch origin
git reset --hard origin/main
```

## 4. 기존 80번 컨테이너 종료

```bash
sudo docker ps
```

다른 프로젝트가 80번을 사용한다면 해당 프로젝트 폴더에서:

```bash
sudo docker compose down
```

## 5. 빌드·실행

```bash
sudo docker compose config
sudo docker compose build
sudo docker compose up -d
sudo docker compose ps
```

캐시 문제를 의심할 때만:

```bash
sudo docker compose build --no-cache
sudo docker compose up -d
```

## 6. 상태 확인

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
curl -I http://127.0.0.1
```

브라우저:

```text
http://현재_EC2_퍼블릭_IP
```

## 7. 통신 증명

추천 버튼을 누른 뒤:

```bash
sudo docker compose logs back --tail 50
```

확인할 로그:

```text
POST /recommend HTTP/1.1 200 OK
POST /meals/complete HTTP/1.1 201 Created
```

## 8. 데이터 보존

다음은 DB volume을 유지한다.

```bash
sudo docker compose down
sudo docker compose up -d
```

다음은 사용자 재고·양념·식사 기록까지 삭제하므로 일반 업데이트에서는 사용하지 않는다.

```bash
sudo docker compose down -v
```
