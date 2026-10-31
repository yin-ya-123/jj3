"""将 models.py 中的表/字段注释持久化到 SQLite 的 schema_comments 表。

SQLite 本身不支持 COMMENT 语法（MySQL/Oracle 的 COMMENT ON 无法使用），
本项目约定：
- ORM 模型（database/models.py）用 __table_args__['comment'] 与
  mapped_column(comment=...) 声明表/字段注释；
- 本脚本读取这些元数据，写入数据库中的 schema_comments 元数据表
  （column_name 为 NULL 的行表示表注释），可重复执行，UPSERT 语义。

用法：
    python scripts/apply_comments.py [数据库路径]

默认数据库路径：D:\\cs\\python\\qt\\Jj3\\database\\stockpilot.db
"""

from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from sqlalchemy import create_engine, func, select
from sqlalchemy.dialects.sqlite import insert

from database.models import Base, SchemaComment

DEFAULT_DB = PROJECT_ROOT / "database" / "stockpilot.db"


def main(db_path: str | Path = DEFAULT_DB) -> None:
    engine = create_engine(f"sqlite:///{db_path}")
    # 确保 schema_comments 表存在（其余业务表已存在则不动，仅补缺表）
    Base.metadata.create_all(engine)

    rows: list[dict] = []
    skipped = {"schema_comments"}
    for name, table in Base.metadata.tables.items():
        if name in skipped:
            continue
        if table.comment:
            rows.append(
                {
                    "table_name": name,
                    "column_name": None,
                    "comment": table.comment,
                }
            )
        for col in table.columns:
            if col.comment:
                rows.append(
                    {
                        "table_name": name,
                        "column_name": col.name,
                        "comment": col.comment,
                    }
                )

    if not rows:
        print("没有可写入的注释（models.py 中未声明任何 comment）。")
        return

    with engine.begin() as conn:
        for row in rows:
            stmt = insert(SchemaComment).values(**row)
            stmt = stmt.on_conflict_do_update(
                index_elements=["table_name", "column_name"],
                set_={
                    "comment": stmt.excluded.comment,
                    "updated_at": func.current_timestamp(),
                },
            )
            conn.execute(stmt)

        total = conn.scalar(
            select(func.count()).select_from(SchemaComment)
        )
        table_comments = conn.scalar(
            select(func.count())
            .select_from(SchemaComment)
            .where(SchemaComment.column_name.is_(None))
        )
        column_comments = conn.scalar(
            select(func.count())
            .select_from(SchemaComment)
            .where(SchemaComment.column_name.is_not(None))
        )

    print(f"写入完成：表注释 {table_comments} 条，字段注释 {column_comments} 条，合计 {total} 条。")
    print(f"数据库：{db_path}")
    print("查询示例：SELECT table_name, column_name, comment FROM schema_comments ORDER BY table_name, column_name;")


if __name__ == "__main__":
    arg = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_DB
    main(arg)
