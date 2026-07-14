# AWS Learner Lab EC2 배포 안내

## 이번 보완판 식별자

- 압축 해제 폴더: `today-what-to-eat-final-fixed2`
- Docker 이미지: `today-what-to-eat-front:final-fixed2`, `today-what-to-eat-back:final-fixed2`
- 컨테이너: `today-menu-front-fixed2`, `today-menu-back-fixed2`
- health: `seed_version=2026-07-14-final-fixed2`, `app_build=final-fixed2`

새 태그를 사용하므로 빌드가 실패했을 때 과거 이미지를 새 코드처럼 다시 실행하지 않습니다.

## 1. GitHub 업로드

기존 Git 저장소 폴더에 이 폴더의 내용을 덮어쓴 뒤:

```bash
git add -A
git commit -m "fix: deploy final fixed2 build"
git pull --rebase origin main
git push origin main
```

## 2. EC2 코드 동기화

```bash
cd ~/today-what-to-eat
git fetch origin
git reset --hard origin/main
git clean -fd
```

파일 확인:

```bash
grep -R "final-fixed2" docker-compose.yml back/app/database.py front/app.py
```

## 3. 디스크 공간 확인 및 안전한 정리

이전 빌드에서 `No space left on device`가 발생했다면 먼저 실행합니다.

```bash
df -h
sudo docker system df
```

기존 컨테이너를 내리되 DB volume은 삭제하지 않습니다.

```bash
sudo docker rm -f today-menu-front today-menu-back today-menu-front-fixed2 today-menu-back-fixed2 2>/dev/null || true
```

사용하지 않는 Docker 빌드 캐시·이미지·컨테이너를 정리합니다. **volume은 삭제하지 않습니다.**

```bash
sudo docker builder prune -af
sudo docker system prune -af
```

다음 명령은 재고 DB까지 삭제하므로 사용하지 않습니다.

```bash
sudo docker system prune -af --volumes
sudo docker compose down -v
```

## 4. 빌드와 실행

```bash
sudo docker compose config
sudo docker compose build --pull
```

`Built`가 표시되고 명령이 정상 종료된 경우에만 실행합니다.

```bash
sudo docker compose up -d
sudo docker compose ps
```

빌드가 실패했는데 `up -d`를 실행해 과거 이미지를 확인하는 방식은 사용하지 않습니다.

한 번에 실행하려면:

```bash
bash scripts/deploy_fixed2_ec2.sh
```

## 5. 최종 확인

```bash
curl -s http://127.0.0.1:8000/health | python3 -m json.tool
```

반드시 다음 값이 나와야 합니다.

```json
{
  "seed_version": "2026-07-14-final-fixed2",
  "app_build": "final-fixed2"
}
```

컨테이너 이름 확인:

```bash
sudo docker ps --format 'table {{.Names}}\t{{.Image}}\t{{.Status}}\t{{.Ports}}'
```

정상 예시:

```text
today-menu-back-fixed2    today-what-to-eat-back:final-fixed2     Up (healthy)
today-menu-front-fixed2   today-what-to-eat-front:final-fixed2    Up
```

브라우저에서 확인:

- 상단 메뉴에 `식사 기록`이 없어야 함
- 사이드바에 `빌드: final-fixed2` 표시
- 당면을 우선 사용으로 지정한 뒤 조건을 만족하면 `사용자 지정 우선 재료 활용 메뉴`가 일반 결과보다 먼저 표시
- 재고 반영 후 별도 식사 기록 페이지로 이동하지 않고 같은 페이지 하단에 `재고 반영 완료` 카드 표시
