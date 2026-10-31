"""财报宽表仓储（阶段 5.1）

落库表 financial_reports：
    UNIQUE(stock_code, report_date)，报告期与披露日期双字段。
    UPSERT 幂等：同一报告期重复写入会更新指标（财报修订场景）。

FLOAT_COLUMNS 需与 data/providers/akshare_financial_provider.py 的
INDICATOR_ALIASES key 保持一致（tests/test_financial_provider.py 会断言）。
"""

from datetime import date

import pandas as pd

from sqlalchemy import func, select
from sqlalchemy.dialects.sqlite import insert

from database.db import SessionLocal
from database.models import FinancialReport


# 宽表浮点指标列（数值单位随数据源原值）
FLOAT_COLUMNS = [
    "roe",
    "roe_diluted",
    "net_profit_ratio",
    "gross_profit_ratio",
    "eps",
    "bps",
    "total_assets",
    "total_liabilities",
    "total_equity",
    "parent_equity",
    "monetary_funds",
    "accounts_receivable",
    "inventory",
    "fixed_asset",
    "goodwill",
    "operate_income",
    "operate_cost",
    "operate_profit",
    "total_profit",
    "net_profit",
    "parent_net_profit",
    "deduct_parent_net_profit",
    "sell_expense",
    "manage_expense",
    "finance_expense",
    "research_expense",
    "operate_income_yoy",
    "net_profit_yoy",
    "parent_net_profit_yoy",
    "deduct_parent_net_profit_yoy",
    "netcash_operate",
    "netcash_invest",
    "netcash_finance",
    "netcash_total",
]


def _to_float(value):
    """将 Pandas 数值转换为 Python float，空值转换为 None"""
    if value is None or pd.isna(value):
        return None
    return float(value)


def _to_date(value):
    """将 Pandas 日期转换为 datetime.date，空值转换为 None"""
    if value is None or pd.isna(value):
        return None
    return pd.Timestamp(value).date()


def save_financial_reports(df: pd.DataFrame, symbol: str) -> int:
    """保存财报宽表，重复报告期自动更新（UPSERT）

    不创建股票行 —— 采集财报不得污染用户自选池。
    """

    if df is None or df.empty:
        return 0

    code = str(symbol).strip()[-6:]

    if not code.isdigit() or len(code) != 6:
        raise ValueError(f"无效股票代码: {symbol}")

    records = []

    for _, row in df.iterrows():
        report_date = _to_date(row.get("report_date"))

        # 缺报告期的行没有意义，直接跳过
        if report_date is None:
            continue

        record = {
            "stock_code": code,
            "report_date": report_date,
            "announce_date": _to_date(row.get("announce_date")),
        }

        for column in FLOAT_COLUMNS:
            record[column] = _to_float(row.get(column))

        records.append(record)

    if not records:
        return 0

    with SessionLocal.begin() as session:
        statement = insert(FinancialReport).values(records)

        statement = statement.on_conflict_do_update(
            index_elements=[
                "stock_code",
                "report_date",
            ],
            set_={
                "announce_date": statement.excluded["announce_date"],
                **{
                    column: statement.excluded[column]
                    for column in FLOAT_COLUMNS
                },
            },
        )

        session.execute(statement)

    return len(records)


def get_latest_report_date(symbol: str) -> date | None:
    """查询某只股票已有的最新报告期（增量同步的起点依据）"""

    code = str(symbol).strip()[-6:]

    with SessionLocal() as session:
        statement = select(func.max(FinancialReport.report_date)).where(
            FinancialReport.stock_code == code
        )

        return session.scalar(statement)


def get_financial_reports(
    symbol: str,
    limit: int = 20,
) -> list:
    """查询某只股票最近的财报（按报告期倒序）"""

    code = str(symbol).strip()[-6:]

    with SessionLocal() as session:
        statement = (
            select(FinancialReport)
            .where(FinancialReport.stock_code == code)
            .order_by(FinancialReport.report_date.desc())
            .limit(limit)
        )

        return list(session.scalars(statement).all())
