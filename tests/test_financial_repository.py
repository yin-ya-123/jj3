"""财报仓储测试（离线，用临时库）"""

import pandas as pd
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker

from database.models import Base, FinancialReport, Stock
from database.repositories import financial_report_repository as repo


def _tmp_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(repo, "SessionLocal", sessionmaker(bind=engine))
    return engine


def _frame():
    return pd.DataFrame(
        {
            "report_date": pd.to_datetime(
                ["2026-06-30", "2026-09-30"]
            ),
            "announce_date": pd.to_datetime(
                ["2026-08-30", "2026-10-30"]
            ),
            "roe": [15.0, 16.0],
            "total_assets": [100.0, 120.0],
            "operate_income": [50.0, 60.0],
            "netcash_operate": [10.0, 20.0],
        }
    )


def test_save_financial_reports_then_read_back(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    assert repo.save_financial_reports(_frame(), "600519") == 2

    reports = repo.get_financial_reports("600519", limit=10)

    assert len(reports) == 2
    assert reports[0].stock_code == "600519"
    # 倒序：最新报告期在前
    assert str(reports[0].report_date) == "2026-09-30"
    assert reports[0].roe == 16.0
    assert reports[1].announce_date is not None


def test_save_financial_reports_does_not_create_stock(tmp_path, monkeypatch):
    """采集财报不得污染用户的自选池"""

    engine = _tmp_session(tmp_path, monkeypatch)

    repo.save_financial_reports(_frame(), "600519")

    with engine.connect() as conn:
        stock_rows = conn.execute(select(Stock)).all()

    assert stock_rows == []


def test_save_twice_updates_not_duplicates(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    repo.save_financial_reports(_frame(), "600519")
    repo.save_financial_reports(_frame(), "600519")

    assert len(repo.get_financial_reports("600519", limit=10)) == 2


def test_save_updates_existing_report_period(tmp_path, monkeypatch):
    """同一报告期重复写入（财报修订）应更新指标而非报错"""

    _tmp_session(tmp_path, monkeypatch)

    repo.save_financial_reports(_frame(), "600519")

    revised = _frame().copy()
    revised.loc[revised["report_date"] == "2026-06-30", "roe"] = 99.0

    repo.save_financial_reports(revised, "600519")

    reports = repo.get_financial_reports("600519", limit=10)

    assert len(reports) == 2

    june = next(
        item for item in reports
        if str(item.report_date) == "2026-06-30"
    )

    assert june.roe == 99.0


def test_get_latest_report_date(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    assert repo.get_latest_report_date("600519") is None

    repo.save_financial_reports(_frame(), "600519")

    assert str(repo.get_latest_report_date("600519")) == "2026-09-30"


def test_reject_invalid_code(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    try:
        repo.save_financial_reports(_frame(), "abc")
    except ValueError:
        pass
    else:
        raise AssertionError("非法代码应被拒绝")


def test_empty_frame_returns_zero(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    assert repo.save_financial_reports(pd.DataFrame(), "600519") == 0


def test_missing_report_date_row_skipped(tmp_path, monkeypatch):
    """缺报告期的行不落库"""

    _tmp_session(tmp_path, monkeypatch)

    frame = _frame().copy()
    frame.loc[1, "report_date"] = pd.NaT

    assert repo.save_financial_reports(frame, "600519") == 1

    assert len(repo.get_financial_reports("600519", limit=10)) == 1


def test_missing_columns_become_none(tmp_path, monkeypatch):
    """宽表缺某些指标列不报错，落 None"""

    _tmp_session(tmp_path, monkeypatch)

    frame = pd.DataFrame(
        {
            "report_date": pd.to_datetime(["2026-06-30"]),
            "announce_date": pd.to_datetime(["2026-08-30"]),
            "roe": [15.0],
        }
    )

    repo.save_financial_reports(frame, "600519")

    report = repo.get_financial_reports("600519", limit=10)[0]

    assert report.roe == 15.0
    assert report.net_profit is None
    assert report.netcash_operate is None
