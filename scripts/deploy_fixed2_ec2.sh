#!/usr/bin/env bash
set -euo pipefail

cd "$(dirname "$0")/.."

echo "[1/6] Stop old containers without deleting the DB volume"
sudo docker rm -f today-menu-front today-menu-back today-menu-front-fixed2 today-menu-back-fixed2 2>/dev/null || true

echo "[2/6] Docker disk usage before cleanup"
sudo docker system df || true

echo "[3/6] Remove unused build cache/images/containers (volumes are preserved)"
sudo docker builder prune -af
sudo docker system prune -af

echo "[4/6] Build fixed2 images"
sudo docker compose build --pull

echo "[5/6] Start only after the build succeeds"
sudo docker compose up -d

echo "[6/6] Verify"
sudo docker compose ps
curl -fsS http://127.0.0.1:8000/health | python3 -m json.tool
