from datetime import date

import pandas as pd

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from database.db import SessionLocal
from database.models import DailyBar


def _to_float(value):
    """将 Pandas 数值转换为 Python float，空值转换为 None"""
    if pd.isna(value):
        return None
    return float(value)


def _to_trade_status(value):
    """将 Baostock tradestatus 归一为 '1'/'0' 字符串，缺失/空值为 None

    历史 df（未含 tradestatus 列）落库时 trade_status=None（未知）。
    """
    if value is None:
        return None

    text = str(value).strip()

    if not text:
        return None

    if text in ("1", "0"):
        return text

    # 其他取值（如 NaN 字符串）视为未知
    return None


def save_daily_bars(
        df: pd.DataFrame,
        symbol: str,
        adjustflag: str = "3",
) -> int:
    """保存历史日线，重复数据自动更新

    口径：库存不复权原始价（adjustflag=3），复权在计算层做。
    不创建股票行 —— 采集行情不得污染用户自选池。
    """

    if df is None or df.empty:
        return 0

    code = str(symbol).strip()[-6:]

    if not code.isdigit() or len(code) != 6:
        raise ValueError(f"无效股票代码: {symbol}")

    records = []

    for _, row in df.iterrows():
        records.append({
            "stock_code": code,
            "trade_date": pd.Timestamp(row["date"]).date(),
            "adjustflag": str(adjustflag),
            "open": _to_float(row["open"]),
            "high": _to_float(row["high"]),
            "low": _to_float(row["low"]),
            "close": _to_float(row["close"]),
            "preclose": _to_float(row["preclose"]),
            "volume": _to_float(row["volume"]),
            "amount": _to_float(row["amount"]),
            "turn": _to_float(row["turn"]),
            "pct_chg": _to_float(row["pctChg"]),
            "trade_status": _to_trade_status(
                row.get("tradestatus") if hasattr(row, "get") else None
            ),
        })

    if not records:
        return 0

    with SessionLocal.begin() as session:
        # SQLite 原生 UPSERT
        statement = insert(DailyBar).values(records)

        statement = statement.on_conflict_do_update(
            index_elements=[
                "stock_code",
                "trade_date",
                "adjustflag",
            ],
            set_={
                "open": statement.excluded.open,
                "high": statement.excluded.high,
                "low": statement.excluded.low,
                "close": statement.excluded.close,
                "preclose": statement.excluded.preclose,
                "volume": statement.excluded.volume,
                "amount": statement.excluded.amount,
                "turn": statement.excluded.turn,
                "pct_chg": statement.excluded.pct_chg,
                "trade_status": statement.excluded.trade_status,
            },
        )

        session.execute(statement)

    return len(records)


def get_latest_trade_date(
        symbol: str,
        adjustflag: str = "3",
) -> date | None:
    """查询某只股票已有的最新交易日（增量同步的起点依据）"""

    code = str(symbol).strip()[-6:]

    with SessionLocal() as session:
        statement = select(func.max(DailyBar.trade_date)).where(
            DailyBar.stock_code == code
        ).where(DailyBar.adjustflag == str(adjustflag))

        return session.scalar(statement)


def get_daily_bars(
        symbol: str,
        limit: int = 20,
        adjustflag: str = "3",
) -> list:
    """查询某只股票最近的历史日线"""

    code = str(symbol).strip()[-6:]

    with SessionLocal() as session:
        statement = (
            select(DailyBar)
            .where(DailyBar.stock_code == code)
            .where(DailyBar.adjustflag == str(adjustflag))
            .order_by(DailyBar.trade_date.desc())
            .limit(limit)
        )

        return list(session.scalars(statement).all())
