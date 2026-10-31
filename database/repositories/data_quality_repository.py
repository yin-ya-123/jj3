"""数据完整性检查仓储（阶段 3.4）

口径说明：
    - 缺失日 = 交易日历中是交易日、但该股票 daily_bars 里没有行。
      长期停牌/新股上市前/退市后都可能表现为缺失，需结合停牌日判断。
    - 停牌日 = daily_bars 中有行且 trade_status='0'（Baostock tradestatus）。
      trade_status 为 NULL 的行表示「未知」：3.4 迁移前的存量行，
      检查时不计入停牌日，但可统计 unknown 数量提示重采回填。

日历依赖：检查是只读操作，不自动联网。日历未覆盖区间时
返回空结果并附 calendar_coverage=False 提示，由调用方决定
是否先跑 scripts/sync_daily_bars.py --ensure-calendar。
"""

from datetime import date

import pandas as pd

from sqlalchemy import select

from database.db import SessionLocal
from database.models import DailyBar

from database.repositories.trading_calendar_repository import get_trading_days


def _to_date_key(value) -> date:
    """把 date / 'YYYYMMDD' / 'YYYY-MM-DD' / Timestamp 统一成 date"""

    if isinstance(value, date):
        return value

    text = str(value).strip()

    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:]))

    return pd.Timestamp(text).date()


def get_missing_trading_days(
    symbol: str,
    start_date,
    end_date,
    adjustflag: str = "3",
) -> list[date]:
    """报出缺失交易日：日历是交易日但库内没有行"""

    code = str(symbol).strip()[-6:]

    trading_days = get_trading_days(start_date, end_date)

    if not trading_days:
        return []

    with SessionLocal() as session:
        rows = session.execute(
            select(DailyBar.trade_date)
            .where(DailyBar.stock_code == code)
            .where(DailyBar.adjustflag == str(adjustflag))
            .where(DailyBar.trade_date >= trading_days[0])
            .where(DailyBar.trade_date <= trading_days[-1])
        ).all()

    stored = {row[0] for row in rows}

    return [day for day in trading_days if day not in stored]


def get_suspension_days(
    symbol: str,
    start_date,
    end_date,
    adjustflag: str = "3",
) -> list[date]:
    """报出停牌日：库内有行且 trade_status='0'"""

    code = str(symbol).strip()[-6:]

    with SessionLocal() as session:
        rows = session.execute(
            select(DailyBar.trade_date)
            .where(DailyBar.stock_code == code)
            .where(DailyBar.adjustflag == str(adjustflag))
            .where(DailyBar.trade_date >= _to_date_key(start_date))
            .where(DailyBar.trade_date <= _to_date_key(end_date))
            .where(DailyBar.trade_status == "0")
        ).all()

    return [row[0] for row in rows]


def check_data_integrity(
    symbol: str,
    start_date,
    end_date,
    adjustflag: str = "3",
) -> dict:
    """单只股票完整性检查汇总

    返回：
        stock_code / start_date / end_date / adjustflag
        trading_days        区间内日历交易日数（0=日历未覆盖）
        bar_count           库内该股票日线行数
        missing_days        缺失交易日列表
        suspension_days     停牌日列表（trade_status='0'）
        unknown_status_rows trade_status 为 NULL 的行数（迁移前存量）
        calendar_coverage   日历是否覆盖该区间
    """

    code = str(symbol).strip()[-6:]

    trading_days = get_trading_days(start_date, end_date)

    start_key = _to_date_key(start_date)
    end_key = _to_date_key(end_date)

    with SessionLocal() as session:
        rows = session.execute(
            select(
                DailyBar.trade_date,
                DailyBar.trade_status,
            )
            .where(DailyBar.stock_code == code)
            .where(DailyBar.adjustflag == str(adjustflag))
            .where(DailyBar.trade_date >= start_key)
            .where(DailyBar.trade_date <= end_key)
        ).all()

    stored_dates = {row[0] for row in rows}
    suspension_days = sorted(
        row[0] for row in rows if row[1] == "0"
    )
    unknown_count = sum(1 for row in rows if row[1] is None)

    # 日历未覆盖区间：缺失列表无意义，返回空并提示
    if not trading_days:
        missing_days = []
        coverage = False
    else:
        missing_days = [
            day for day in trading_days if day not in stored_dates
        ]
        coverage = True

    return {
        "stock_code": code,
        "start_date": start_key,
        "end_date": end_key,
        "adjustflag": str(adjustflag),
        "trading_days": len(trading_days),
        "bar_count": len(rows),
        "missing_days": missing_days,
        "suspension_days": suspension_days,
        "unknown_status_rows": unknown_count,
        "calendar_coverage": coverage,
    }
