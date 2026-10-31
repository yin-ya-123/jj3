"""日线采集服务测试（离线，临时库 + 假数据源）"""

import importlib
from datetime import date

import pandas as pd
from sqlalchemy import create_engine, insert, select
from sqlalchemy.orm import sessionmaker

from database.models import Base, Bar, DailyBar, DataSyncLog, TradingCalendar
from data.collectors import daily_collector as collector_module
from data.collectors.daily_collector import FACTOR_START_DATE, DailyCollector


BARS = pd.DataFrame(
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
        "tradestatus": ["1", "0"],
    }
)

FACTORS = pd.DataFrame(
    {
        "divid_operate_date": pd.to_datetime(["2020-01-01"]),
        "fore_adjust_factor": [1.0],
        "back_adjust_factor": [1.0],
        "adjust_factor": [1.0],
    }
)


MINUTE_BARS = pd.DataFrame(
    {
        "trade_time": ["2026-10-27 09:35:00", "2026-10-27 09:40:00"],
        "open": [10.0, 10.5],
        "high": [11.0, 11.5],
        "low": [9.8, 10.2],
        "close": [10.8, 11.2],
        "preclose": [10.5, 10.8],
        "volume": [100.0, 200.0],
        "amount": [1000.0, 2000.0],
        "turn": [0.5, 0.6],
        "pct_chg": [1.0, 2.0],
        "trade_status": [1, 1],
    }
)


class FakeProvider:
    """假数据源，记录调用参数"""

    def __init__(
        self,
        factors=None,
        bars=None,
        factor_error=None,
        minute_bars=None,
        calendar_days=None,
    ):
        self.factors = factors
        self.bars = bars
        self.factor_error = factor_error
        self.minute_bars = minute_bars
        self.calendar_days = calendar_days
        self.calls = []

    def get_adjust_factors(self, symbol, start_date, end_date):
        self.calls.append(("factors", start_date, end_date))

        if self.factor_error:
            raise self.factor_error

        return self.factors

    def get_daily_history(self, symbol, start_date, end_date, adjustflag):
        self.calls.append(("bars", start_date, end_date, adjustflag))
        return self.bars

    def get_period_history(
        self, symbol, period, start_date, end_date, adjustflag
    ):
        self.calls.append(("period", period, start_date, end_date, adjustflag))
        return self.minute_bars

    def get_trade_dates(self, start_date, end_date):
        self.calls.append(("calendar", start_date, end_date))
        return self.calendar_days


def _tmp_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    session = sessionmaker(bind=engine)

    monkeypatch.setattr(collector_module, "SessionLocal", session)

    # 各仓储模块各自持有 SessionLocal，要一起指向临时库，
    # 漏一个就会把测试数据写进正式库
    for module_name in (
        "database.repositories.adjust_factor_repository",
        "database.repositories.daily_bar_repository",
        "database.repositories.bar_repository",
        "database.repositories.trading_calendar_repository",
    ):
        module = importlib.import_module(module_name)

        monkeypatch.setattr(module, "SessionLocal", session)

    return engine


def test_sync_stock_defaults_to_raw_price(tmp_path, monkeypatch):
    """阶段 3 口径：默认存不复权原始价"""

    _tmp_session(tmp_path, monkeypatch)

    collector = DailyCollector()
    collector.provider = FakeProvider(factors=FACTORS, bars=BARS)

    result = collector.sync_stock(
        "600519", "2026-01-01", "2026-10-30"
    )

    assert result["status"] == "success"
    assert result["record_count"] == 2

    bars_call = [
        call for call in collector.provider.calls
        if call[0] == "bars"
    ][0]

    assert bars_call[3] == "3"


def test_sync_stock_syncs_factors_first(tmp_path, monkeypatch):
    """先拉因子再拉日线"""

    _tmp_session(tmp_path, monkeypatch)

    collector = DailyCollector()
    collector.provider = FakeProvider(factors=FACTORS, bars=BARS)

    collector.sync_stock("600519", "2026-01-01", "2026-10-30")

    kinds = [call[0] for call in collector.provider.calls]

    assert kinds[0] == "factors"
    assert "bars" in kinds


def test_sync_stock_writes_log(tmp_path, monkeypatch):
    """同步日志要带上周期和复权口径"""

    engine = _tmp_session(tmp_path, monkeypatch)

    collector = DailyCollector()
    collector.provider = FakeProvider(factors=FACTORS, bars=BARS)

    collector.sync_stock("600519", "2026-01-01", "2026-10-30")

    with engine.connect() as conn:
        rows = conn.execute(select(DataSyncLog)).all()

    assert len(rows) == 1
    assert rows[0].stock_code == "600519"
    assert rows[0].period == "d"
    assert rows[0].adjustflag == "3"
    assert rows[0].record_count == 2
    assert rows[0].status == "success"


def test_factor_failure_aborts_daily_sync(tmp_path, monkeypatch):
    """因子同步失败就不该再采日线，否则会存下算不出复权价的原始价"""

    engine = _tmp_session(tmp_path, monkeypatch)

    collector = DailyCollector()
    collector.provider = FakeProvider(
        factor_error=RuntimeError("接口挂了")
    )

    result = collector.sync_stock(
        "600519", "2026-01-01", "2026-10-30"
    )

    assert result["status"] == "failed"
    assert "复权因子同步失败" in result["message"]

    kinds = [call[0] for call in collector.provider.calls]

    assert "bars" not in kinds

    with engine.connect() as conn:
        rows = conn.execute(select(DataSyncLog)).all()

    assert len(rows) == 1
    assert rows[0].status == "failed"
    assert rows[0].record_count == 0


def test_factor_sync_covers_listing_history(tmp_path, monkeypatch):
    """因子区间要从上市至今，区间太窄算出来的复权价是错的"""

    _tmp_session(tmp_path, monkeypatch)

    collector = DailyCollector()
    collector.provider = FakeProvider(factors=FACTORS, bars=BARS)

    collector.sync_stock("600519", "2026-01-01", "2026-10-30")

    factors_call = [
        call for call in collector.provider.calls
        if call[0] == "factors"
    ][0]

    assert factors_call[1] == FACTOR_START_DATE
    assert factors_call[2] == "2026-10-30"


def test_minute_period_goes_to_bars_table(tmp_path, monkeypatch):
    """分钟线进 bars 表，日志记周期和复权口径"""

    engine = _tmp_session(tmp_path, monkeypatch)

    collector = DailyCollector()
    collector.provider = FakeProvider(
        factors=FACTORS,
        minute_bars=MINUTE_BARS,
    )

    result = collector.sync_stock(
        "600519",
        "2026-10-27",
        "2026-10-27",
        period="5",
    )

    assert result["status"] == "success"
    assert result["period"] == "5"
    assert result["record_count"] == 2

    with engine.connect() as conn:
        bars = conn.execute(select(Bar)).all()

    assert len(bars) == 2
    assert bars[0].period == "5"
    assert bars[0].adjustflag == "3"

    with engine.connect() as conn:
        rows = conn.execute(select(DataSyncLog)).all()

    assert len(rows) == 1
    assert rows[0].period == "5"
    assert rows[0].adjustflag == "3"


def test_weekly_period_is_not_stored(tmp_path, monkeypatch):
    """周线月线不入库，直接判失败"""

    engine = _tmp_session(tmp_path, monkeypatch)

    collector = DailyCollector()
    collector.provider = FakeProvider(factors=FACTORS, bars=BARS)

    result = collector.sync_stock(
        "600519",
        "2026-01-01",
        "2026-10-30",
        period="w",
    )

    assert result["status"] == "failed"
    assert "周线" in result["message"]

    kinds = [call[0] for call in collector.provider.calls]

    assert "bars" not in kinds
    assert "period" not in kinds

    with engine.connect() as conn:
        bars = conn.execute(select(Bar)).all()

    assert len(bars) == 0


def _seed_daily_bar(engine, code, trade_date):
    """往临时库里塞一条已有日线，模拟「库内已有最新交易日」"""

    with engine.begin() as conn:
        conn.execute(
            insert(DailyBar).values(
                stock_code=code,
                trade_date=trade_date,
                adjustflag="3",
                close=10.0,
            )
        )


def test_incremental_skips_when_up_to_date(tmp_path, monkeypatch):
    """库内已是最新：直接跳过，不发任何网络请求"""

    engine = _tmp_session(tmp_path, monkeypatch)

    _seed_daily_bar(engine, "600519", date(2026, 10, 30))

    collector = DailyCollector()
    collector.provider = FakeProvider(factors=FACTORS, bars=BARS)

    result = collector.sync_stock(
        "600519",
        "2026-10-01",
        "2026-10-30",
        incremental=True,
    )

    assert result["status"] == "skipped"
    assert result["record_count"] == 0
    assert collector.provider.calls == []


def test_incremental_starts_after_latest_trade_date(tmp_path, monkeypatch):
    """增量起点被推到库内最新交易日的次日"""

    engine = _tmp_session(tmp_path, monkeypatch)

    _seed_daily_bar(engine, "600519", date(2026, 10, 27))

    collector = DailyCollector()
    collector.provider = FakeProvider(factors=FACTORS, bars=BARS)

    result = collector.sync_stock(
        "600519",
        "2026-10-01",
        "2026-10-30",
        incremental=True,
    )

    assert result["status"] == "success"

    bars_call = [
        call for call in collector.provider.calls
        if call[0] == "bars"
    ][0]

    # 带横杠的入参也要被规范化，K 线接口吃 YYYYMMDD
    assert bars_call[1] == "20261028"


def test_incremental_empty_db_pulls_full_range(tmp_path, monkeypatch):
    """库里没有该股票数据：增量退化为全量，从入参起点开始拉"""

    engine = _tmp_session(tmp_path, monkeypatch)

    collector = DailyCollector()
    collector.provider = FakeProvider(factors=FACTORS, bars=BARS)

    result = collector.sync_stock(
        "000001",
        "2026-10-01",
        "2026-10-30",
        incremental=True,
    )

    assert result["status"] == "success"

    bars_call = [
        call for call in collector.provider.calls
        if call[0] == "bars"
    ][0]

    assert bars_call[1] == "20261001"


def test_incremental_not_blocked_without_calendar(tmp_path, monkeypatch):
    """日历表没数据不能拦截增量，照常请求数据源"""

    engine = _tmp_session(tmp_path, monkeypatch)

    _seed_daily_bar(engine, "600519", date(2026, 10, 27))

    collector = DailyCollector()
    collector.provider = FakeProvider(factors=FACTORS, bars=BARS)

    result = collector.sync_stock(
        "600519",
        "2026-10-01",
        "2026-10-30",
        incremental=True,
    )

    assert result["status"] == "success"

    bars_call = [
        call for call in collector.provider.calls
        if call[0] == "bars"
    ][0]

    assert bars_call[1] == "20261028"


def test_collector_sync_calendar_writes_table(tmp_path, monkeypatch):
    """采集器同步日历：写库 + 统计返回正确"""

    engine = _tmp_session(tmp_path, monkeypatch)

    calendar = pd.DataFrame(
        {
            "calendar_date": pd.to_datetime(
                ["2026-10-29", "2026-10-30", "2026-10-31"]
            ),
            "is_trading_day": [1, 1, 0],
        }
    )

    collector = DailyCollector()
    collector.provider = FakeProvider(
        factors=FACTORS,
        bars=BARS,
        calendar_days=calendar,
    )

    stats = collector.sync_calendar("2026-10-29", "2026-10-31")

    assert stats["total_days"] == 3
    assert stats["trading_days"] == 2

    with engine.connect() as conn:
        rows = conn.execute(select(TradingCalendar)).all()

    assert len(rows) == 3
    assert rows[2].is_trading_day == 0


def test_calendar_max_date(tmp_path, monkeypatch):
    """get_max_calendar_date 返回日历表最大日期，空表返回 None"""

    engine = _tmp_session(tmp_path, monkeypatch)

    repo = importlib.import_module(
        "database.repositories.trading_calendar_repository"
    )

    assert repo.get_max_calendar_date() is None

    with engine.begin() as conn:
        conn.execute(
            insert(TradingCalendar).values(
                calendar_date=date(2026, 10, 30),
                is_trading_day=1,
            )
        )

    assert repo.get_max_calendar_date() == date(2026, 10, 30)


def test_sync_stock_persists_tradestatus(tmp_path, monkeypatch):
    """阶段 3.4：日线采集要把 tradestatus 落库 daily_bars"""

    engine = _tmp_session(tmp_path, monkeypatch)

    collector = DailyCollector()
    collector.provider = FakeProvider(factors=FACTORS, bars=BARS)

    collector.sync_stock("600519", "2026-01-01", "2026-10-30")

    with engine.connect() as conn:
        rows = conn.execute(
            select(DailyBar).order_by(DailyBar.trade_date)
        ).all()

    assert len(rows) == 2
    assert rows[0].trade_status == "1"
    assert rows[1].trade_status == "0"
