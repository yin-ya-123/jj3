"""技术指标计算层（阶段 4.1，纯 pandas 自实现）

输入：日线 DataFrame（含 date / open / high / low / close 等列，
      可由 daily_bar_repository.get_daily_bars + adjustment.apply_adjust 构造）。
输出：追加指标列后的 DataFrame 副本（不修改入参）。

约定：
- 全部纯 pandas / numpy 实现，不引入 ta-lib 等重型依赖。
- 各指标独立函数、参数可配；数据不足时对应位置为 NaN，不报错。
- 停牌日（NaN 价格）会被 rolling / ewm 自然跳过。
"""

import numpy as np
import pandas as pd

PRICE_COLUMNS = ("open", "high", "low", "close", "preclose")


def _numeric(df: pd.DataFrame) -> pd.DataFrame:
    """把价格列统一转为 float，非法值置 NaN"""

    result = df.copy()

    for column in PRICE_COLUMNS:
        if column in result.columns:
            result[column] = pd.to_numeric(
                result[column], errors="coerce"
            )

    return result


def _has_columns(frame: pd.DataFrame, columns) -> bool:
    """检查必需的行情列是否齐全，缺列时直接返回 False"""

    return all(column in frame.columns for column in columns)


def add_ma(df: pd.DataFrame, window: int = 5) -> pd.DataFrame:
    """简单移动平均 MA

    列名：ma_{window}
    """

    frame = _numeric(df)

    if not _has_columns(frame, ("close",)):
        return frame

    frame[f"ma_{window}"] = (
        frame["close"].rolling(window=window, min_periods=window).mean()
    )
    return frame


def add_ema(df: pd.DataFrame, span: int = 12) -> pd.DataFrame:
    """指数移动平均 EMA（adjust=False，从第一根 K 线起算）

    列名：ema_{span}
    """

    frame = _numeric(df)

    if not _has_columns(frame, ("close",)):
        return frame

    frame[f"ema_{span}"] = (
        frame["close"].ewm(span=span, adjust=False).mean()
    )
    return frame


def add_macd(
    df: pd.DataFrame,
    fast: int = 12,
    slow: int = 26,
    signal: int = 9,
) -> pd.DataFrame:
    """MACD：DIF / DEA / MACD 柱

    - DIF = EMA(fast) - EMA(slow)
    - DEA = EMA(signal, DIF)
    - MACD 柱 = 2 * (DIF - DEA)   （国内软件通用口径）

    列名：dif / dea / macd
    """

    frame = _numeric(df)

    if not _has_columns(frame, ("close",)):
        return frame

    close = frame["close"]

    ema_fast = close.ewm(span=fast, adjust=False).mean()
    ema_slow = close.ewm(span=slow, adjust=False).mean()
    dif = ema_fast - ema_slow
    dea = dif.ewm(span=signal, adjust=False).mean()

    frame["dif"] = dif
    frame["dea"] = dea
    frame["macd"] = 2.0 * (dif - dea)
    return frame


def add_rsi(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """相对强弱指标 RSI（Wilder 平滑）

    - 涨跌幅差后按 alpha=1/period 递推平滑（等价 Wilder 平均）
    - 全上涨（avg_loss=0）→ RSI=100；无波动 → 50

    列名：rsi_{period}
    """

    frame = _numeric(df)
    close = frame["close"]

    delta = close.diff()
    gain = delta.clip(lower=0.0)
    loss = (-delta).clip(lower=0.0)

    avg_gain = gain.ewm(alpha=1.0 / period, adjust=False).mean()
    avg_loss = loss.ewm(alpha=1.0 / period, adjust=False).mean()

    rsi = 50.0
    rsi = pd.Series(50.0, index=frame.index, dtype="float64")

    rs = avg_gain / avg_loss.replace(0.0, np.nan)
    computed = 100.0 - 100.0 / (1.0 + rs)

    # avg_loss == 0 且 avg_gain > 0 → 100；avg_loss == 0 且 avg_gain == 0 → 50
    all_up = (avg_loss == 0.0) & (avg_gain > 0.0)
    flat = (avg_loss == 0.0) & (avg_gain == 0.0)

    rsi = rsi.where(flat, computed.where(~all_up, 100.0))

    frame[f"rsi_{period}"] = rsi
    return frame


def add_kdj(
    df: pd.DataFrame,
    n: int = 9,
    k_period: int = 3,
    d_period: int = 3,
) -> pd.DataFrame:
    """随机指标 KDJ

    - RSV = (close - lowN) / (highN - lowN) * 100，高低相等时取 50
    - K = SMA(RSV, k_period, 1)，D = SMA(K, d_period, 1)，J = 3K - 2D
      （SMA(X, N, 1) 等价 ewm(alpha=1/N, adjust=False)）

    列名：kdj_k / kdj_d / kdj_j
    """

    frame = _numeric(df)

    low_n = frame["low"].rolling(window=n, min_periods=1).min()
    high_n = frame["high"].rolling(window=n, min_periods=1).max()
    span = (high_n - low_n).replace(0.0, np.nan)

    rsv = (frame["close"] - low_n) / span * 100.0
    rsv = rsv.fillna(50.0)

    k = rsv.ewm(alpha=1.0 / k_period, adjust=False).mean()
    d = k.ewm(alpha=1.0 / d_period, adjust=False).mean()

    frame["kdj_k"] = k
    frame["kdj_d"] = d
    frame["kdj_j"] = 3.0 * k - 2.0 * d
    return frame


def add_boll(
    df: pd.DataFrame,
    window: int = 20,
    num_std: float = 2.0,
) -> pd.DataFrame:
    """布林带 BOLL（总体标准差 ddof=0）

    列名：boll_mid / boll_upper / boll_lower
    """

    frame = _numeric(df)

    if not _has_columns(frame, ("close",)):
        return frame

    close = frame["close"]

    mid = close.rolling(window=window, min_periods=window).mean()
    std = close.rolling(window=window, min_periods=window).std(ddof=0)

    frame["boll_mid"] = mid
    frame["boll_upper"] = mid + num_std * std
    frame["boll_lower"] = mid - num_std * std
    return frame


def add_atr(df: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """平均真实波幅 ATR（Wilder 平滑）

    TR = max(high - low, |high - prev_close|, |low - prev_close|)

    列名：atr_{period}
    """

    frame = _numeric(df)

    if not _has_columns(frame, ("close", "high", "low")):
        return frame

    prev_close = frame["close"].shift(1)
    high_low = frame["high"] - frame["low"]
    high_pc = (frame["high"] - prev_close).abs()
    low_pc = (frame["low"] - prev_close).abs()

    tr = pd.concat([high_low, high_pc, low_pc], axis=1).max(axis=1)
    atr = tr.ewm(alpha=1.0 / period, adjust=False).mean()

    frame[f"atr_{period}"] = atr
    return frame


def add_all_indicators(
    df: pd.DataFrame,
    ma_windows=(5, 10, 20, 60),
    ema_spans=(12, 26),
    rsi_periods=(14,),
    atr_periods=(14,),
) -> pd.DataFrame:
    """一次性计算常用指标（默认参数）

    依次叠加：MA(5/10/20/60)、EMA(12/26)、MACD(12/26/9)、
    RSI(14)、KDJ(9,3,3)、BOLL(20,2)、ATR(14)。
    """

    frame = _numeric(df)

    if frame.empty or not _has_columns(frame, ("close", "high", "low")):
        return frame

    for window in ma_windows:
        frame = add_ma(frame, window=window)

    for span in ema_spans:
        frame = add_ema(frame, span=span)

    frame = add_macd(frame)
    frame = add_rsi(frame, period=rsi_periods[0])
    frame = add_kdj(frame)
    frame = add_boll(frame)
    frame = add_atr(frame, period=atr_periods[0])
    return frame
