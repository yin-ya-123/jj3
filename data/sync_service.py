"""行情同步服务层（阶段 3.5）

CLI（scripts/sync_daily_bars.py）与 Streamlit 界面（ui/data_sync.py）
共用的同步编排逻辑，避免两处重复实现：

    run_daily_sync(...)     单次同步编排：可选补日历 + 批量采集
    ensure_calendar_cover() 交易日历覆盖保障（供 CLI / UI 共用）

注意：
    本模块会写正式数据库并联网，界面中由用户点击按钮触发；
    collector 参数可在测试中注入 FakeProvider，不传则用真实 Baostock。
"""

from datetime import timedelta

from data.collectors.daily_collector import PERIOD_NAMES, DailyCollector
from database.repositories.trading_calendar_repository import (
    get_max_calendar_date,
)


def ensure_calendar_cover(collector: DailyCollector, end_date: str) -> str:
    """保证交易日历覆盖到 end_date，返回说明：已覆盖 / 已补齐 / 已初始化"""

    max_date = get_max_calendar_date()
    end_key = str(end_date).strip().replace("-", "")

    if max_date is not None:
        if max_date.strftime("%Y%m%d") >= end_key:
            return "已覆盖"

        start = (max_date + timedelta(days=1)).strftime("%Y-%m-%d")
        collector.sync_calendar(start, end_date)

        return "已补齐"
    else:
        collector.sync_calendar("1990-01-01", end_date)

        return "已初始化"


def run_daily_sync(
    codes: list[str],
    start: str,
    end: str,
    period: str = "d",
    adjustflag: str = "3",
    with_factors: bool = True,
    incremental: bool = False,
    ensure_calendar: bool = False,
    collector: DailyCollector | None = None,
) -> dict:
    """执行一次同步，返回结构化结果（供界面展示 / 测试断言）

    参数：
        codes            股票代码列表（6 位）
        start / end      区间（YYYY-MM-DD）
        period           周期：d / 5 / 15 / 30 / 60
        adjustflag       复权口径（项目默认 3=不复权）
        with_factors     是否先同步复权因子
        incremental      增量模式（从库内最新交易日次日拉取，仅日线）
        ensure_calendar  采集前自动补齐交易日历到结束日
        collector        测试可注入；默认创建真实采集器

    返回：
        summary 字段：total / success / skipped / failed / duration
    """

    c = collector if collector is not None else DailyCollector()

    calendar_note = None

    if ensure_calendar:
        calendar_note = ensure_calendar_cover(c, end)

    results = c.sync_stocks(
        symbols=codes,
        start_date=start,
        end_date=end,
        adjustflag=adjustflag,
        period=period,
        with_factors=with_factors,
        incremental=incremental,
    )

    success = sum(
        1 for item in results if item["status"] == "success"
    )
    skipped = sum(
        1 for item in results if item["status"] == "skipped"
    )
    failed = len(results) - success - skipped

    return {
        "codes": codes,
        "period": period,
        "adjustflag": adjustflag,
        "start": start,
        "end": end,
        "mode": "incremental" if incremental else "full",
        "calendar": calendar_note,
        "results": results,
        "summary": {
            "total": len(results),
            "success": success,
            "skipped": skipped,
            "failed": failed,
            "period_name": PERIOD_NAMES.get(period, period),
        },
    }
