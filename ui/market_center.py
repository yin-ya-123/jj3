"""行情中心页面（阶段 4.5）

K 线图 + 均线 / BOLL / 成交量 / MACD 叠加，支持前复权展示。
页面只读展示，不写库；数据复用 daily_bar_repository + adjustment + indicators/analysis。
"""

import pandas as pd
import plotly.graph_objects as go
import streamlit as st
from plotly.subplots import make_subplots

from data.adjustment import apply_adjust
from data.analysis import add_volume_analysis, volume_price_status
from data.indicators import add_all_indicators
from database.repositories.adjust_factor_repository import get_adjust_factor_frame
from database.repositories.daily_bar_repository import get_daily_bars
from database.repositories.stock_repository import list_stocks

# A 股惯例：红涨绿跌
COLOR_UP = "#e63946"
COLOR_DOWN = "#2a9d8f"

ADJUST_OPTIONS = {
    "前复权": "qfq",
    "不复权": "none",
}

K_LIMIT_OPTIONS = (60, 120, 250)
# 多取 80 根前置数据，保证 MA60 / BOLL 等指标在前段有值
EXTRA_BARS = 80


def _load_active_stocks() -> list[dict]:
    return list_stocks(only_active=True)


def _label_map(rows: list[dict]) -> dict[str, str]:
    return {r["code"]: f'{r["code"]} {r["name"] or ""}' for r in rows}


def _rows_to_frame(rows) -> pd.DataFrame:
    """ORM 行列表 → 日线 DataFrame（trade_date 归一为 date）"""

    if not rows:
        return pd.DataFrame()

    return pd.DataFrame(
        [
            {
                "date": pd.to_datetime(row.trade_date),
                "open": row.open,
                "high": row.high,
                "low": row.low,
                "close": row.close,
                "preclose": row.preclose,
                "volume": row.volume,
                "amount": row.amount,
                "turn": row.turn,
                "pct_chg": row.pct_chg,
                "trade_status": row.trade_status,
            }
            for row in rows
        ]
    )


def _build_indicators_frame(code: str, limit: int, mode: str) -> pd.DataFrame:
    """加载日线 + 复权 + 指标列，返回按日期升序的 DataFrame"""

    rows = get_daily_bars(code, limit=limit + EXTRA_BARS, adjustflag="3")

    if not rows:
        return pd.DataFrame()

    df = _rows_to_frame(rows).sort_values("date").reset_index(drop=True)

    factors = get_adjust_factor_frame(code)
    adjusted = apply_adjust(df, factors, mode=mode)

    adjusted = add_all_indicators(adjusted)
    adjusted = add_volume_analysis(adjusted)
    return adjusted


def _candle_figure(df: pd.DataFrame) -> go.Figure:
    """K 线主图 + 成交量 + MACD 副图"""

    figure = make_subplots(
        rows=3,
        cols=1,
        shared_xaxes=True,
        vertical_spacing=0.03,
        row_heights=[0.62, 0.18, 0.20],
        subplot_titles=("K 线与均线/BOLL", "成交量", "MACD"),
    )

    dates = df["date"]

    figure.add_trace(
        go.Candlestick(
            x=dates,
            open=df["open"],
            high=df["high"],
            low=df["low"],
            close=df["close"],
            name="K 线",
            increasing_line_color=COLOR_UP,
            decreasing_line_color=COLOR_DOWN,
            increasing_fillcolor=COLOR_UP,
            decreasing_fillcolor=COLOR_DOWN,
        ),
        row=1,
        col=1,
    )

    for window in (5, 10, 20, 60):
        column = f"ma_{window}"

        if column in df.columns:
            figure.add_trace(
                go.Scatter(
                    x=dates,
                    y=df[column],
                    mode="lines",
                    name=f"MA{window}",
                    line={"width": 1.1},
                ),
                row=1,
                col=1,
            )

    for column, name, dash in (
        ("boll_upper", "BOLL 上轨", "dash"),
        ("boll_lower", "BOLL 下轨", "dash"),
    ):
        if column in df.columns:
            figure.add_trace(
                go.Scatter(
                    x=dates,
                    y=df[column],
                    mode="lines",
                    name=name,
                    line={"width": 1.0, "dash": dash, "color": "#9b59b6"},
                ),
                row=1,
                col=1,
            )

    # 成交量：红涨绿跌
    direction = df["close"] >= df["open"].fillna(df["close"])
    volume_colors = [COLOR_UP if flag else COLOR_DOWN for flag in direction]

    figure.add_trace(
        go.Bar(x=dates, y=df["volume"], name="成交量", marker_color=volume_colors),
        row=2,
        col=1,
    )

    if "ma_vol_5" in df.columns:
        figure.add_trace(
            go.Scatter(
                x=dates,
                y=df["ma_vol_5"],
                mode="lines",
                name="均量 5",
                line={"width": 1.0},
            ),
            row=2,
            col=1,
        )

    # MACD 副图
    if "dif" in df.columns:
        macd_colors = [
            COLOR_UP if value >= 0 else COLOR_DOWN
            for value in df["macd"].fillna(0.0)
        ]
        figure.add_trace(
            go.Bar(x=dates, y=df["macd"], name="MACD 柱", marker_color=macd_colors),
            row=3,
            col=1,
        )
        figure.add_trace(
            go.Scatter(x=dates, y=df["dif"], mode="lines", name="DIF", line={"width": 1.0}),
            row=3,
            col=1,
        )
        figure.add_trace(
            go.Scatter(x=dates, y=df["dea"], mode="lines", name="DEA", line={"width": 1.0}),
            row=3,
            col=1,
        )

    figure.update_layout(
        height=680,
        margin={"l": 10, "r": 10, "t": 40, "b": 10},
        xaxis_rangeslider_visible=False,
        legend={"orientation": "h", "yanchor": "bottom", "y": 1.02},
        hovermode="x unified",
    )

    figure.update_xaxes(type="date")
    return figure


def render_market_center() -> None:
    st.title("📊 行情中心")

    rows = _load_active_stocks()

    if not rows:
        st.info("自选池为空，请先在「📋 股票管理」中添加股票。")
        return

    label_map = _label_map(rows)
    codes = list(label_map.keys())

    left, mid, right = st.columns([3, 1, 1])

    with left:
        selected = st.selectbox(
            "选择股票",
            options=codes,
            format_func=lambda code: label_map.get(code, code),
            key="mc_stock",
        )

    with mid:
        adjust_label = st.selectbox(
            "复权方式",
            options=list(ADJUST_OPTIONS.keys()),
            index=0,
            key="mc_adjust",
        )

    with right:
        limit = st.selectbox(
            "显示 K 线数量",
            options=K_LIMIT_OPTIONS,
            index=1,
            key="mc_limit",
        )

    mode = ADJUST_OPTIONS[adjust_label]
    df = _build_indicators_frame(selected, limit=limit, mode=mode)

    if df.empty:
        st.warning(f"{selected} 暂无日线数据，请先在「🔄 数据同步」中同步行情。")
        return

    st.caption(
        f"{label_map.get(selected, selected)}　|　{df['date'].iloc[-1].date()}　|　"
        f"{adjust_label}（库存不复权，计算层换算）"
    )

    figure = _candle_figure(df)
    st.plotly_chart(figure, use_container_width=True)

    latest = df.iloc[-1]
    vp = volume_price_status(df)

    metrics = [
        ("最新收盘", f"{latest['close']:.2f}", "元"),
        ("涨跌幅", f"{latest.get('pct_chg', float('nan')):+.2f}%" if not pd.isna(latest.get("pct_chg")) else "-", "当日"),
        ("量比", f"{vp.get('volume_ratio', '-')}" if vp.get("volume_ratio") is not None else "-", vp.get("status", "")),
        ("换手率", f"{latest.get('turn', float('nan')):.2f}%" if not pd.isna(latest.get("turn")) else "-", "当日"),
    ]

    columns = st.columns(len(metrics))

    for column, (label, value, suffix) in zip(columns, metrics):
        column.metric(label, value, suffix)

    latest_frame = df.tail(10).iloc[::-1][
        ["date", "close", "pct_chg", "volume_ratio", "turn", "ma_20", "dif", "dea", "rsi_14"]
    ]

    st.subheader("最新指标明细")
    st.dataframe(
        latest_frame,
        use_container_width=True,
        hide_index=True,
        column_config={
            "date": st.column_config.TextColumn("日期"),
            "close": st.column_config.NumberColumn("收盘价", format="%.2f"),
            "pct_chg": st.column_config.NumberColumn("涨跌幅%", format="%.2f"),
            "volume_ratio": st.column_config.NumberColumn("量比", format="%.2f"),
            "turn": st.column_config.NumberColumn("换手率%", format="%.2f"),
            "ma_20": st.column_config.NumberColumn("MA20", format="%.2f"),
            "dif": st.column_config.NumberColumn("DIF", format="%.3f"),
            "dea": st.column_config.NumberColumn("DEA", format="%.3f"),
            "rsi_14": st.column_config.NumberColumn("RSI14", format="%.2f"),
        },
    )
