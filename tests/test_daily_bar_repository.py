"""日线仓储测试（离线，用临时库）"""

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database.models import Base, Stock
from database.repositories import daily_bar_repository as repo


def _tmp_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(repo, "SessionLocal", sessionmaker(bind=engine))
    return engine


def _frame():
    return pd.DataFrame(
        {
            "date": ["2026-10-27", "2026-10-28"],
            "open": [10.0, 11.0],
            "high": [12.0, 13.0],
            "low": [9.0, 10.0],
            "close": [11.0, 12.0],
            "preclose": [10.5, 11.5],
            "volume": [100.0, 200.0],
            "amount": [1000.0, 2000.0],
            "turn": [0.5, 0.6],
            "pctChg": [1.0, 2.0],
        }
    )


def test_save_daily_bars_then_read_back(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    assert repo.save_daily_bars(_frame(), "600519", adjustflag="3") == 2

    bars = repo.get_daily_bars("600519", limit=10, adjustflag="3")

    assert len(bars) == 2
    assert bars[0].stock_code == "600519"
    assert bars[0].close == 12.0


def test_save_daily_bars_does_not_create_stock(tmp_path, monkeypatch):
    """采集行情不得污染用户的自选池"""

    engine = _tmp_session(tmp_path, monkeypatch)

    repo.save_daily_bars(_frame(), "600519", adjustflag="3")

    with engine.connect() as conn:
        stock_rows = conn.execute(select(Stock)).all()

    assert stock_rows == []


def test_save_twice_updates_not_duplicates(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    repo.save_daily_bars(_frame(), "600519", adjustflag="3")
    repo.save_daily_bars(_frame(), "600519", adjustflag="3")

    assert len(repo.get_daily_bars("600519", limit=10, adjustflag="3")) == 2


def test_different_adjustflag_can_coexist(tmp_path, monkeypatch):
    """唯一约束含 adjustflag，不同口径的行可以并存"""

    _tmp_session(tmp_path, monkeypatch)

    repo.save_daily_bars(_frame(), "600519", adjustflag="3")
    repo.save_daily_bars(_frame(), "600519", adjustflag="2")

    assert len(repo.get_daily_bars("600519", limit=10, adjustflag="3")) == 2
    assert len(repo.get_daily_bars("600519", limit=10, adjustflag="2")) == 2


def test_reject_invalid_code(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    try:
        repo.save_daily_bars(_frame(), "abc")
    except ValueError:
        pass
    else:
        raise AssertionError("非法代码应被拒绝")


def test_empty_frame_returns_zero(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    assert repo.save_daily_bars(pd.DataFrame(), "600519") == 0
