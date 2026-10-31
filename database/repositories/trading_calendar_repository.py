"""交易日历仓储

日历是「一张表，一天一行」，没有股票维度，
所以接口只按日期区间进出，不接股票代码。
"""

from datetime import date

import pandas as pd

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from database.db import SessionLocal
from database.models import TradingCalendar


def _to_date(value) -> date:
    """把 date / 'YYYYMMDD' / 'YYYY-MM-DD' 统一成 date"""

    if isinstance(value, date):
        return value

    text = str(value).strip()

    if len(text) == 8 and text.isdigit():
        return date(int(text[:4]), int(text[4:6]), int(text[6:]))

    return pd.Timestamp(text).date()


def save_trade_dates(df: pd.DataFrame) -> int:
    """保存交易日历，重复数据自动更新，返回写入条数"""

    if df is None or df.empty:
        return 0

    records = []

    for _, row in df.iterrows():
        records.append({
            "calendar_date": pd.Timestamp(row["calendar_date"]).date(),
            "is_trading_day": int(row["is_trading_day"]),
        })

    if not records:
        return 0

    with SessionLocal.begin() as session:
        statement = insert(TradingCalendar).values(records)

        statement = statement.on_conflict_do_update(
            index_elements=["calendar_date"],
            set_={"is_trading_day": statement.excluded.is_trading_day},
        )

        session.execute(statement)

    return len(records)


def get_calendar_days(start_date, end_date) -> list[tuple[date, int]]:
    """查询区间内的日历日，含是否交易日标记"""

    with SessionLocal() as session:
        statement = (
            select(
                TradingCalendar.calendar_date,
                TradingCalendar.is_trading_day,
            )
            .where(
                TradingCalendar.calendar_date
                >= _to_date(start_date)
            )
            .where(
                TradingCalendar.calendar_date
                <= _to_date(end_date)
            )
            .order_by(TradingCalendar.calendar_date)
        )

        return [(row[0], int(row[1])) for row in session.execute(statement).all()]


def get_trading_days(start_date, end_date) -> list[date]:
    """查询区间内的交易日"""

    return [
        day
        for day, flag in get_calendar_days(start_date, end_date)
        if flag == 1
    ]


def get_max_calendar_date() -> date | None:
    """日历表已有数据的最大日期，没有数据返回 None"""

    with SessionLocal() as session:
        return session.scalar(
            select(func.max(TradingCalendar.calendar_date))
        )


def has_trading_day(start_date, end_date) -> bool:
    """区间内是否有交易日

    日历没覆盖该区间时返回 True —— 不误杀，
    让调用方照常去请求数据源。
    """

    days = get_calendar_days(start_date, end_date)

    if not days:
        return True

    return any(flag == 1 for _, flag in days)
