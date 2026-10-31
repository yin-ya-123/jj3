"""估值指标计算层（阶段 5.3）

输入：财报宽表 DataFrame（compute_fundamental_metrics 输出）与最新收盘价。
输出：PE / PB / PE_TTM 指标 dict。

约定：
- 估值使用「不复权收盘价」，与财报每股指标（报告期实际值）口径一致；
  复权价仅用于量价分析（data/adjustment.py），不用于估值。
- 财报自带每股收益 eps / 每股净资产 bps 优先；缺失或 <=0 时返回 None 不硬算。
- PE_TTM 口径（A 股累计报告期）：
    ttm_eps = 最新报告期累计 eps + 去年年报 eps - 去年同报告期累计 eps
    最新为年报时 ttm_eps 即年报 eps。缺去年同期或去年年报时返回 None。
"""

import numpy as np
import pandas as pd

from database.repositories.daily_bar_repository import get_daily_bars


def get_latest_close(symbol: str):
    """查询某只股票最新交易日不复权收盘价（无数据返回 None）"""

    bars = get_daily_bars(symbol, limit=1, adjustflag="3")
    if not bars:
        return None

    latest = bars[0]
    return None if latest.close is None else float(latest.close)


def _pick_eps_by_report(frame: pd.DataFrame, report_date: pd.Timestamp):
    """取指定报告期的 eps 值（找不到返回 None）"""

    row = frame[frame["report_date"] == report_date]
    if row.empty or "eps" not in frame.columns:
        return None

    value = row.iloc[0]["eps"]
    return None if pd.isna(value) else float(value)


def compute_valuation(frame: pd.DataFrame, close):
    """计算估值指标

    参数：
        frame: 财报宽表（至少含 report_date/eps/bps，建议来自 fundamentals 输出）
        close: 最新不复权收盘价
    返回：
        {
            "report_date": 最新报告期日期字符串或 None,
            "close": float | None,
            "eps": float | None,
            "bps": float | None,
            "pe": float | None,      # 静态市盈率 = close / eps
            "pb": float | None,      # 市净率 = close / bps
            "pe_ttm": float | None,  # 滚动市盈率（口径见模块 docstring）
        }
    """

    if frame is None or frame.empty or close is None:
        return {
            "report_date": None,
            "close": None if close is None else float(close),
            "eps": None,
            "bps": None,
            "pe": None,
            "pb": None,
            "pe_ttm": None,
        }

    close = float(close)
    latest = frame.iloc[-1]
    report_date = latest["report_date"]

    result = {
        "report_date": report_date.strftime("%Y-%m-%d") if report_date is not None else None,
        "close": close,
        "eps": None,
        "bps": None,
        "pe": None,
        "pb": None,
        "pe_ttm": None,
    }

    if "eps" not in frame.columns or "bps" not in frame.columns:
        return result

    eps = None if pd.isna(latest.get("eps")) else float(latest["eps"])
    bps = None if pd.isna(latest.get("bps")) else float(latest["bps"])

    result["eps"] = eps
    result["bps"] = bps

    # ---- 静态 PE / PB ----
    if eps is not None and eps > 0:
        result["pe"] = round(close / eps, 2)
    if bps is not None and bps > 0:
        result["pb"] = round(close / bps, 2)

    # ---- PE_TTM ----
    ttm_eps = _compute_ttm_eps(frame)
    if ttm_eps is not None and ttm_eps > 0:
        result["pe_ttm"] = round(close / ttm_eps, 2)

    return result


def _compute_ttm_eps(frame: pd.DataFrame):
    """按累计报告期口径推算滚动每股收益（缺数据返回 None）"""

    if "eps" not in frame.columns:
        return None

    latest_date = frame["report_date"].iloc[-1]
    month, day = latest_date.month, latest_date.day

    # 最新为年报：TTM EPS 即年报累计 eps
    if month == 12 and day == 31:
        return _pick_eps_by_report(frame, latest_date)

    last_year_date = latest_date - pd.DateOffset(years=1)

    prev_year_annual = _pick_eps_by_report(
        frame, pd.Timestamp(year=latest_date.year - 1, month=12, day=31)
    )
    prev_year_same = _pick_eps_by_report(frame, last_year_date)
    latest_eps = _pick_eps_by_report(frame, latest_date)

    if (
        latest_eps is None
        or prev_year_annual is None
        or prev_year_same is None
    ):
        return None

    return latest_eps + prev_year_annual - prev_year_same
