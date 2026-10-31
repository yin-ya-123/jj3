"""同步服务层测试（阶段 3.5，离线）

覆盖：
    ensure_calendar_cover   已覆盖 / 已补齐 / 已初始化 三分支
    run_daily_sync          参数透传、汇总统计、日历保障开关
    get_sync_logs           同步日志排序与字段（dashboard_repository）
"""

from datetime import date, datetime

from sqlalchemy import create_engine, insert
from sqlalchemy.orm import sessionmaker

from data import sync_service
from database.models import Base, DataSyncLog
from database.repositories import dashboard_repository as dashrepo


class FakeCollector:
    """模拟采集器：记录调用，返回固定结果"""

    def __init__(self):
        self.sync_calls = []
        self.calendar_calls = []

    def sync_stocks(self, **kwargs):
        self.sync_calls.append(kwargs)

        return [
            {"stock_code": "600519", "status": "success",
             "record_count": 5, "message": ""},
            {"stock_code": "000001", "status": "skipped",
             "record_count": 0, "message": "无新数据"},
            {"stock_code": "000002", "status": "failed",
             "record_count": 0, "message": "网络错误"},
        ]

    def sync_calendar(self, start, end):
        self.calendar_calls.append((start, end))


def _seed_calendar_max(monkeypatch, max_date):
    monkeypatch.setattr(
        sync_service,
        "get_max_calendar_date",
        lambda: max_date,
    )


def test_calendar_already_covered(monkeypatch):
    """日历最大日期 >= 结束日 → 已覆盖，不联网"""

    collector = FakeCollector()
    _seed_calendar_max(monkeypatch, date(2026, 10, 30))

    note = sync_service.ensure_calendar_cover(collector, "2026-10-20")

    assert note == "已覆盖"
    assert collector.calendar_calls == []


def test_calendar_backfilled(monkeypatch):
    """日历不足 → 从最大日的次日补齐到结束日"""

    collector = FakeCollector()
    _seed_calendar_max(monkeypatch, date(2026, 10, 25))

    note = sync_service.ensure_calendar_cover(collector, "2026-10-30")

    assert note == "已补齐"
    assert collector.calendar_calls == [("2026-10-26", "2026-10-30")]


def test_calendar_initialized(monkeypatch):
    """日历表为空 → 全量初始化 1990-01-01 起"""

    collector = FakeCollector()
    _seed_calendar_max(monkeypatch, None)

    note = sync_service.ensure_calendar_cover(collector, "2026-10-30")

    assert note == "已初始化"
    assert collector.calendar_calls == [("1990-01-01", "2026-10-30")]


def test_run_daily_sync_passthrough_and_summary(monkeypatch):
    """参数透传 + 汇总统计 + 不开日历保障时 calendar=None"""

    collector = FakeCollector()
    _seed_calendar_max(monkeypatch, date(2026, 10, 30))

    result = sync_service.run_daily_sync(
        codes=["600519", "000001", "000002"],
        start="2026-01-01",
        end="2026-10-30",
        period="d",
        adjustflag="3",
        with_factors=False,
        incremental=True,
        ensure_calendar=False,
        collector=collector,
    )

    # 参数透传
    call = collector.sync_calls[0]

    assert call["symbols"] == ["600519", "000001", "000002"]
    assert call["start_date"] == "2026-01-01"
    assert call["end_date"] == "2026-10-30"
    assert call["period"] == "d"
    assert call["adjustflag"] == "3"
    assert call["with_factors"] is False
    assert call["incremental"] is True

    # 汇总
    assert result["mode"] == "incremental"
    assert result["calendar"] is None
    assert result["summary"] == {
        "total": 3,
        "success": 1,
        "skipped": 1,
        "failed": 1,
        "period_name": "日线",
    }


def test_run_daily_sync_with_calendar(monkeypatch):
    """开日历保障 → 先补日历再采集"""

    collector = FakeCollector()
    _seed_calendar_max(monkeypatch, date(2026, 10, 1))

    result = sync_service.run_daily_sync(
        codes=["600519"],
        start="2026-10-01",
        end="2026-10-30",
        ensure_calendar=True,
        collector=collector,
    )

    assert collector.calendar_calls == [("2026-10-02", "2026-10-30")]
    assert result["calendar"] == "已补齐"


def test_get_sync_logs_order_and_fields(tmp_path, monkeypatch):
    """日志按创建时间倒序，字段映射完整"""

    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)

    monkeypatch.setattr(dashrepo, "SessionLocal", session)

    with session() as s:
        s.add(DataSyncLog(
            stock_code="600519",
            start_date="2026-10-01",
            end_date="2026-10-30",
            period="d",
            adjustflag="3",
            record_count=20,
            status="success",
            message="完成",
            created_at=datetime(2026, 10, 31, 10, 0),
        ))
        s.add(DataSyncLog(
            stock_code="000001",
            start_date="2026-10-01",
            end_date="2026-10-29",
            period="5",
            adjustflag="3",
            record_count=0,
            status="failed",
            message="网络错误",
            created_at=datetime(2026, 10, 31, 9, 0),
        ))
        s.commit()

    logs = dashrepo.get_sync_logs(limit=10)

    assert len(logs) == 2
    assert logs[0]["股票代码"] == "600519"
    assert logs[0]["记录数量"] == 20
    assert logs[0]["状态"] == "success"
    assert logs[1]["周期"] == "5"
    assert logs[1]["说明"] == "网络错误"
