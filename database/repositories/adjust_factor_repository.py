"""复权因子仓储

因子表是「事件表」：每只股票每次除权除息一行。
back_adjust_factor 是累积历史事实，永不改变；fore_adjust_factor 会漂移，仅作采集快照。
"""

import pandas as pd

from sqlalchemy import select
from sqlalchemy.dialects.sqlite import insert

from database.db import SessionLocal
from database.models import AdjustFactor


def _to_float(value):
    """Pandas 数值转 float，空值转 None"""

    if value is None:
        return None

    if pd.isna(value):
        return None

    return float(value)


def save_adjust_factors(df: pd.DataFrame, symbol: str) -> int:
    """保存复权因子，重复事件自动更新"""

    if df is None or df.empty:
        return 0

    code = str(symbol).strip()[-6:]

    if not code.isdigit() or len(code) != 6:
        raise ValueError(f"无效股票代码: {symbol}")

    records = []

    for _, row in df.iterrows():
        records.append({
            "stock_code": code,
            "divid_operate_date": pd.Timestamp(
                row["divid_operate_date"]
            ).date(),
            "fore_adjust_factor": _to_float(
                row.get("fore_adjust_factor")
            ),
            "back_adjust_factor": _to_float(
                row.get("back_adjust_factor")
            ),
            "adjust_factor": _to_float(row.get("adjust_factor")),
        })

    if not records:
        return 0

    with SessionLocal.begin() as session:
        statement = insert(AdjustFactor).values(records)

        statement = statement.on_conflict_do_update(
            index_elements=["stock_code", "divid_operate_date"],
            set_={
                "fore_adjust_factor": statement.excluded.fore_adjust_factor,
                "back_adjust_factor": statement.excluded.back_adjust_factor,
                "adjust_factor": statement.excluded.adjust_factor,
            },
        )

        session.execute(statement)

    return len(records)


def get_adjust_factors(code: str) -> list:
    """按日期升序返回某只股票的复权因子"""

    code = str(code).strip()[-6:]

    with SessionLocal() as session:
        statement = (
            select(AdjustFactor)
            .where(AdjustFactor.stock_code == code)
            .order_by(AdjustFactor.divid_operate_date)
        )

        return list(session.scalars(statement).all())


def get_adjust_factor_frame(code: str) -> pd.DataFrame:
    """返回 DataFrame：divid_operate_date / back_adjust_factor（按日期升序）

    空表时返回空 DataFrame，调用方需自行判断。
    """

    rows = get_adjust_factors(code)

    columns = [
        "divid_operate_date",
        "back_adjust_factor",
        "fore_adjust_factor",
    ]

    if not rows:
        return pd.DataFrame(columns=columns)

    return pd.DataFrame(
        [
            {
                "divid_operate_date": row.divid_operate_date,
                "back_adjust_factor": row.back_adjust_factor,
                "fore_adjust_factor": row.fore_adjust_factor,
            }
            for row in rows
        ],
        columns=columns,
    )


def latest_back_factor(code: str) -> float:
    """最新生效的后复权因子，没有因子时返回 1.0"""

    frame = get_adjust_factor_frame(code)

    if frame.empty:
        return 1.0

    frame = frame.dropna(subset=["back_adjust_factor"])
    frame = frame.sort_values("divid_operate_date")

    if frame.empty:
        return 1.0

    return float(frame["back_adjust_factor"].iloc[-1])
