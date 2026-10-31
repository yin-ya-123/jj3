"""数据完整性检查仓储测试（阶段 3.4，离线临时库）"""

import importlib
from datetime import date

from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import sessionmaker

from database.models import Base, DailyBar, TradingCalendar
from database.repositories import (
    data_quality_repository as qrepo,
    trading_calendar_repository as calrepo,
)


def _tmp_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)

    monkeypatch.setattr(qrepo, "SessionLocal", session)
    monkeypatch.setattr(calrepo, "SessionLocal", session)

    return engine


def _seed_calendar(engine, days):
    """塞日历：days 为 [(date, is_trading_day), ...]"""

    with engine.begin() as conn:
        for day, flag in days:
            conn.execute(
                insert(TradingCalendar).values(
                    calendar_date=day,
                    is_trading_day=flag,
                )
            )


def _seed_bars(engine, code, rows):
    """塞日线：rows 为 [(date, trade_status), ...]"""

    with engine.begin() as conn:
        for day, status in rows:
            conn.execute(
                insert(DailyBar).values(
                    stock_code=code,
                    trade_date=day,
                    adjustflag="3",
                    close=10.0,
                    trade_status=status,
                )
            )


def _cal(day, flag=1):
    return (date(2026, 10, day), flag)


def test_missing_trading_days_reported(tmp_path, monkeypatch):
    """日历是交易日但库内无行 → 报缺失日"""

    engine = _tmp_session(tmp_path, monkeypatch)

    # 交易日：27/28/29/30，库内只有 27、30
    _seed_calendar(engine, [
        _cal(27), _cal(28), _cal(29), _cal(30),
    ])
    _seed_bars(engine, "600519", [
        (date(2026, 10, 27), "1"),
        (date(2026, 10, 30), "1"),
    ])

    result = qrepo.check_data_integrity(
        "600519", "2026-10-27", "2026-10-30"
    )

    assert result["trading_days"] == 4
    assert result["bar_count"] == 2
    assert result["missing_days"] == [
        date(2026, 10, 28),
        date(2026, 10, 29),
    ]
    assert result["suspension_days"] == []
    assert result["calendar_coverage"] is True


def test_suspension_days_reported(tmp_path, monkeypatch):
    """库内 trade_status='0' 的行 → 报停牌日"""

    engine = _tmp_session(tmp_path, monkeypatch)

    _seed_calendar(engine, [_cal(27), _cal(28), _cal(29)])
    _seed_bars(engine, "600519", [
        (date(2026, 10, 27), "1"),
        (date(2026, 10, 28), "0"),
        (date(2026, 10, 29), "1"),
    ])

    result = qrepo.check_data_integrity(
        "600519", "2026-10-27", "2026-10-29"
    )

    assert result["missing_days"] == []
    assert result["suspension_days"] == [date(2026, 10, 28)]


def test_complete_data_no_issues(tmp_path, monkeypatch):
    """数据完整：无缺失、无停牌、无未知状态"""

    engine = _tmp_session(tmp_path, monkeypatch)

    _seed_calendar(engine, [_cal(27), _cal(28)])
    _seed_bars(engine, "600519", [
        (date(2026, 10, 27), "1"),
        (date(2026, 10, 28), "1"),
    ])

    result = qrepo.check_data_integrity(
        "600519", "2026-10-27", "2026-10-28"
    )

    assert result["missing_days"] == []
    assert result["suspension_days"] == []
    assert result["unknown_status_rows"] == 0


def test_calendar_not_covered(tmp_path, monkeypatch):
    """日历未覆盖区间：不报缺失，calendar_coverage=False"""

    engine = _tmp_session(tmp_path, monkeypatch)

    _seed_bars(engine, "600519", [
        (date(2026, 10, 27), "1"),
    ])

    result = qrepo.check_data_integrity(
        "600519", "2026-10-01", "2026-10-30"
    )

    assert result["calendar_coverage"] is False
    assert result["trading_days"] == 0
    assert result["missing_days"] == []


def test_unknown_status_rows_counted(tmp_path, monkeypatch):
    """3.4 前存量行 trade_status=NULL → 统计进 unknown_status_rows"""

    engine = _tmp_session(tmp_path, monkeypatch)

    _seed_calendar(engine, [_cal(27), _cal(28)])
    _seed_bars(engine, "600519", [
        (date(2026, 10, 27), None),
        (date(2026, 10, 28), "1"),
    ])

    result = qrepo.check_data_integrity(
        "600519", "2026-10-27", "2026-10-28"
    )

    assert result["unknown_status_rows"] == 1
    assert result["suspension_days"] == []


def test_missing_days_ignores_weekend(tmp_path, monkeypatch):
    """日历中非交易日（周末）不算缺失"""

    engine = _tmp_session(tmp_path, monkeypatch)

    _seed_calendar(engine, [
        _cal(27, 1),  # 周一
        _cal(28, 1),  # 周二
        _cal(31, 0),  # 周六休市
    ])
    _seed_bars(engine, "600519", [
        (date(2026, 10, 27), "1"),
    ])

    result = qrepo.check_data_integrity(
        "600519", "2026-10-27", "2026-10-31"
    )

    assert result["trading_days"] == 2
    assert result["missing_days"] == [date(2026, 10, 28)]


def test_get_suspension_days_helper(tmp_path, monkeypatch):
    """独立接口 get_suspension_days 只报停牌日"""

    engine = _tmp_session(tmp_path, monkeypatch)

    _seed_bars(engine, "600519", [
        (date(2026, 10, 27), "1"),
        (date(2026, 10, 28), "0"),
    ])

    days = qrepo.get_suspension_days(
        "600519", "2026-10-27", "2026-10-28"
    )

    assert days == [date(2026, 10, 28)]
