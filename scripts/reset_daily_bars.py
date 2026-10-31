# -*- coding: utf-8 -*-
"""清空旧口径日线数据（破坏性，需人工确认）

背景：
    库里现有 daily_bars 是旧口径（adjustflag='2'，前复权价）。
    前复权价会随除权整体漂移，不能做增量同步，必须换成不复权原始价。
    新旧口径混在一张表里会变成两个真相源，所以要先清空再重采。

用法（项目根目录）：
    .venv\\Scripts\\python.exe scripts\\reset_daily_bars.py

建议先跑 scripts/upgrade_db.py 生成备份。
"""

import sqlite3
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from database.db import DATABASE_PATH

BACKUP_DIR = DATABASE_PATH.parent / "backups"


def main():
    conn = sqlite3.connect(DATABASE_PATH)

    total = conn.execute(
        "select count(*) from daily_bars"
    ).fetchone()[0]

    old = conn.execute(
        "select count(*) from daily_bars where adjustflag='2'"
    ).fetchone()[0]

    print(f"数据库：{DATABASE_PATH}")
    print(f"daily_bars 总行数：{total}")
    print(f"其中旧口径（adjustflag='2'）：{old}")

    if old == 0:
        print("没有旧口径数据，无需清理")
        conn.close()
        return

    backups = (
        sorted(BACKUP_DIR.glob("stockpilot_*.db"))
        if BACKUP_DIR.exists()
        else []
    )

    if backups:
        print(f"最近备份：{backups[-1].name}")
    else:
        print("警告：没有找到备份，建议先执行 scripts/upgrade_db.py")

    answer = input(f"确认删除这 {old} 行？输入 YES 继续：").strip()

    if answer != "YES":
        print("已取消")
        conn.close()
        return

    conn.execute("delete from daily_bars where adjustflag='2'")
    conn.commit()

    left = conn.execute(
        "select count(*) from daily_bars"
    ).fetchone()[0]

    conn.close()

    print(f"清理完成，daily_bars 剩余 {left} 行")


if __name__ == "__main__":
    main()
