from __future__ import annotations

import os
import sqlite3
from pathlib import Path

path = Path(os.getenv("DB_PATH", "back/data/today_menu.db"))
if not path.exists():
    raise SystemExit(f"DB 파일을 찾을 수 없습니다: {path}")

conn = sqlite3.connect(path)
print(f"DB: {path.resolve()}")
print("\n[테이블]")
for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"):
    print("-", row[0])

print("\n[개수]")
for table in ["ingredient_master", "inventory", "seasonings", "recipes", "meal_history", "recommendation_history"]:
    count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
    print(f"{table}: {count}")
