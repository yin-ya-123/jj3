"""复权换算

口径约定：
    库里存「不复权」原始价（adjustflag=3），复权在计算层做。

原因（实测证据见 scripts/diag_factor_semantics.py）：
    Baostock 的前复权锚定当前日期，股票再除权后历史前复权价会整体变化；
    不复权价和后复权因子都是客观历史事实，永远不变，回测才可复现。

公式：
    后复权价 = 不复权价 * back_adjust_factor(date)
    前复权价 = 不复权价 * back_adjust_factor(date) / back_adjust_factor(latest)
"""

import numpy as np
import pandas as pd

PRICE_COLUMNS = ("open", "high", "low", "close", "preclose")


def latest_back_factor(factors: pd.DataFrame) -> float:
    """因子表里最后生效的后复权因子，没有则返回 1.0"""

    if factors is None or len(factors) == 0:
        return 1.0

    frame = factors.dropna(subset=["back_adjust_factor"])

    if frame.empty:
        return 1.0

    frame = frame.sort_values("divid_operate_date")

    return float(frame["back_adjust_factor"].iloc[-1])


def build_back_factor(dates, factors: pd.DataFrame) -> pd.Series:
    """阶梯因子：每个日期取「最后一个 divid_operate_date <= date」那一行的因子

    早于第一个除权日的日期返回 1.0。
    """

    index = dates.index

    if factors is None or len(factors) == 0:
        return pd.Series(1.0, index=index)

    frame = factors[["divid_operate_date", "back_adjust_factor"]].copy()
    frame["divid_operate_date"] = pd.to_datetime(
        frame["divid_operate_date"], errors="coerce"
    )
    frame = frame.dropna(
        subset=["divid_operate_date", "back_adjust_factor"]
    )
    frame = frame.sort_values("divid_operate_date")

    if frame.empty:
        return pd.Series(1.0, index=index)

    event_dates = frame["divid_operate_date"].to_numpy(
        dtype="datetime64[ns]"
    )
    event_factors = frame["back_adjust_factor"].to_numpy(
        dtype="float64"
    )
    target = pd.to_datetime(
        pd.Series(dates).reset_index(drop=True)
    ).to_numpy(dtype="datetime64[ns]")

    # searchsorted(side="right") - 1 → 最后一个 <= target 的位置
    position = np.searchsorted(event_dates, target, side="right") - 1

    values = np.ones(len(target), dtype="float64")
    matched = position >= 0
    values[matched] = event_factors[position[matched]]

    return pd.Series(values, index=index)


def apply_adjust(
    df: pd.DataFrame,
    factors: pd.DataFrame,
    mode: str = "qfq",
    price_columns=PRICE_COLUMNS,
) -> pd.DataFrame:
    """按复权模式换算价格

    mode:
        'qfq'  前复权（推荐展示与回测）
        'hfq'  后复权
        'none' 不复权，原样返回

    结果里额外带一列 adjust_factor，记录每行实际乘的系数，方便核对。
    """

    if df is None or df.empty:
        return df

    mode = str(mode).lower()

    if mode == "none":
        return df.copy()

    if mode not in ("qfq", "hfq"):
        raise ValueError(
            f"不支持的复权模式: {mode}（可用 qfq / hfq / none）"
        )

    date_column = None

    for candidate in ("date", "trade_time", "trade_date"):
        if candidate in df.columns:
            date_column = candidate
            break

    if date_column is None:
        raise ValueError("行情数据缺少日期列（date / trade_time）")

    result = df.copy()

    factor = build_back_factor(result[date_column], factors)

    if mode == "hfq":
        multiplier = factor
    else:
        base = latest_back_factor(factors)
        multiplier = factor / base if base else factor
        # Baostock 的前复权因子只保留 6 位小数（foreAdjustFactor），
        # 本地按同样规则舍入，才能与数据源逐位一致
        multiplier = multiplier.round(6)

    for column in price_columns:
        if column in result.columns:
            result[column] = (
                pd.to_numeric(result[column], errors="coerce")
                * multiplier
            )

    result["adjust_factor"] = multiplier.to_numpy()

    return result
