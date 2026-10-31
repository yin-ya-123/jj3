"""财务指标计算层（阶段 5.2）

输入：financial_reports 宽表数据（FinancialReport 记录列表或含
      FLOAT_COLUMNS 列的 DataFrame），按报告期排列。
输出：追加指标列的 DataFrame 副本（不修改入参），或结构化 dict。

约定：
- 与 data/analysis.py / data/indicators.py 一致：纯 pandas 自实现、
  缺列容错、数据不足返回 NaN 不报错。
- 指标取值优先级：财报自带字段（akshare 东财口径）优先；
  缺失时用宽表基础字段自算兜底（口径见各函数 docstring）。
- 同比（YOY）自算口径：同股票、报告期相差恰好 1 年的上一期对比。
"""

from datetime import date

import numpy as np
import pandas as pd

from database.repositories.financial_report_repository import FLOAT_COLUMNS


def _numeric(frame: pd.DataFrame) -> pd.DataFrame:
    """复制并统一数值列类型，保证下游运算安全"""
    return frame.copy()


def _has_columns(frame: pd.DataFrame, columns) -> bool:
    """检查列是否齐全（任一缺失即返回 False）"""
    return all(column in frame.columns for column in columns)


def reports_to_frame(records) -> pd.DataFrame:
    """FinancialReport 记录列表 → 宽表 DataFrame

    - report_date / announce_date 转为 datetime64，便于同比/环比对齐。
    - 数值列只保留 FLOAT_COLUMNS 中真实存在的列。
    """

    if not records:
        return pd.DataFrame()

    frame = pd.DataFrame(
        [
            {
                "stock_code": getattr(record, "stock_code", None),
                "report_date": pd.Timestamp(getattr(record, "report_date", None)),
                "announce_date": pd.Timestamp(getattr(record, "announce_date", None)),
                **{
                    column: getattr(record, column, None)
                    for column in FLOAT_COLUMNS
                },
            }
            for record in records
        ]
    )

    for column in FLOAT_COLUMNS:
        if column in frame.columns:
            frame[column] = pd.to_numeric(frame[column], errors="coerce")

    frame = frame.dropna(subset=["report_date"]).sort_values("report_date")
    return frame.reset_index(drop=True)


def _safe_pct_change(current: pd.Series, previous: pd.Series) -> pd.Series:
    """同比/环比通用计算：(当前/上一期 - 1) * 100，除零/缺失返回 NaN"""

    denominator = previous.replace(0.0, np.nan)
    return (current / denominator - 1.0) * 100.0


def _add_yoy(frame: pd.DataFrame, column: str, yoy_column: str) -> pd.DataFrame:
    """自算同比：同股票、报告期相差 1 年的上一期对比"""

    if column not in frame.columns or yoy_column in frame.columns:
        return frame

    work = frame[["stock_code", "report_date", column]].copy()
    work["_prev_date"] = work["report_date"] - pd.DateOffset(years=1)

    merged = work.merge(
        work[["stock_code", "report_date", column]].rename(
            columns={"report_date": "_prev_date", column: "_prev_value"}
        ),
        on=["stock_code", "_prev_date"],
        how="left",
    )

    frame[yoy_column] = _safe_pct_change(merged[column], merged["_prev_value"])
    return frame


def compute_fundamental_metrics(frame: pd.DataFrame) -> pd.DataFrame:
    """计算基础财务指标，追加到 DataFrame 副本

    新增指标列（数值含义）：
      - operate_income        营业收入（原列透传）
      - operate_income_yoy    营收同比 %（原列缺失时自算）
      - net_profit            净利润（net_profit 优先，缺失用归母净利兜底）
      - net_profit_yoy        净利润同比 %（原列缺失时自算）
      - gross_profit_ratio    毛利率 %（原列缺失时自算）
      - net_profit_ratio      净利率 %（原列缺失时自算）
      - roe                   净资产收益率 %（原列缺失时自算）
      - debt_ratio            资产负债率 %（total_liabilities / total_assets）
      - netcash_operate       经营活动现金流净额（原列透传）
    """

    if frame is None or frame.empty:
        return frame

    result = _numeric(frame)

    # ---- 营收与净利润（优先透传原列） ----
    if "operate_income" in result.columns:
        result["operate_income"] = pd.to_numeric(
            result["operate_income"], errors="coerce"
        )
    if "netcash_operate" in result.columns:
        result["netcash_operate"] = pd.to_numeric(
            result["netcash_operate"], errors="coerce"
        )

    if "net_profit" in result.columns:
        result["net_profit"] = pd.to_numeric(result["net_profit"], errors="coerce")
        # 缺失行用归母净利兜底（逐行填充）
        if "parent_net_profit" in result.columns:
            parent_net_profit = pd.to_numeric(
                result["parent_net_profit"], errors="coerce"
            )
            result["net_profit"] = result["net_profit"].fillna(parent_net_profit)

    # ---- 同比：财报自带列优先，缺失列自算 ----
    for column, yoy_column in (
        ("operate_income", "operate_income_yoy"),
        ("net_profit", "net_profit_yoy"),
    ):
        if _has_columns(result, (column, "stock_code", "report_date")):
            if yoy_column not in result.columns:
                result = _add_yoy(result, column, yoy_column)
            else:
                result[yoy_column] = pd.to_numeric(
                    result[yoy_column], errors="coerce"
                )

    # ---- 毛利率：自带优先，(营收-营业成本)/营收 兜底 ----
    if "gross_profit_ratio" in result.columns:
        result["gross_profit_ratio"] = pd.to_numeric(
            result["gross_profit_ratio"], errors="coerce"
        )
    if (
        result.get("gross_profit_ratio", pd.Series(dtype=float)).isna().all()
        and _has_columns(result, ("operate_income", "operate_cost"))
    ):
        income = result["operate_income"].replace(0.0, np.nan)
        result["gross_profit_ratio"] = (
            (result["operate_income"] - result["operate_cost"]) / income * 100.0
        )

    # ---- 净利率：自带优先，净利润/营收 兜底 ----
    if "net_profit_ratio" in result.columns:
        result["net_profit_ratio"] = pd.to_numeric(
            result["net_profit_ratio"], errors="coerce"
        )
    if (
        result.get("net_profit_ratio", pd.Series(dtype=float)).isna().all()
        and _has_columns(result, ("net_profit", "operate_income"))
    ):
        income = result["operate_income"].replace(0.0, np.nan)
        result["net_profit_ratio"] = result["net_profit"] / income * 100.0

    # ---- ROE：自带优先，归母净利/归母权益 兜底 ----
    if "roe" in result.columns:
        result["roe"] = pd.to_numeric(result["roe"], errors="coerce")
    if (
        result.get("roe", pd.Series(dtype=float)).isna().all()
        and _has_columns(result, ("parent_net_profit", "parent_equity"))
    ):
        equity = result["parent_equity"].replace(0.0, np.nan)
        result["roe"] = result["parent_net_profit"] / equity * 100.0

    # ---- 资产负债率：负债/资产 ----
    if _has_columns(result, ("total_liabilities", "total_assets")):
        assets = result["total_assets"].replace(0.0, np.nan)
        result["debt_ratio"] = result["total_liabilities"] / assets * 100.0

    return result


def get_metrics_by_report(report_date, frame: pd.DataFrame) -> dict:
    """取指定报告期的指标字典（找不到返回空 dict）"""

    if frame is None or frame.empty or "report_date" not in frame.columns:
        return {}

    target = pd.Timestamp(report_date)
    row = frame[frame["report_date"] == target]

    if row.empty:
        return {}

    series = row.iloc[0]
    return {
        column: (
            None
            if pd.isna(value)
            else float(value)
            if np.issubdtype(type(value), np.number)
            else value
        )
        for column, value in series.items()
        if column not in ("stock_code", "report_date", "announce_date")
    }
