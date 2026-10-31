"""技术指标综合评分（阶段 4.4）

输入：日线 DataFrame（含 close/high/low/volume/turn 等列）。
评分函数内部自动补齐指标列（indicators.add_all_indicators + analysis 量价列）。

口径（可解释、加权、基准 50 分，0~100 封顶）：
- 均线排列       多头 +15 / 空头 -15
- 收盘 vs MA20  上方 +8 / 下方 -8
- MACD          DIF>DEA +10；近 5 日金叉额外 +5；反之 -10 / -5
- RSI14         超卖(<30) +10；偏强(55~70) -4；超买(>70) -10；其余 0~+4
- KDJ           K>D +8 / K<D -8；J 超买(>100) -5；J 超卖(<0) +5
- BOLL          收盘低于下轨 +6（超卖机会）；高于上轨 -6（超买风险）
- 量价配合       放量上涨 +8；温和放量上涨 +4；放量下跌 -8；缩量回调 -4

风险等级：由最新波动率（ATR14/收盘价）与超买超卖叠加判断。
返回 dict：score / signal / risk_level / items / 说明。
"""

import numpy as np
import pandas as pd

from data.indicators import add_all_indicators, add_atr
from data.analysis import (
    add_avg_volume,
    add_volume_ratio,
    add_turn_analysis,
    volume_price_status,
)


def _ensure_columns(df: pd.DataFrame) -> pd.DataFrame:
    """补齐评分所需的指标列（幂等：已有列不重复计算）"""

    frame = df.copy()

    if "atr_14" not in frame.columns:
        frame = add_atr(frame, period=14)

    if "rsi_14" not in frame.columns or "dif" not in frame.columns:
        frame = add_all_indicators(frame)

    if "ma_vol_5" not in frame.columns:
        frame = add_avg_volume(frame)

    if "volume_ratio" not in frame.columns:
        frame = add_volume_ratio(frame)

    if "turn_ma_5" not in frame.columns:
        frame = add_turn_analysis(frame)

    return frame


def _latest(frame: pd.DataFrame, column: str):
    """取列最新值，缺列或全 NaN 返回 None"""

    if column not in frame.columns:
        return None

    value = frame[column].iloc[-1]

    if pd.isna(value):
        return None

    return float(value)


def _macd_bias(frame: pd.DataFrame) -> int:
    """MACD：DIF 与 DEA 关系 + 近 5 日金叉/死叉"""

    score = 0

    dif = _latest(frame, "dif")
    dea = _latest(frame, "dea")

    if dif is None or dea is None:
        return 0

    score += 10 if dif > dea else -10

    tail = frame.tail(6)

    if len(tail) >= 2:
        prev_dif = tail["dif"].iloc[-2]
        prev_dea = tail["dea"].iloc[-2]
        last_dif = tail["dif"].iloc[-1]
        last_dea = tail["dea"].iloc[-1]

        if not pd.isna(prev_dif) and not pd.isna(prev_dea):
            cross_up = (prev_dif <= prev_dea) and (last_dif > last_dea)
            cross_down = (prev_dif >= prev_dea) and (last_dif < last_dea)

            score += 5 if cross_up else (-5 if cross_down else 0)

    return score


def _rsi_bias(value: float) -> int:
    """RSI14：超卖/超买与强弱区间"""

    if value < 30:
        return 10
    if value < 45:
        return 4
    if value <= 55:
        return 0
    if value <= 70:
        return -4
    return -10


def _kdj_bias(frame: pd.DataFrame) -> int:
    """KDJ：K/D 关系与 J 超买超卖"""

    score = 0
    k = _latest(frame, "kdj_k")
    d = _latest(frame, "kdj_d")
    j = _latest(frame, "kdj_j")

    if k is not None and d is not None:
        score += 8 if k > d else -8

    if j is not None:
        if j > 100:
            score -= 5
        elif j < 0:
            score += 5

    return score


def _boll_bias(frame: pd.DataFrame) -> int:
    """BOLL：收盘价相对上下轨"""

    close = _latest(frame, "close")
    upper = _latest(frame, "boll_upper")
    lower = _latest(frame, "boll_lower")

    if close is None or upper is None or lower is None:
        return 0

    if close < lower:
        return 6
    if close > upper:
        return -6
    return 0


def _ma_alignment_score(frame: pd.DataFrame) -> tuple[int, str]:
    """均线排列 + 收盘价相对 MA20"""

    score = 0
    alignment = "数据不足"

    if all(f"ma_{w}" in frame.columns for w in (5, 10, 20, 60)):
        values = [float(frame[f"ma_{w}"].iloc[-1]) for w in (5, 10, 20, 60)]

        if not any(np.isnan(values)):
            if all(values[i] > values[i + 1] for i in range(3)):
                score += 15
                alignment = "多头排列"
            elif all(values[i] < values[i + 1] for i in range(3)):
                score -= 15
                alignment = "空头排列"
            else:
                alignment = "均线纠缠"

    close = _latest(frame, "close")
    ma20 = _latest(frame, "ma_20")

    if close is not None and ma20 is not None:
        score += 8 if close > ma20 else -8

    return score, alignment


def _volume_score(frame: pd.DataFrame) -> int:
    """量价配合打分（基于最新状态）"""

    status = volume_price_status(frame)

    mapping = {
        "放量上涨": 8,
        "温和放量上涨": 4,
        "放量下跌": -8,
        "缩量回调": -4,
        "缩量整理": 0,
        "平量整理": 0,
    }

    return mapping.get(status.get("status"), 0)


def _volatility_ratio(frame: pd.DataFrame) -> float | None:
    """波动率：ATR14 / 收盘价（%）"""

    atr = _latest(frame, "atr_14")
    close = _latest(frame, "close")

    if atr is None or close is None or close <= 0:
        return None

    return atr / close * 100.0


def score_technical(df: pd.DataFrame) -> dict:
    """技术指标综合评分

    返回 dict：
    - score：0~100 整数
    - signal：看多 / 中性 / 看空
    - risk_level：低 / 中 / 高
    - items：信号依据列表 [{name, impact, detail}]，impact 为 positive / negative / neutral
    - note：综合说明
    """

    frame = _ensure_columns(df)

    if frame.empty or "close" not in frame.columns:
        return {
            "score": 0,
            "signal": "数据不足",
            "risk_level": "数据不足",
            "items": [],
            "note": "缺少行情数据，无法评分",
        }

    items = []
    score = 50

    ma_score, alignment = _ma_alignment_score(frame)
    score += ma_score

    if alignment != "数据不足":
        items.append(
            {
                "name": "均线排列",
                "impact": "positive" if ma_score > 0 else ("negative" if ma_score < 0 else "neutral"),
                "detail": f"{alignment}，MA5/10/20/60 依次{'递增' if ma_score > 0 else '递减'}"
                if ma_score else f"{alignment}",
            }
        )

    close = _latest(frame, "close")
    ma20 = _latest(frame, "ma_20")

    if close is not None and ma20 is not None:
        pct = (close - ma20) / ma20 * 100.0
        items.append(
            {
                "name": "MA20 位置",
                "impact": "positive" if close > ma20 else "negative",
                "detail": f"收盘价 {'高于' if close > ma20 else '低于'} MA20（{pct:+.2f}%）",
            }
        )

    macd_score = _macd_bias(frame)
    score += macd_score

    dif = _latest(frame, "dif")
    dea = _latest(frame, "dea")

    if dif is not None and dea is not None:
        items.append(
            {
                "name": "MACD",
                "impact": "positive" if macd_score > 0 else ("negative" if macd_score < 0 else "neutral"),
                "detail": f"DIF {'高于' if dif > dea else '低于'} DEA"
                + ("，近 5 日金叉" if macd_score >= 15 else "")
                + ("，近 5 日死叉" if macd_score <= -15 else ""),
            }
        )

    rsi = _latest(frame, "rsi_14")

    if rsi is not None:
        rsi_score = _rsi_bias(rsi)
        score += rsi_score

        if rsi < 30:
            detail = "超卖区间，存在反弹需求"
        elif rsi > 70:
            detail = "超买区间，短期回调风险"
        elif rsi < 45:
            detail = "偏弱区间"
        elif rsi <= 55:
            detail = "中性区间"
        else:
            detail = "偏强区间"

        items.append(
            {
                "name": "RSI(14)",
                "impact": "positive" if rsi_score > 0 else ("negative" if rsi_score < 0 else "neutral"),
                "detail": f"RSI={rsi:.1f}，{detail}",
            }
        )

    kdj_score = _kdj_bias(frame)
    score += kdj_score

    k = _latest(frame, "kdj_k")
    d = _latest(frame, "kdj_d")
    j = _latest(frame, "kdj_j")

    if k is not None and d is not None:
        items.append(
            {
                "name": "KDJ",
                "impact": "positive" if kdj_score > 0 else ("negative" if kdj_score < 0 else "neutral"),
                "detail": f"K={k:.1f} D={d:.1f} J={j:.1f}，"
                + ("K 线在 D 线上方" if k > d else "K 线在 D 线下方"),
            }
        )

    boll_score = _boll_bias(frame)
    score += boll_score

    if boll_score != 0:
        items.append(
            {
                "name": "BOLL",
                "impact": "positive" if boll_score > 0 else "negative",
                "detail": "收盘价低于下轨（超卖机会）" if boll_score > 0 else "收盘价高于上轨（超买风险）",
            }
        )

    volume_score = _volume_score(frame)
    score += volume_score

    vp_status = volume_price_status(frame)
    items.append(
        {
            "name": "量价配合",
            "impact": "positive" if volume_score > 0 else ("negative" if volume_score < 0 else "neutral"),
            "detail": vp_status.get("detail", ""),
        }
    )

    score = int(np.clip(round(score), 0, 100))

    if score >= 60:
        signal = "看多"
    elif score <= 40:
        signal = "看空"
    else:
        signal = "中性"

    # 风险等级：波动率 + 超买超卖叠加
    volatility = _volatility_ratio(frame)
    risk_points = 0.0

    if volatility is not None:
        if volatility >= 4.0:
            risk_points += 2
        elif volatility >= 2.0:
            risk_points += 1

    if rsi is not None and rsi > 75:
        risk_points += 1

    if j is not None and j > 110:
        risk_points += 1

    if rsi is not None and rsi < 20:
        risk_points += 1

    if risk_points >= 3:
        risk_level = "高"
    elif risk_points >= 1:
        risk_level = "中"
    else:
        risk_level = "低"

    note = (
        f"综合得分 {score}/100（{signal}），风险等级 {risk_level}。"
        f"波动率 {'%.2f%%' % volatility if volatility is not None else '未知'}。"
        "评分仅基于技术指标，不构成投资建议；数据不足或处于观望区时建议继续观察。"
    )

    return {
        "score": score,
        "signal": signal,
        "risk_level": risk_level,
        "items": items,
        "note": note,
    }
