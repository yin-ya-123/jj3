"""交易日历仓储测试（离线，临时库）"""

import importlib
from datetime import date

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database.models import Base, TradingCalendar


def _repo(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'cal.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)

    module = importlib.import_module(
        "database.repositories.trading_calendar_repository"
    )

    monkeypatch.setattr(module, "SessionLocal", session)

    return module, engine


def test_save_and_query(tmp_path, monkeypatch):
    """写入后能按区间取到交易日，非交易日不算"""

    repo, _ = _repo(tmp_path, monkeypatch)

    df = pd.DataFrame(
        {
            "calendar_date": pd.to_datetime(["2026-10-30", "2026-10-31"]),
            "is_trading_day": [1, 0],
        }
    )

    assert repo.save_trade_dates(df) == 2
    assert repo.get_trading_days(
        "2026-10-01", "2026-10-31"
    ) == [date(2026, 10, 30)]
    assert repo.has_trading_day("2026-10-30", "2026-10-31") is True
    assert repo.has_trading_day("2026-10-31", "2026-10-31") is False


def test_save_is_idempotent(tmp_path, monkeypatch):
    """同一天重复同步是覆盖，不是重复插入"""

    repo, engine = _repo(tmp_path, monkeypatch)

    df = pd.DataFrame(
        {
            "calendar_date": pd.to_datetime(["2026-10-31"]),
            "is_trading_day": [0],
        }
    )

    repo.save_trade_dates(df)

    df2 = df.copy()
    df2["is_trading_day"] = [1]

    repo.save_trade_dates(df2)

    with engine.connect() as conn:
        rows = conn.execute(select(TradingCalendar)).all()

    assert len(rows) == 1
    assert rows[0].is_trading_day == 1


def test_unknown_range_is_not_blocked(tmp_path, monkeypatch):
    """日历没覆盖的区间不能拦截，返回 True 让调用方照常请求数据源"""

    repo, _ = _repo(tmp_path, monkeypatch)

    assert repo.has_trading_day("2030-01-01", "2030-01-31") is True
