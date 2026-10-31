import pandas as pd
from data.utils import market_of

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from database.db import SessionLocal
from database.models import Stock, DailyBar


def _to_float(value):
    """将 Pandas 数值转换为 Python float，空值转换为 None"""
    if pd.isna(value):
        return None
    return float(value)


def save_daily_bars(
        df: pd.DataFrame,
        symbol: str,
        adjustflag: str = "2",
) -> int:
    """保存历史日线，重复数据自动更新"""

    if df is None or df.empty:
        return 0

    code = str(symbol).strip()[-6:]

    if not code.isdigit() or len(code) != 6:
        raise ValueError(f"无效股票代码: {symbol}")

    # 根据 6 位代码判断所属市场
    market = market_of(code)

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
        })

    if not records:
        return 0

    with SessionLocal.begin() as session:
        # 股票基础信息：只在首次出现时创建
        stock = session.get(Stock, code)

        if stock is None:
            session.add(
                Stock(
                    code=code,
                    market=market,
                )
            )

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
            },
        )

        session.execute(statement)

    return len(records)


def get_daily_bars(
        symbol: str,
        limit: int = 20,
        adjustflag: str = "2",
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
