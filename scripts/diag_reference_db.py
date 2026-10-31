"""诊断：stock_reference 表结构与内容分布（只读）

用法：
    .venv\\Scripts\\python.exe scripts\\diag_reference_db.py
"""

from sqlalchemy import text

from database.db import DATABASE_PATH, engine


def main():
    print("数据库文件:", DATABASE_PATH)
    print("存在:", DATABASE_PATH.exists())

    if DATABASE_PATH.exists():
        print("大小:", DATABASE_PATH.stat().st_size, "字节")

    with engine.connect() as conn:
        print("\n---- 建表语句 ----")
        rows = conn.execute(
            text(
                "SELECT sql FROM sqlite_master "
                "WHERE tbl_name = 'stock_reference'"
            )
        ).all()

        for (sql,) in rows:
            print(sql)

        print("\n---- 行数 ----")
        print(
            "总行数:",
            conn.execute(
                text("SELECT COUNT(*) FROM stock_reference")
            ).scalar(),
        )
        print(
            "去重代码数:",
            conn.execute(
                text("SELECT COUNT(DISTINCT code) FROM stock_reference")
            ).scalar(),
        )

        print("\n---- market 分布 ----")
        for row in conn.execute(
            text(
                "SELECT market, COUNT(*) FROM stock_reference "
                "GROUP BY market ORDER BY 2 DESC"
            )
        ):
            print(row)

        print("\n---- 000 开头样本（撞码高发区）----")
        for row in conn.execute(
            text(
                "SELECT code, name, market FROM stock_reference "
                "WHERE code LIKE '000%' ORDER BY code LIMIT 30"
            )
        ):
            print(row)

        print("\n---- 非股票嫌疑行数 ----")
        print(
            conn.execute(
                text(
                    "SELECT COUNT(*) FROM stock_reference "
                    "WHERE name LIKE '%指数%' OR name LIKE '%ETF%' "
                    "OR name LIKE '%LOF%' OR name LIKE '%债%' "
                    "OR name LIKE '%基金%'"
                )
            ).scalar(),
        )

        print("\n---- 其他表行数（确认未被牵连）----")
        for table in ("stocks", "daily_bars", "data_sync_logs"):
            print(
                table,
                conn.execute(
                    text(f"SELECT COUNT(*) FROM {table}")
                ).scalar(),
            )


if __name__ == "__main__":
    main()