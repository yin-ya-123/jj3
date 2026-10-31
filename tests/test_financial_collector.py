"""财报采集服务测试（离线，临时库 + 假数据源）"""

from datetime import date

import pandas as pd
from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import sessionmaker

from data.collectors.financial_collector import FinancialCollector
from database.models import Base, FinancialReport
from database.repositories import financial_report_repository


REPORTS = pd.DataFrame(
    {
        "report_date": pd.to_datetime(["2026-06-30", "2026-09-30"]),
        "announce_date": pd.to_datetime(["2026-08-30", "2026-10-30"]),
        "roe": [15.0, 16.0],
        "total_assets": [100.0, 120.0],
    }
)


class FakeProvider:
    """假数据源，记录调用参数"""

    def __init__(self, reports=None, error=None):
        self.reports = reports
        self.error = error
        self.calls = []

    def get_financial_reports(self, symbol, start_date, end_date):
        self.calls.append((symbol, start_date, end_date))

        if self.error:
            raise self.error

        return self.reports


def _tmp_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)

    monkeypatch.setattr(financial_report_repository, "SessionLocal", session)

    return engine


def test_sync_stock_writes_reports(tmp_path, monkeypatch):
    engine = _tmp_session(tmp_path, monkeypatch)

    collector = FinancialCollector()
    collector.provider = FakeProvider(reports=REPORTS)

    result = collector.sync_stock("600519")

    assert result["status"] == "success"
    assert result["record_count"] == 2

    with engine.connect() as conn:
        rows = conn.execute(
            select(FinancialReport).order_by(FinancialReport.report_date)
        ).all()

    assert len(rows) == 2
    assert rows[0].stock_code == "600519"
    assert rows[0].roe == 15.0


def test_sync_stock_empty_reports_skipped(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    collector = FinancialCollector()
    collector.provider = FakeProvider(reports=pd.DataFrame())

    result = collector.sync_stock("600519")

    assert result["status"] == "skipped"
    assert result["record_count"] == 0


def test_sync_stock_provider_failure(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    collector = FinancialCollector()
    collector.provider = FakeProvider(error=RuntimeError("接口挂了"))

    result = collector.sync_stock("600519")

    assert result["status"] == "failed"
    assert result["record_count"] == 0
    assert "接口挂了" in result["message"]


def test_incremental_pulls_after_latest_report_date(tmp_path, monkeypatch):
    """增量起点被推到库内最新报告期的次日"""

    engine = _tmp_session(tmp_path, monkeypatch)

    with engine.begin() as conn:
        conn.execute(
            insert(FinancialReport).values(
                stock_code="600519",
                report_date=date(2026, 6, 30),
                announce_date=date(2026, 8, 30),
                roe=15.0,
            )
        )

    collector = FinancialCollector()
    collector.provider = FakeProvider(reports=REPORTS)

    result = collector.sync_stock(
        "600519",
        start_date="19900101",
        incremental=True,
    )

    assert result["status"] == "success"

    call = collector.provider.calls[0]

    # 起点应为 2026-06-30 的次日 20260701
    assert call[1] == "20260701"


def test_incremental_empty_db_keeps_start_date(tmp_path, monkeypatch):
    """库里没有该股票财报：增量退化为全量，起点不变"""

    _tmp_session(tmp_path, monkeypatch)

    collector = FinancialCollector()
    collector.provider = FakeProvider(reports=REPORTS)

    result = collector.sync_stock(
        "600519",
        start_date="20260101",
        incremental=True,
    )

    assert result["status"] == "success"

    call = collector.provider.calls[0]

    assert call[1] == "20260101"


def test_incremental_start_not_before_given_date(tmp_path, monkeypatch):
    """传入起点晚于库内最新报告期次日时，以入参为准"""

    engine = _tmp_session(tmp_path, monkeypatch)

    with engine.begin() as conn:
        conn.execute(
            insert(FinancialReport).values(
                stock_code="600519",
                report_date=date(2026, 6, 30),
                announce_date=date(2026, 8, 30),
            )
        )

    collector = FinancialCollector()
    collector.provider = FakeProvider(reports=REPORTS)

    collector.sync_stock(
        "600519",
        start_date="20270101",
        incremental=True,
    )

    call = collector.provider.calls[0]

    assert call[1] == "20270101"


def test_sync_stocks_summary(tmp_path, monkeypatch):
    engine = _tmp_session(tmp_path, monkeypatch)

    collector = FinancialCollector()
    collector.provider = FakeProvider(reports=REPORTS)

    results = collector.sync_stocks(
        ["600519", "000001"],
    )

    assert len(results) == 2
    assert all(item["status"] == "success" for item in results)

    with engine.connect() as conn:
        count = conn.execute(
            select(FinancialReport)
        ).scalars().all()

    assert len(count) == 4
