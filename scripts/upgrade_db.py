"""数据库结构升级：阶段 2 股票基础管理

用法（项目根目录执行）：
    uv run --no-sync python scripts/upgrade_db.py

做三件事：
    1. 备份 database/stockpilot.db 到 database/backups/
    2. stocks 表补 4 个字段（已存在自动跳过，可重复执行）
    3. 建 3 张新表：stock_groups / stock_group_members / stock_reference
"""

import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, text

from database.db import DATABASE_PATH, engine
from database.models import Base


# 阶段 2 需要给 stocks 表补的字段
NEW_COLUMNS = [
    ("is_active", "INTEGER NOT NULL DEFAULT 1"),
    ("industry", "VARCHAR(50)"),
    ("ipo_date", "DATE"),
    ("updated_at", "DATETIME"),
]


def backup_db() -> Path:
    """备份数据库文件，返回备份路径"""

    backup_dir = DATABASE_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"stockpilot_{stamp}.db"

    shutil.copy2(DATABASE_PATH, target)

    return target


def add_missing_columns() -> list:
    """给 stocks 表补字段，已存在的字段自动跳过"""

    existing = {
        column["name"]
        for column in inspect(engine).get_columns("stocks")
    }

    added = []

    with engine.begin() as conn:
        for name, ddl in NEW_COLUMNS:
            if name in existing:
                continue

            conn.execute(text(f"ALTER TABLE stocks ADD COLUMN {name} {ddl}"))
            added.append(name)

    return added


def main() -> None:
    print(f"数据库文件：{DATABASE_PATH}")

    if not DATABASE_PATH.exists():
        print("数据库文件不存在，请先执行 sync_stocks.py 生成数据")
        return

    #1. 备份
    backup = backup_db()
    print(f"[1/3] 备份完成：{backup}")

    # 2. 补字段
    added = add_missing_columns()
    print(f"[2/3] stocks 新增字段：{added if added else '无（已是最新）'}")

    # 3. 建新表（只建缺失的表，不动已有的表）
    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()
    print(f"[3/3] 当前数据表：{tables}")

    # 校验
    with engine.connect() as conn:
        stocks = conn.execute(text("SELECT COUNT(*) FROM stocks")).scalar()
        bars = conn.execute(text("SELECT COUNT(*) FROM daily_bars")).scalar()
        active = conn.execute(
            text("SELECT COUNT(*) FROM stocks WHERE is_active = 1")
        ).scalar()

    print(f"校验：stocks={stocks}（有效 {active}），daily_bars={bars}")
    print("升级完成")


if __name__ == "__main__":
    main()