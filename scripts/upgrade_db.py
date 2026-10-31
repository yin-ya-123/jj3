"""数据库结构升级：阶段 2 股票基础管理 + 阶段 3 行情与数据中心

用法（项目根目录执行）：
    .venv\\Scripts\\python.exe scripts\\upgrade_db.py

做五件事：
    1. 备份 database/stockpilot.db 到 database/backups/
    2. stocks 表补 4 个字段（阶段 2，已存在自动跳过）
    3. data_sync_logs 表补 2 个字段（阶段 3：period / adjustflag）
    4. daily_bars 表补 trade_status 字段（阶段 3.4：tradestatus 落库）
    5. 建缺失的表（bars / adjust_factors / stock_groups / stock_reference /
       financial_reports ...）

脚本可重复执行：已有字段、已有表都会跳过。
"""

import shutil
import sys
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, text

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from database.db import DATABASE_PATH, engine
from database.models import Base


# stocks 表补的字段（阶段 2）
STOCKS_COLUMNS = [
    ("is_active", "INTEGER NOT NULL DEFAULT 1"),
    ("industry", "VARCHAR(50)"),
    ("ipo_date", "DATE"),
    ("updated_at", "DATETIME"),
]

# data_sync_logs 表补的字段（阶段 3）
# adjustflag 的旧行默认值给 '2'：迁移前库里只有前复权口径的数据
# （daily_bars 594 行全是 adjustflag='2'），老日志标成 '3' 等于伪造历史。
# 新写入的日志由 ORM 显式赋值，不吃这个默认值。
SYNC_LOG_COLUMNS = [
    ("period", "VARCHAR(5) NOT NULL DEFAULT 'd'"),
    ("adjustflag", "VARCHAR(1) NOT NULL DEFAULT '2'"),
]

# daily_bars 表补的字段（阶段 3.4）
# trade_status：Baostock tradestatus（'1'=正常交易 '0'=停牌）。
# 存量行保持 NULL（未知），由完整性检查脚本提示重采回填。
DAILY_BAR_COLUMNS = [
    ("trade_status", "VARCHAR(2)"),
]


def backup_db() -> Path:
    """备份数据库文件，返回备份路径"""

    backup_dir = DATABASE_PATH.parent / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)

    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    target = backup_dir / f"stockpilot_{stamp}.db"

    shutil.copy2(DATABASE_PATH, target)

    return target


def add_missing_columns(table: str, columns: list) -> list:
    """给表补字段，已存在的字段自动跳过"""

    inspector = inspect(engine)

    if table not in inspector.get_table_names():
        return []

    existing = {
        column["name"]
        for column in inspector.get_columns(table)
    }

    added = []

    with engine.begin() as conn:
        for name, ddl in columns:
            if name in existing:
                continue

            conn.execute(text(f"ALTER TABLE {table} ADD COLUMN {name} {ddl}"))
            added.append(name)

    return added


def main() -> None:
    print(f"数据库文件：{DATABASE_PATH}")

    if not DATABASE_PATH.exists():
        print("数据库文件不存在，请先执行采集脚本生成数据")
        return

    # 1. 备份
    backup = backup_db()
    print(f"[1/5] 备份完成：{backup}")

    # 2. stocks 补字段
    added = add_missing_columns("stocks", STOCKS_COLUMNS)
    print(f"[2/5] stocks 新增字段：{added if added else '无（已是最新）'}")

    # 3. 同步日志补字段
    added = add_missing_columns("data_sync_logs", SYNC_LOG_COLUMNS)
    print(f"[3/5] data_sync_logs 新增字段：{added if added else '无（已是最新）'}")

    # 4. daily_bars 补字段（阶段 3.4：tradestatus 落库）
    added = add_missing_columns("daily_bars", DAILY_BAR_COLUMNS)
    print(f"[4/5] daily_bars 新增字段：{added if added else '无（已是最新）'}")

    # 5. 建缺失的表（只建缺失的，不动已有的表）
    Base.metadata.create_all(bind=engine)
    tables = inspect(engine).get_table_names()
    print(f"[5/5] 当前数据表：{tables}")

    # 校验
    with engine.connect() as conn:
        stocks = conn.execute(text("SELECT COUNT(*) FROM stocks")).scalar()
        bars = conn.execute(text("SELECT COUNT(*) FROM daily_bars")).scalar()
        logs = conn.execute(text("SELECT COUNT(*) FROM data_sync_logs")).scalar()
        active = conn.execute(
            text("SELECT COUNT(*) FROM stocks WHERE is_active = 1")
        ).scalar()
        raw = conn.execute(
            text("SELECT COUNT(*) FROM daily_bars WHERE adjustflag = '3'")
        ).scalar()
        has_financial_reports = "financial_reports" in tables

    print(
        f"校验：stocks={stocks}（有效 {active}），"
        f"daily_bars={bars}（不复权 {raw}），同步日志={logs}，"
        f"financial_reports={'已建' if has_financial_reports else '未建'}"
    )
    print("升级完成")


if __name__ == "__main__":
    main()
