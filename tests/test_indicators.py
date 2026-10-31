"""技术指标计算层离线测试（不联网、不写正式库）"""

import numpy as np
import pandas as pd
import pytest

from data.indicators import (
    add_all_indicators,
    add_atr,
    add_boll,
    add_ema,
    add_kdj,
    add_ma,
    add_macd,
    add_rsi,
)


def make_bars(n: int = 10, seed: int = 1):
    """构造 n 根日线（含 date/open/high/low/close/preclose/volume）"""

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


def test_add_ma_basic_values():
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0]})

    result = add_ma(df, window=3)

    values = result["ma_3"]
    assert values.iloc[0] != values.iloc[0]  # NaN
    assert values.iloc[1] != values.iloc[1]  # NaN
    assert values.iloc[2] == pytest.approx(2.0)
    assert values.iloc[3] == pytest.approx(3.0)
    assert values.iloc[4] == pytest.approx(4.0)


def test_add_ma_does_not_mutate_input():
    df = pd.DataFrame({"close": [1.0, 2.0, 3.0]})

    add_ma(df, window=3)

    assert "ma_3" not in df.columns


def test_add_ema_matches_manual():
    """EMA(3) adjust=False 手算验证：alpha = 2/(3+1) = 0.5"""

    df = pd.DataFrame({"close": [1.0, 2.0, 3.0, 4.0, 5.0]})

    result = add_ema(df, span=3)

    expected = [1.0, 1.5, 2.25, 3.125, 4.0625]

    assert np.allclose(result["ema_3"], expected)


def test_add_macd_relationship():
    """DIF = EMA12 - EMA26；DEA = EMA9(DIF)；MACD柱 = 2*(DIF-DEA)"""

    df = make_bars(n=60)

    result = add_macd(df)

    close = result["close"]
    ema12 = close.ewm(span=12, adjust=False).mean()
    ema26 = close.ewm(span=26, adjust=False).mean()
    dif_manual = ema12 - ema26
    dea_manual = dif_manual.ewm(span=9, adjust=False).mean()

    assert np.allclose(result["dif"].dropna(), dif_manual.dropna())
    assert np.allclose(result["dea"].dropna(), dea_manual.dropna())
    assert np.allclose(
        result["macd"].dropna(), (2.0 * (dif_manual - dea_manual)).dropna()
    )


def test_add_rsi_all_up_is_100():
    """单边上涨 → RSI = 100"""

    df = pd.DataFrame({"close": list(range(1, 21))})

    result = add_rsi(df, period=14)

    assert result["rsi_14"].iloc[-1] == pytest.approx(100.0)


def test_add_rsi_all_down_is_0():
    """单边下跌 → RSI = 0"""

    df = pd.DataFrame({"close": list(range(20, 0, -1))})

    result = add_rsi(df, period=14)

    assert result["rsi_14"].iloc[-1] == pytest.approx(0.0)


def test_add_rsi_flat_is_50():
    """无波动 → RSI = 50"""

    df = pd.DataFrame({"close": [5.0] * 20})

    result = add_rsi(df, period=14)

    assert result["rsi_14"].iloc[-1] == pytest.approx(50.0)


def test_add_rsi_bounded():
    """正常序列 RSI 落在 [0, 100]"""

    df = make_bars(n=40, seed=7)

    result = add_rsi(df, period=14)

    rsi = result["rsi_14"].dropna()

    assert rsi.between(0.0, 100.0).all()


def test_add_kdj_constant_price():
    """价格恒定 → RSV=50 → K/D/J 收敛到 50"""

    df = pd.DataFrame(
        {
            "high": [10.0] * 10,
            "low": [10.0] * 10,
            "close": [10.0] * 10,
        }
    )

    result = add_kdj(df)

    assert result["kdj_j"].iloc[-1] == pytest.approx(50.0, abs=1e-6)
    assert result["kdj_k"].iloc[-1] == pytest.approx(50.0, abs=1e-6)
    assert result["kdj_d"].iloc[-1] == pytest.approx(50.0, abs=1e-6)


def test_add_kdj_range():
    """KDJ 与 RSV 联动：收盘贴近窗口高点 → K 偏大"""

    df = pd.DataFrame(
        {
            "high": [10.0, 10.0, 10.0],
            "low": [8.0, 8.0, 8.0],
            "close": [9.0, 9.9, 9.9],
        }
    )

    result = add_kdj(df)

    assert result["kdj_k"].iloc[-1] > 50.0


def test_add_boll_symmetric_bands():
    """布林带以 MID 对称：UPPER - MID == MID - LOWER"""

    df = make_bars(n=30)

    result = add_boll(df, window=20)

    mid_rows = result.dropna(subset=["boll_mid"])

    assert np.allclose(
        mid_rows["boll_upper"] - mid_rows["boll_mid"],
        mid_rows["boll_mid"] - mid_rows["boll_lower"],
    )


def test_add_boll_constant_series():
    """恒定序列 → 上下轨 == MID（std=0）"""

    df = pd.DataFrame({"close": [3.0] * 25})

    result = add_boll(df, window=20)

    tail = result.dropna(subset=["boll_mid"])

    assert np.allclose(tail["boll_upper"], tail["boll_mid"])
    assert np.allclose(tail["boll_lower"], tail["boll_mid"])


def test_add_atr_nonnegative():
    """TR / ATR 恒 >= 0"""

    df = make_bars(n=30, seed=3)

    result = add_atr(df, period=14)

    assert (result["atr_14"].dropna() >= 0.0).all()


def test_add_atr_manual():
    """ATR(2) 手算验证：TR 序列 Wilder 平滑"""

    df = pd.DataFrame(
        {
            "high": [11.0, 12.0, 13.0],
            "low": [9.0, 8.0, 10.0],
            "close": [10.0, 12.0, 11.0],
        }
    )

    result = add_atr(df, period=2)

    # TR: day0 = 11-9 = 2；day1 = max(12-8, |12-10|, |8-10|) = 4；
    # day2 = max(13-10, |13-12|, |10-12|) = 3
    # ATR(2) Wilder: day0 = 2；day1 = (2*1 + 4)/2 = 3；day2 = (3*1 + 3)/2 = 3
    assert result["atr_2"].iloc[0] == pytest.approx(2.0)
    assert result["atr_2"].iloc[1] == pytest.approx(3.0)
    assert result["atr_2"].iloc[2] == pytest.approx(3.0)


def test_add_all_indicators_columns():
    df = make_bars(n=70)

    result = add_all_indicators(df)

    expected_columns = {
        "ma_5", "ma_10", "ma_20", "ma_60",
        "ema_12", "ema_26",
        "dif", "dea", "macd",
        "rsi_14",
        "kdj_k", "kdj_d", "kdj_j",
        "boll_mid", "boll_upper", "boll_lower",
        "atr_14",
    }

    assert expected_columns.issubset(set(result.columns))


def test_add_all_indicators_empty():
    result = add_all_indicators(pd.DataFrame())

    assert result.empty
