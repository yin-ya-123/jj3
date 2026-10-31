"""技术分析页面（阶段 4.6）

展示：综合评分、趋势判断、支撑压力、量价、指标明细、信号依据；
提供结构化技术分析报告下载（Markdown）。
页面只读，不写库。
"""

import pandas as pd
import streamlit as st

from data.analysis import (
    add_volume_analysis,
    analyze_trend,
    find_support_resistance,
    volume_price_status,
)
from data.indicators import add_all_indicators
from data.report import build_technical_report
from data.scoring import score_technical
from database.repositories.adjust_factor_repository import get_adjust_factor_frame
from database.repositories.daily_bar_repository import get_daily_bars
from database.repositories.stock_repository import list_stocks

from data.adjustment import apply_adjust
from ui.glossary import render_indicator_glossary

REPORT_LOOKBACK = 120
EXTRA_BARS = 80

SIGNAL_COLORS = {
    "看多": "#e63946",
    "中性": "#6c757d",
    "看空": "#2a9d8f",
    "数据不足": "#6c757d",
}

RISK_COLORS = {
    "低": "#2a9d8f",
    "中": "#f4a261",
    "高": "#e63946",
    "数据不足": "#6c757d",
}


def _load_active_stocks() -> list[dict]:
    return list_stocks(only_active=True)


def _label_map(rows: list[dict]) -> dict[str, str]:
    return {r["code"]: f'{r["code"]} {r["name"] or ""}' for r in rows}


def _rows_to_frame(rows) -> pd.DataFrame:
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


def _load_analysis_frame(code: str, limit: int = REPORT_LOOKBACK) -> pd.DataFrame:
    """加载日线（前复权）+ 指标 + 量价列，按日期升序"""

    rows = get_daily_bars(code, limit=limit + EXTRA_BARS, adjustflag="3")

    if not rows:
        return pd.DataFrame()

    df = _rows_to_frame(rows).sort_values("date").reset_index(drop=True)
    factors = get_adjust_factor_frame(code)
    adjusted = apply_adjust(df, factors, mode="qfq")
    adjusted = add_all_indicators(adjusted)
    adjusted = add_volume_analysis(adjusted)
    return adjusted


def _impact_mark(impact: str) -> str:
    mapping = {
        "positive": "利多",
        "negative": "利空",
        "neutral": "中性",
    }
    return mapping.get(impact, impact)


def _render_metrics(latest, vp) -> None:
    columns = st.columns(5)

    columns[0].metric("最新收盘", f"{latest['close']:.2f}", "元")

    pct = latest.get("pct_chg")

    if not pd.isna(pct):
        columns[1].metric("涨跌幅", f"{pct:+.2f}%", "当日")
    else:
        columns[1].metric("涨跌幅", "-", "当日")

    ratio = vp.get("volume_ratio")

    if ratio is not None:
        columns[2].metric("量比", f"{ratio:.2f}", vp.get("status", ""))
    else:
        columns[2].metric("量比", "-", vp.get("status", ""))

    turn = latest.get("turn")

    if not pd.isna(turn):
        columns[3].metric("换手率", f"{turn:.2f}%", "当日")
    else:
        columns[3].metric("换手率", "-", "当日")

    close = latest.get("close")
    ma20 = latest.get("ma_20")

    if not pd.isna(close) and not pd.isna(ma20):
        diff = (close - ma20) / ma20 * 100.0
        columns[4].metric("较 MA20", f"{diff:+.2f}%", "偏离")
    else:
        columns[4].metric("较 MA20", "-", "偏离")


def _render_score(score: dict) -> None:
    st.subheader("综合评分")

    left, mid, right = st.columns([2, 1, 1])

    with left:
        st.progress(min(score.get("score", 0) / 100.0, 1.0), text=f"综合得分 {score.get('score')}/100")

    with mid:
        signal = score.get("signal", "数据不足")
        st.markdown(
            f"<div style='font-size:1.1rem;color:{SIGNAL_COLORS.get(signal, '#6c757d')};'>"
            f"信号：<b>{signal}</b></div>",
            unsafe_allow_html=True,
        )

    with right:
        risk = score.get("risk_level", "数据不足")
        st.markdown(
            f"<div style='font-size:1.1rem;color:{RISK_COLORS.get(risk, '#6c757d')};'>"
            f"风险等级：<b>{risk}</b></div>",
            unsafe_allow_html=True,
        )

    st.caption(score.get("note", ""))

    if score.get("items"):
        st.markdown(
            "| 信号项 | 方向 | 依据 |\n|---|---|---|\n"
            + "\n".join(
                f"| {item.get('name', '-')} | {_impact_mark(item.get('impact', 'neutral'))} | "
                f"{item.get('detail', '')} |"
                for item in score["items"]
            ),
            unsafe_allow_html=True,
        )


def _render_trend(trend: dict) -> None:
    st.subheader("趋势判断")

    columns = st.columns(5)
    columns[0].metric("趋势", trend.get("trend", "-"))
    columns[1].metric("均线排列", trend.get("alignment", "-"))
    columns[2].metric("MA20 方向", trend.get("ma20_direction", "-"))

    vs20 = trend.get("price_vs_ma20")
    columns[3].metric("较 MA20", f"{vs20:+.2f}%" if vs20 is not None else "-")

    recent = trend.get("recent_percent")
    columns[4].metric("近 20 日", f"{recent:+.2f}%" if recent is not None else "-")


def _render_sr(sr: dict) -> None:
    st.subheader("支撑位与压力位")

    if not sr.get("supports") and not sr.get("resistances"):
        st.info("数据不足，未识别出支撑/压力位。")
        return

    left, right = st.columns(2)

    with left:
        st.markdown("**支撑位**")

        if sr.get("supports"):
            st.dataframe(
                pd.DataFrame(sr["supports"])[["price", "type", "detail"]],
                use_container_width=True,
                hide_index=True,
                column_config={"price": st.column_config.NumberColumn("价格", format="%.2f")},
            )
        else:
            st.caption("无")

    with right:
        st.markdown("**压力位**")

        if sr.get("resistances"):
            st.dataframe(
                pd.DataFrame(sr["resistances"])[["price", "type", "detail"]],
                use_container_width=True,
                hide_index=True,
                column_config={"price": st.column_config.NumberColumn("价格", format="%.2f")},
            )
        else:
            st.caption("无")


def _render_indicator_table(df: pd.DataFrame) -> None:
    st.subheader("指标明细")

    latest = df.iloc[-1]

    columns = st.columns(4)

    definitions = [
        ("收盘价", "close", ".2f"),
        ("MA20", "ma_20", ".2f"),
        ("MA60", "ma_60", ".2f"),
        ("DIF / DEA", "dif", ".3f"),
        ("RSI(14)", "rsi_14", ".2f"),
        ("KDJ K/D/J", "kdj_k", ".2f"),
        ("BOLL 上/下", "boll_upper", ".2f"),
        ("ATR(14)", "atr_14", ".3f"),
    ]

    for i, (label, column, fmt) in enumerate(definitions):
        value = latest.get(column)

        if pd.isna(value):
            columns[i % 4].metric(label, "-")
        else:
            columns[i % 4].metric(label, f"{value:{fmt}}")

    vp = volume_price_status(df)
    st.caption(f"量价配合：{vp.get('status', '')}　|　{vp.get('detail', '')}")


def render_technical_analysis() -> None:
    st.title("📊 技术分析")

    rows = _load_active_stocks()

    if not rows:
        st.info("自选池为空，请先在「📋 股票管理」中添加股票。")
        return

    label_map = _label_map(rows)
    codes = list(label_map.keys())

    selected = st.selectbox(
        "选择股票",
        options=codes,
        format_func=lambda code: label_map.get(code, code),
        key="ta_stock",
    )

    df = _load_analysis_frame(selected)

    if df.empty:
        st.warning(f"{selected} 暂无日线数据，请先在「🔄 数据同步」中同步行情。")
        return

    latest = df.iloc[-1]
    vp = volume_price_status(df)

    st.caption(
        f"{label_map.get(selected, selected)}　|　数据截至 {df['date'].iloc[-1].date()}　|　"
        f"前复权口径（库存不复权，计算层换算）"
    )

    _render_metrics(latest, vp)

    trend = analyze_trend(df)
    sr = find_support_resistance(df, lookback=REPORT_LOOKBACK)
    score = score_technical(df)

    st.divider()
    _render_trend(trend)
    st.divider()
    _render_score(score)
    st.divider()
    _render_sr(sr)
    st.divider()
    _render_indicator_table(df)

    st.divider()
    st.subheader("技术分析报告")

    report = build_technical_report(
        {"code": selected, "name": label_map.get(selected, "")},
        df,
        trend,
        sr,
        score,
    )

    st.download_button(
        "下载技术分析报告（Markdown）",
        data=report.encode("utf-8"),
        file_name=f"技术分析报告_{selected}.md",
        mime="text/markdown",
        use_container_width=False,
    )

    with st.expander("预览报告全文"):
        st.markdown(report)

    st.divider()
    render_indicator_glossary()
