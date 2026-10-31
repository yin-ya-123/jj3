import pandas as pd

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from database.db import SessionLocal
from database.models import Bar

# bars 表只放分钟线；日线在 daily_bars，周线月线不入库
MINUTE_PERIODS = ("5", "15", "30", "60")


def _to_float(value):
    """将 Pandas 数值转换为 Python float，空值转换为 None"""

    if value is None:
        return None

    if pd.isna(value):
        return None

    return float(value)


def save_bars(
        df: pd.DataFrame,
        symbol: str,
        period: str,
        adjustflag: str = "3",
) -> int:
    """保存多周期行情（分钟线），重复数据自动更新"""

    if df is None or df.empty:
        return 0

    code = str(symbol).strip()[-6:]

    if not code.isdigit() or len(code) != 6:
        raise ValueError(f"无效股票代码: {symbol}")

    period = str(period).strip()

    if period not in MINUTE_PERIODS:
        raise ValueError(
            f"bars 表只存分钟线周期，收到: {period}"
        )

    records = []

    for _, row in df.iterrows():
        records.append({
            "stock_code": code,
            "period": period,
            # 规整到秒：毫秒精度会让唯一约束匹配不上，插出重复行
            "trade_time": pd.Timestamp(row["trade_time"]).floor("s"),
            "adjustflag": str(adjustflag),
            "open": _to_float(row.get("open")),
            "high": _to_float(row.get("high")),
            "low": _to_float(row.get("low")),
            "close": _to_float(row.get("close")),
            "preclose": _to_float(row.get("preclose")),
            "volume": _to_float(row.get("volume")),
            "amount": _to_float(row.get("amount")),
            "turn": _to_float(row.get("turn")),
            "pct_chg": _to_float(row.get("pct_chg")),
            "trade_status": row.get("trade_status"),
        })

    if not records:
        return 0

    with SessionLocal.begin() as session:
        statement = insert(Bar).values(records)

        statement = statement.on_conflict_do_update(
            index_elements=[
                "stock_code",
                "period",
                "trade_time",
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


def get_bars(
        symbol: str,
        period: str = "5",
        limit: int = 500,
        adjustflag: str = "3",
) -> list:
    """查询某只股票指定周期的行情，按时间升序"""

    code = str(symbol).strip()[-6:]

    with SessionLocal() as session:
        statement = (
            select(Bar)
            .where(Bar.stock_code == code)
            .where(Bar.period == str(period))
            .where(Bar.adjustflag == str(adjustflag))
            .order_by(Bar.trade_time)
            .limit(limit)
        )

        return list(session.scalars(statement).all())