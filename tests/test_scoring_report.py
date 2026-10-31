"""技术指标综合评分 + 报告生成 离线测试（不联网、不写库）"""

import numpy as np
import pandas as pd
import pytest

from data.report import build_technical_report
from data.scoring import score_technical


def make_trend_bars(n: int = 90, direction: str = "up", final_surge: bool = False):
    """单调上升/下降序列，可选最后一根放量拉升"""

    if direction == "up":
        close = np.linspace(10.0, 25.0, n)
    else:
        close = np.linspace(25.0, 10.0, n)

    close = close.copy()

    if final_surge:
        close[-1] = close[-2] * 1.03

    volume = np.full(n, 1e5)
    turn = np.full(n, 1.0)

    if final_surge:
        volume[-1] = 5e5  # 显著放量
        turn[-1] = 2.5

    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=n, freq="B"),
            "open": close,
            "high": close + 0.5,
            "low": close - 0.5,
            "close": close,
            "preclose": np.concatenate([[np.nan], close[:-1]]),
            "volume": volume,
            "amount": volume * close,
            "turn": turn,
            "pct_chg": np.concatenate(
                [[np.nan], np.diff(close) / close[:-1] * 100.0]
            ),
        }
    )


def test_score_technical_bullish():
    """多头 + 放量 → 高分看多"""

    df = make_trend_bars(direction="up", final_surge=True)

    result = score_technical(df)

    assert result["score"] >= 60
    assert result["signal"] == "看多"
    assert result["risk_level"] in ("低", "中", "高")
    assert result["items"], "信号依据列表不应为空"


def test_score_technical_bearish():
    """空头 → 低分看空"""

    df = make_trend_bars(direction="down")

    result = score_technical(df)

    assert result["score"] <= 40
    assert result["signal"] == "看空"


def test_score_technical_items_positive_negative():
    """信号依据包含利多/利空方向标注"""

    df = make_trend_bars(direction="up", final_surge=True)

    result = score_technical(df)

    impacts = {item["impact"] for item in result["items"]}

    assert "positive" in impacts
    # 量价配合在放量上涨时为 positive
    vp = next(item for item in result["items"] if item["name"] == "量价配合")
    assert vp["impact"] == "positive"


def test_score_technical_insufficient():
    result = score_technical(pd.DataFrame())

    assert result["signal"] == "数据不足"
    assert result["items"] == []


def test_score_technical_does_not_mutate_input():
    df = make_trend_bars(direction="up")

    score_technical(df)

    assert "dif" not in df.columns


# =========================
# build_technical_report
# =========================

def test_build_technical_report_structure():
    df = make_trend_bars(direction="up", final_surge=True)

    trend = {"trend": "上升趋势", "alignment": "多头排列", "ma20_direction": "上行",
             "price_vs_ma20": 5.0, "price_vs_ma60": 10.0, "recent_percent": 8.0}
    sr = {
        "supports": [{"price": 20.5, "type": "阶段低点", "days_ago": 3, "detail": "近 60 日局部低点（3 日前）"}],
        "resistances": [{"price": 26.0, "type": "阶段高点", "days_ago": 1, "detail": "近 60 日局部高点（1 日前）"}],
    }
    score = score_technical(df)

    text = build_technical_report(
        {"code": "600001", "name": "测试股票"},
        df,
        trend,
        sr,
        score,
    )

    for section in (
        "# 技术分析报告",
        "## 一、当前行情",
        "## 二、技术指标明细",
        "## 三、综合评分",
        "## 四、支撑位与压力位",
        "## 五、综合研判与观望建议",
        "*免责声明",
    ):
        assert section in text, f"报告缺少章节：{section}"

    assert "600001" in text
    assert "测试股票" in text
    assert "上升趋势" in text


def test_build_technical_report_empty():
    text = build_technical_report(
        {"code": "600001", "name": "测试股票"},
        pd.DataFrame(),
        {},
        {},
        {"score": 0, "signal": "数据不足", "risk_level": "数据不足", "items": []},
    )

    assert "无行情数据" in text
