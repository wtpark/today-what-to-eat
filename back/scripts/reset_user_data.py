from __future__ import annotations

import os
import sqlite3
from pathlib import Path

path = Path(os.getenv("DB_PATH", "/app/data/today_menu.db"))
if not path.exists():
    raise SystemExit(f"DB 파일을 찾을 수 없습니다: {path}")

answer = input("재고·식사·추천 이력을 삭제합니다. 계속하려면 RESET 입력: ").strip()
if answer != "RESET":
    raise SystemExit("취소했습니다.")

conn = sqlite3.connect(path)
conn.execute("PRAGMA foreign_keys = ON")
conn.execute("BEGIN IMMEDIATE")
try:
    for table in ["inventory_usage", "meal_history", "recommendation_history", "inventory"]:
        conn.execute(f"DELETE FROM {table}")
    conn.commit()
except Exception:
    conn.rollback()
    raise
finally:
    conn.close()
print("사용자 데이터를 초기화했습니다. 마스터·레시피·양념 목록은 유지됩니다.")
