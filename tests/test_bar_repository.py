"""多周期行情（分钟线）仓储测试（离线，用临时库）"""

import pandas as pd
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base
from database.repositories import bar_repository as repo


def _tmp_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(repo, "SessionLocal", sessionmaker(bind=engine))


def _frame(times=None):
    if times is None:
        times = ["2026-10-27 09:35:00", "2026-10-27 09:40:00"]

    return pd.DataFrame(
        {
            "trade_time": pd.to_datetime(times),
            "open": [1.0] * len(times),
            "high": [2.0] * len(times),
            "low": [0.5] * len(times),
            "close": [1.5] * len(times),
            "volume": [100.0] * len(times),
            "amount": [1000.0] * len(times),
        }
    )


def test_save_bars_then_read_back(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    count = repo.save_bars(_frame(), "600519", "5")

    assert count == 2

    bars = repo.get_bars("600519", period="5")

    assert len(bars) == 2
    assert bars[0].stock_code == "600519"
    assert bars[0].period == "5"
    assert bars[0].close == 1.5


def test_save_bars_twice_updates_not_duplicates(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    repo.save_bars(_frame(), "600519", "5")
    repo.save_bars(_frame(), "600519", "5")

    assert len(repo.get_bars("600519", period="5")) == 2


def test_different_periods_are_independent(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    repo.save_bars(_frame(), "600519", "5")
    repo.save_bars(_frame(), "600519", "15")

    assert len(repo.get_bars("600519", period="5")) == 2
    assert len(repo.get_bars("600519", period="15")) == 2


def test_reject_non_minute_period(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    try:
        repo.save_bars(_frame(), "600519", "d")
    except ValueError as exc:
        assert "分钟线" in str(exc)
    else:
        raise AssertionError("日线周期应被拒绝")


def test_reject_invalid_code(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    try:
        repo.save_bars(_frame(), "abc", "5")
    except ValueError:
        pass
    else:
        raise AssertionError("非法代码应被拒绝")


def test_empty_frame_returns_zero(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    assert repo.save_bars(pd.DataFrame(), "600519", "5") == 0


def test_trade_time_floored_to_second(tmp_path, monkeypatch):
    """毫秒精度必须规整到秒，否则唯一约束匹配不上，会插出重复行"""

    _tmp_session(tmp_path, monkeypatch)

    df = pd.DataFrame(
        {
            "trade_time": pd.to_datetime(["2026-10-27 09:35:00.123456"]),
            "open": [1.0],
            "high": [2.0],
            "low": [0.5],
            "close": [1.5],
            "volume": [100.0],
            "amount": [1000.0],
        }
    )

    repo.save_bars(df, "600519", "5")
    repo.save_bars(df, "600519", "5")

    assert len(repo.get_bars("600519", period="5")) == 1
