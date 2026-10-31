"""量价分析 + 趋势 + 支撑压力 离线测试（不联网、不写库）"""

import numpy as np
import pandas as pd
import pytest

from data.analysis import (
    add_avg_volume,
    add_turn_analysis,
    add_volume_analysis,
    add_volume_ratio,
    analyze_trend,
    find_support_resistance,
    volume_price_status,
)


def make_bars(n: int = 70, seed: int = 1):
    """构造 n 根日线（含 volume / turn）"""

    rng = np.random.default_rng(seed)
    close = 10.0 + np.cumsum(rng.normal(0.1, 0.5, n))
    open_ = close + rng.normal(0.0, 0.2, n)
    high = np.maximum(open_, close) + rng.uniform(0.0, 0.5, n)
    low = np.minimum(open_, close) - rng.uniform(0.0, 0.5, n)

    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=n, freq="B"),
            "open": open_,
            "high": high,
            "low": low,
            "close": close,
            "preclose": np.concatenate([[np.nan], close[:-1]]),
            "volume": rng.uniform(1e5, 1e6, n),
            "amount": rng.uniform(1e7, 1e8, n),
            "turn": rng.uniform(0.1, 3.0, n),
        }
    )


def make_trend_bars(n: int = 80, direction: str = "up"):
    """单调上升/下降序列，便于验证趋势判断"""

    if direction == "up":
        close = np.linspace(10.0, 30.0, n)
    else:
        close = np.linspace(30.0, 10.0, n)

    high = close + 0.5
    low = close - 0.5

    return pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=n, freq="B"),
            "open": close,
            "high": high,
            "low": low,
            "close": close,
            "preclose": np.concatenate([[np.nan], close[:-1]]),
            "volume": np.full(n, 1e5),
            "turn": np.full(n, 1.0),
        }
    )


# =========================
# add_avg_volume
# =========================

def test_add_avg_volume_values():
    df = pd.DataFrame({"volume": [100.0, 200.0, 300.0, 400.0, 500.0]})

    result = add_avg_volume(df, windows=(5,))

    assert "ma_vol_5" in result.columns
    assert result["ma_vol_5"].iloc[4] == pytest.approx(300.0)
    assert result["ma_vol_5"].iloc[0] != result["ma_vol_5"].iloc[0]  # NaN


def test_add_avg_volume_default_columns():
    df = make_bars(n=15)

    result = add_avg_volume(df)

    assert "ma_vol_5" in result.columns
    assert "ma_vol_10" in result.columns


# =========================
# add_volume_ratio
# =========================

def test_add_volume_ratio_manual():
    """前 N 日均量口径：第 N+1 根起有值"""

    volumes = [100.0, 200.0, 300.0, 400.0, 500.0, 600.0]
    df = pd.DataFrame({"volume": volumes})

    result = add_volume_ratio(df, window=5)

    # 前 5 根无前 5 日均量 → NaN
    assert result["volume_ratio"].iloc[4] != result["volume_ratio"].iloc[4]

    # 第 6 根：600 / mean([100,200,300,400,500]) = 600 / 300 = 2.0
    assert result["volume_ratio"].iloc[5] == pytest.approx(2.0)


def test_add_volume_ratio_does_not_mutate_input():
    df = pd.DataFrame({"volume": [100.0, 200.0, 300.0]})

    add_volume_ratio(df)

    assert "volume_ratio" not in df.columns


def test_volume_price_status_bullish_surge():
    """放量上涨：volume_ratio >= 1.5 且收涨"""

    df = make_bars(n=20)
    df.loc[df.index[-1], "volume"] = 2_000_000.0  # 前 5 日均量远小于此
    df.loc[df.index[-1], "close"] = df.loc[df.index[-2], "close"] * 1.03  # 收涨

    status = volume_price_status(df)

    assert status["status"] == "放量上涨"
    assert status["volume_ratio"] is not None


def test_volume_price_status_bearish_surge():
    """放量下跌"""

    df = make_bars(n=20)
    df.loc[df.index[-1], "volume"] = 2_000_000.0
    df.loc[df.index[-1], "close"] = df.loc[df.index[-2], "close"] * 0.97

    status = volume_price_status(df)

    assert status["status"] == "放量下跌"


def test_volume_price_status_insufficient():
    """样本不足返回数据不足"""

    df = pd.DataFrame({"close": [1.0, 2.0]})

    status = volume_price_status(df)

    assert status["status"] == "数据不足"


def test_add_turn_analysis_columns():
    df = make_bars(n=15)

    result = add_turn_analysis(df)

    assert "turn_ma_5" in result.columns
    assert "turn_ratio" in result.columns
    assert result["turn_ma_5"].iloc[4] == pytest.approx(
        df["turn"].iloc[:5].mean()
    )


def test_add_volume_analysis_all():
    df = make_bars(n=15)

    result = add_volume_analysis(df)

    for column in ("ma_vol_5", "ma_vol_10", "volume_ratio", "turn_ma_5", "turn_ratio"):
        assert column in result.columns


# =========================
# analyze_trend
# =========================

def test_analyze_trend_up():
    df = make_trend_bars(direction="up")

    result = analyze_trend(df)

    assert result["trend"] == "上升趋势"
    assert result["alignment"] == "多头排列"
    assert result["ma20_direction"] == "上行"
    assert result["price_vs_ma20"] is not None


def test_analyze_trend_down():
    df = make_trend_bars(direction="down")

    result = analyze_trend(df)

    assert result["trend"] == "下降趋势"
    assert result["alignment"] == "空头排列"
    assert result["ma20_direction"] == "下行"


def test_analyze_trend_insufficient():
    result = analyze_trend(pd.DataFrame())

    assert result["trend"] == "数据不足"


# =========================
# find_support_resistance
# =========================

def test_find_support_contains_low():
    """V 型：窗口内低点应进入支撑候选"""

    close = np.concatenate(
        [np.linspace(20.0, 10.0, 20), np.linspace(10.0, 18.0, 20)]
    )
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=40, freq="B"),
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "preclose": np.concatenate([[np.nan], close[:-1]]),
            "volume": np.full(40, 1e5),
            "turn": np.full(40, 1.0),
        }
    )

    result = find_support_resistance(df, lookback=40)

    prices = [item["price"] for item in result["supports"]]

    assert min(prices) <= 10.5  # 低点 10 附近应出现
    assert any(item["type"] == "阶段低点" for item in result["supports"])


def test_find_resistance_contains_high():
    """倒 V 型：高点应进入压力候选"""

    close = np.concatenate(
        [np.linspace(10.0, 20.0, 20), np.linspace(20.0, 12.0, 20)]
    )
    df = pd.DataFrame(
        {
            "date": pd.date_range("2026-01-01", periods=40, freq="B"),
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "preclose": np.concatenate([[np.nan], close[:-1]]),
            "volume": np.full(40, 1e5),
            "turn": np.full(40, 1.0),
        }
    )

    result = find_support_resistance(df, lookback=40)

    prices = [item["price"] for item in result["resistances"]]

    assert max(prices) >= 19.5
    assert any(item["type"] == "阶段高点" for item in result["resistances"])


def test_find_support_resistance_insufficient():
    result = find_support_resistance(pd.DataFrame())

    assert result["supports"] == []
    assert result["resistances"] == []
