"""量价分析 + 趋势判断 + 支撑压力（阶段 4.2 / 4.3）

输入：日线 DataFrame（含 date/open/high/low/close/preclose/volume/turn 等列，
      可由 daily_bar_repository.get_daily_bars + adjustment.apply_adjust 构造）。
输出：追加列后的 DataFrame 副本（不修改入参），或结构化 dict。

约定：
- 与 data/indicators.py 一致：纯 pandas 自实现、缺列容错、数据不足返回 NaN 不报错。
- 量价分析依赖日线库已有 volume（股）/ turn（换手率 %）列。
"""

import numpy as np
import pandas as pd

from data.indicators import add_ma, _numeric, _has_columns

VOLUME_MA_WINDOWS = (5, 10)
VOLUME_RATIO_WINDOW = 5
TURN_MA_WINDOW = 5


# =========================
# 4.2 量价分析层
# =========================

def add_avg_volume(
    df: pd.DataFrame,
    windows=VOLUME_MA_WINDOWS,
) -> pd.DataFrame:
    """均量线：成交量 N 日均值

    列名：ma_vol_{window}
    """

    frame = _numeric(df)

    if not _has_columns(frame, ("volume",)):
        return frame

    for window in windows:
        frame[f"ma_vol_{window}"] = (
            frame["volume"].rolling(window=window, min_periods=window).mean()
        )

    return frame


def add_volume_ratio(
    df: pd.DataFrame,
    window: int = VOLUME_RATIO_WINDOW,
) -> pd.DataFrame:
    """量比：当日成交量 / 过去 N 日平均成交量（不含当日）

    列名：volume_ratio
    口径：A 股常用量比为当日每分钟均量对比近 5 日每分钟均量，
    日线场景简化为「当日成交量 / 前 N 日均量」，>1.5 视为放量、<0.8 视为缩量。
    """

    frame = _numeric(df)

    if not _has_columns(frame, ("volume",)):
        return frame

    previous_avg = (
        frame["volume"].shift(1).rolling(window=window, min_periods=window).mean()
    )

    frame["volume_ratio"] = frame["volume"] / previous_avg.replace(0.0, np.nan)
    return frame


def add_turn_analysis(
    df: pd.DataFrame,
    window: int = TURN_MA_WINDOW,
) -> pd.DataFrame:
    """换手率分析：换手率均值与相对倍数

    列名：turn_ma_{window} / turn_ratio
    turn_ratio = 当日换手率 / 近 window 日平均换手率。
    """

    frame = _numeric(df)

    if not _has_columns(frame, ("turn",)):
        return frame

    frame[f"turn_ma_{window}"] = (
        frame["turn"].rolling(window=window, min_periods=window).mean()
    )
    frame["turn_ratio"] = (
        frame["turn"] / frame[f"turn_ma_{window}"].replace(0.0, np.nan)
    )
    return frame


def volume_price_status(df: pd.DataFrame) -> dict:
    """最新一根 K 线的量价配合状态

    规则（简化、可解释）：
    - 放量上涨：收盘上涨且 volume_ratio >= 1.5
    - 放量下跌：收盘下跌且 volume_ratio >= 1.5
    - 温和放量上涨：上涨且 1.0 <= volume_ratio < 1.5
    - 缩量回调：下跌且 volume_ratio < 0.8
    - 缩量整理：涨跌幅绝对值很小且缩量
    - 平量整理：其余

    返回 dict：status（中文状态）/ volume_ratio / pct_chg / 说明。
    数据不足或缺列时返回 None 型字段的 dict。
    """

    frame = _numeric(df)

    if frame.empty or not _has_columns(frame, ("close",)):
        return {
            "status": "数据不足",
            "volume_ratio": None,
            "pct_chg": None,
            "detail": "缺少足够行情数据",
        }

    frame = add_volume_ratio(frame)

    latest = frame.iloc[-1]
    ratio = latest.get("volume_ratio")

    if pd.isna(ratio):
        return {
            "status": "数据不足",
            "volume_ratio": None,
            "pct_chg": None,
            "detail": "量比数据不足（样本 < 6 根）",
        }

    close = float(latest["close"])
    prev_close = float(latest.get("preclose", np.nan))

    if pd.isna(prev_close) or prev_close == 0.0:
        pct = None
        direction = 0.0
    else:
        pct = (close - prev_close) / prev_close * 100.0
        direction = 1.0 if pct > 0.05 else (-1.0 if pct < -0.05 else 0.0)

    ratio_value = float(ratio)

    if ratio_value >= 1.5 and direction > 0:
        status = "放量上涨"
        detail = "成交量显著放大且收涨，多方力量较强"
    elif ratio_value >= 1.5 and direction < 0:
        status = "放量下跌"
        detail = "成交量显著放大且收跌，空方抛压明显"
    elif ratio_value >= 1.0 and direction > 0:
        status = "温和放量上涨"
        detail = "量能温和放大配合上涨，走势健康"
    elif ratio_value < 0.8 and direction < 0:
        status = "缩量回调"
        detail = "下跌但量能萎缩，抛压有限，可观察企稳"
    elif ratio_value < 0.8 and direction == 0:
        status = "缩量整理"
        detail = "涨跌幅度小且缩量，多空观望"
    else:
        status = "平量整理"
        detail = "量能平稳，方向待选择"

    return {
        "status": status,
        "volume_ratio": round(ratio_value, 2),
        "pct_chg": round(pct, 2) if pct is not None else None,
        "detail": detail,
    }


# =========================
# 4.3 趋势判断
# =========================

TREND_MA_WINDOWS = (5, 10, 20, 60)


def _trend_ma_alignment(frame: pd.DataFrame, windows) -> str:
    """均线排列：多头 / 空头 / 纠缠（基于最新值比较）"""

    values = []

    for window in windows:
        column = f"ma_{window}"

        if column not in frame.columns:
            return "数据不足"

        value = frame[column].iloc[-1]

        if pd.isna(value):
            return "数据不足"

        values.append(float(value))

    if all(values[i] > values[i + 1] for i in range(len(values) - 1)):
        return "多头排列"
    if all(values[i] < values[i + 1] for i in range(len(values) - 1)):
        return "空头排列"

    return "均线纠缠"


def analyze_trend(
    df: pd.DataFrame,
    ma_windows=TREND_MA_WINDOWS,
) -> dict:
    """趋势判断：均线排列 + 价格相对位置 + MA20 方向

    返回 dict：
    - trend：上升趋势 / 下降趋势 / 震荡
    - alignment：多头排列 / 空头排列 / 均线纠缠 / 数据不足
    - ma20_direction：上行 / 下行 / 走平
    - price_vs_ma20 / price_vs_ma60：最新收盘价偏离百分比
    - recent_percent：近 20 日涨跌幅
    """

    frame = _numeric(df)

    if frame.empty or not _has_columns(frame, ("close",)):
        return {
            "trend": "数据不足",
            "alignment": "数据不足",
            "ma20_direction": "数据不足",
            "price_vs_ma20": None,
            "price_vs_ma60": None,
            "recent_percent": None,
        }

    for window in ma_windows:
        if f"ma_{window}" not in frame.columns:
            frame = add_ma(frame, window=window)

    alignment = _trend_ma_alignment(frame, ma_windows)
    close = float(frame["close"].iloc[-1])

    ma20 = frame.get("ma_20")
    ma60 = frame.get("ma_60")

    if ma20 is not None and not pd.isna(ma20.iloc[-1]):
        ma20_value = float(ma20.iloc[-1])
        price_vs_ma20 = (close - ma20_value) / ma20_value * 100.0
    else:
        ma20_value = None
        price_vs_ma20 = None

    if ma60 is not None and not pd.isna(ma60.iloc[-1]):
        ma60_value = float(ma60.iloc[-1])
        price_vs_ma60 = (close - ma60_value) / ma60_value * 100.0
    else:
        price_vs_ma60 = None

    # MA20 方向：当前值 vs 5 个交易日前
    ma20_direction = "数据不足"

    if ma20 is not None and len(frame) >= 6:
        latest_ma20 = ma20.iloc[-1]
        prev_ma20 = ma20.iloc[-6]

        if not pd.isna(latest_ma20) and not pd.isna(prev_ma20):
            diff = float(latest_ma20) - float(prev_ma20)
            pct = diff / abs(float(prev_ma20)) * 100.0 if prev_ma20 else 0.0
            if pct > 0.1:
                ma20_direction = "上行"
            elif pct < -0.1:
                ma20_direction = "下行"
            else:
                ma20_direction = "走平"

    if alignment == "多头排列":
        trend = "上升趋势"
    elif alignment == "空头排列":
        trend = "下降趋势"
    else:
        trend = "震荡"

    # 近 20 日涨跌幅
    if len(frame) >= 21 and close:
        base = float(frame["close"].iloc[-21])

        if base:
            recent_percent = (close - base) / base * 100.0
        else:
            recent_percent = None
    else:
        recent_percent = None

    return {
        "trend": trend,
        "alignment": alignment,
        "ma20_direction": ma20_direction,
        "price_vs_ma20": round(price_vs_ma20, 2) if price_vs_ma20 is not None else None,
        "price_vs_ma60": round(price_vs_ma60, 2) if price_vs_ma60 is not None else None,
        "recent_percent": round(recent_percent, 2) if recent_percent is not None else None,
    }


# =========================
# 4.3 支撑位与压力位
# =========================

def _fractal_extremes(
    frame: pd.DataFrame,
    column: str,
    window: int,
    kind: str,
):
    """窗口内找局部极值点（kind='low' 低点 / 'high' 高点），返回 [(price, 距今K线数)]"""

    series = frame[column]
    n = len(frame)
    points = []

    for i in range(window, n - window):
        segment = series.iloc[i - window: i + window + 1]

        if segment.isna().any():
            continue

        center = float(series.iloc[i])

        if kind == "low" and center <= float(segment.min()):
            points.append((center, n - 1 - i))
        elif kind == "high" and center >= float(segment.max()):
            points.append((center, n - 1 - i))

    # 去重：同价位区间只保留最近一次
    unique = []

    for price, days_ago in points:
        if not unique or abs(price - unique[-1][0]) > 1e-9:
            unique.append((price, days_ago))
        else:
            unique[-1] = (price, min(days_ago, unique[-1][1]))

    return unique


def _nearest_round_level(price: float, step: float) -> float:
    """邻近整数/半整数关口：向下取整到 step 的倍数"""

    if step <= 0 or price <= 0:
        return float(price)

    return float(np.floor(price / step) * step)


def find_support_resistance(
    df: pd.DataFrame,
    lookback: int = 60,
    top_n: int = 3,
    allow_round: bool = True,
) -> dict:
    """支撑位与压力位

    支撑候选：
    - lookback 窗口内的局部低点（fractal，左右各 3 根）
    - BOLL 下轨（若列存在）
    - MA60 / MA20（若列存在，且低于现价附近）
    - 整数关口（向下取整的 1 元台阶，仅当附近无更近候选时补充）

    压力候选：
    - lookback 窗口内的局部高点
    - BOLL 上轨
    - MA20 / MA60（高于现价附近时）
    - 整数关口（向上）

    返回 dict：
    - supports：[{price, type, days_ago, detail}]
    - resistances：[{price, type, days_ago, detail}]
    按距离现价从近到远排序，最多 top_n 个。
    """

    frame = _numeric(df)

    if frame.empty or not _has_columns(frame, ("close", "high", "low")):
        return {"supports": [], "resistances": []}

    window = frame.tail(lookback).reset_index(drop=True)
    close = float(frame["close"].iloc[-1])

    candidates_support = []
    candidates_resistance = []

    for price, days_ago in _fractal_extremes(window, "low", 3, "low"):
        if price < close * 0.995:
            candidates_support.append(
                {
                    "price": round(price, 2),
                    "type": "阶段低点",
                    "days_ago": int(days_ago),
                    "detail": f"近 {lookback} 日局部低点（{int(days_ago)} 日前）",
                }
            )

    for price, days_ago in _fractal_extremes(window, "high", 3, "high"):
        if price > close * 1.005:
            candidates_resistance.append(
                {
                    "price": round(price, 2),
                    "type": "阶段高点",
                    "days_ago": int(days_ago),
                    "detail": f"近 {lookback} 日局部高点（{int(days_ago)} 日前）",
                }
            )

    for column, label in (("boll_lower", "BOLL 下轨"), ("ma_60", "MA60"), ("ma_20", "MA20")):
        if column in frame.columns:
            value = frame[column].iloc[-1]

            if pd.isna(value) or float(value) <= 0:
                continue

            price = float(value)

            if price <= close * 1.02:
                candidates_support.append(
                    {
                        "price": round(price, 2),
                        "type": label,
                        "days_ago": 0,
                        "detail": f"{label} 当前值",
                    }
                )
            elif price >= close * 0.98:
                candidates_resistance.append(
                    {
                        "price": round(price, 2),
                        "type": label,
                        "days_ago": 0,
                        "detail": f"{label} 当前值",
                    }
                )

    if allow_round:
        step = 1.0 if close < 100 else 10.0

        support_level = _nearest_round_level(close * 0.98, step)
        if support_level < close:
            candidates_support.append(
                {
                    "price": round(support_level, 2),
                    "type": "整数关口",
                    "days_ago": 0,
                    "detail": f"下方整数关口（{step:.0f} 元台阶）",
                }
            )

        resistance_level = _nearest_round_level(close * 1.02, step) + step
        if resistance_level > close:
            candidates_resistance.append(
                {
                    "price": round(resistance_level, 2),
                    "type": "整数关口",
                    "days_ago": 0,
                    "detail": f"上方整数关口（{step:.0f} 元台阶）",
                }
            )

    def sort_key(item):
        return abs(item["price"] - close)

    def dedupe(items):
        seen = []
        result = []

        for item in items:
            price = item["price"]

            if any(abs(price - old["price"]) < 0.01 for old in seen):
                continue

            seen.append(item)
            result.append(item)

        return result

    supports = dedupe(sorted(candidates_support, key=sort_key))[:top_n]
    resistances = dedupe(sorted(candidates_resistance, key=sort_key))[:top_n]

    return {
        "supports": supports,
        "resistances": resistances,
    }


# =========================
# 便捷汇总
# =========================

def add_volume_analysis(
    df: pd.DataFrame,
    volume_ma_windows=VOLUME_MA_WINDOWS,
    volume_ratio_window: int = VOLUME_RATIO_WINDOW,
    turn_ma_window: int = TURN_MA_WINDOW,
) -> pd.DataFrame:
    """一次性追加量价分析列：均量 / 量比 / 换手率均线与倍数"""

    frame = add_avg_volume(df, windows=volume_ma_windows)
    frame = add_volume_ratio(frame, window=volume_ratio_window)
    frame = add_turn_analysis(frame, window=turn_ma_window)
    return frame
