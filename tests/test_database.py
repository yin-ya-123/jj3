
from sqlalchemy import inspect

from database.db import engine, init_db


def test_database_initialization():
    init_db()

    inspector = inspect(engine)

    tables = inspector.get_table_names()

    assert "stocks" in tables
    assert "daily_bars" in tables
    assert "data_sync_logs" in tables

    print("\nStockPilot 数据库初始化成功")
    print("数据表:", tables)
