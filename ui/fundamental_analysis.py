"""基本面分析页面（阶段 5.6）

展示：核心财务指标、基本面综合评分、估值指标、多期趋势表；
提供结构化基本面分析报告下载（Markdown）。
页面只读，不写库。
"""

import pandas as pd
import streamlit as st

from data.financial_trend import financial_report_markdown, trend_summary, trend_table
from data.fundamental_score import fundamental_score
from data.fundamentals import reports_to_frame
from data.valuation import compute_valuation, get_latest_close
from database.repositories.financial_report_repository import get_financial_reports
from database.repositories.stock_repository import list_stocks

GRADE_COLORS = {
    "优秀": "#2a9d8f",
    "良好": "#2a9d8f",
    "一般": "#f4a261",
    "偏弱": "#e63946",
    "差": "#e63946",
}

RISK_COLORS = {
    "低风险": "#2a9d8f",
    "中低风险": "#2a9d8f",
    "中风险": "#f4a261",
    "中高风险": "#e63946",
    "高风险": "#e63946",
    "数据不足": "#6c757d",
}


def _load_active_stocks() -> list[dict]:
    return list_stocks(only_active=True)


def _label_map(rows: list[dict]) -> dict[str, str]:
    return {r["code"]: f'{r["code"]} {r["name"] or ""}' for r in rows}


def _load_fundamental_frame(code: str) -> pd.DataFrame:
    """加载财报宽表（按披露日期排序）"""

    records = get_financial_reports(code)

    if not records:
        return pd.DataFrame()

    frame = reports_to_frame(records)
    if "report_date" in frame.columns:
        frame = frame.sort_values("report_date").reset_index(drop=True)
    return frame


def _render_metrics(summary: dict) -> None:
    st.subheader("核心财务指标")

    columns = st.columns(5)

    columns[0].metric(
        "营业收入",
        f"{summary['revenue'] / 1e8:.2f} 亿" if summary["revenue"] is not None else "-",
        f"同比 {summary['revenue_yoy']:+.2f}%" if summary["revenue_yoy"] is not None else "-",
    )
    columns[1].metric(
        "净利润",
        f"{summary['net_profit'] / 1e8:.2f} 亿" if summary["net_profit"] is not None else "-",
        f"同比 {summary['net_profit_yoy']:+.2f}%" if summary["net_profit_yoy"] is not None else "-",
    )
    columns[2].metric(
        "毛利率",
        f"{summary['gross_margin']:.2f}%" if summary["gross_margin"] is not None else "-",
        f"净利率 {summary['net_margin']:.2f}%" if summary["net_margin"] is not None else "-",
    )
    columns[3].metric(
        "ROE",
        f"{summary['roe']:.2f}%" if summary["roe"] is not None else "-",
        "加权净资产收益率",
    )
    columns[4].metric(
        "资产负债率",
        f"{summary['debt_ratio']:.2f}%" if summary["debt_ratio"] is not None else "-",
        f"经营现金流 {summary['netcash_operate'] / 1e8:.2f} 亿"
        if summary["netcash_operate"] is not None
        else "-",
    )

    st.caption(
        f"连续营收同比增长 {summary['revenue_growth_periods']} 期　|　"
        f"连续净利润同比增长 {summary['profit_growth_periods']} 期"
    )


def _render_score(score: dict) -> None:
    st.subheader("基本面评分")

    if not score.get("data_sufficient"):
        st.info("核心财报数据不足，无法给出基本面评分。")
        return

    left, mid, right = st.columns([2, 1, 1])

    with left:
        st.progress(min(score.get("score", 0) / 100.0, 1.0), text=f"基本面得分 {score.get('score')}/100")

    with mid:
        grade = score.get("grade", "-")
        st.markdown(
            f"<div style='font-size:1.1rem;color:{GRADE_COLORS.get(grade, '#6c757d')};'>"
            f"评级：<b>{grade}</b></div>",
            unsafe_allow_html=True,
        )

    with right:
        risk = score.get("risk_level", "数据不足")
        st.markdown(
            f"<div style='font-size:1.1rem;color:{RISK_COLORS.get(risk, '#6c757d')};'>"
            f"风险等级：<b>{risk}</b></div>",
            unsafe_allow_html=True,
        )

    if score.get("items"):
        st.markdown(
            "| 评分项 | 得分 | 依据 |\n|---|---|---|\n"
            + "\n".join(
                f"| {item.get('name', '-')} | {item.get('score', 0):+d} | "
                f"{item.get('detail', '')} |"
                for item in score["items"]
            ),
            unsafe_allow_html=True,
        )


def _render_valuation(valuation: dict) -> None:
    st.subheader("估值")

    columns = st.columns(4)
    columns[0].metric("收盘价", f"{valuation.get('close'):.2f}" if valuation.get("close") else "-")
    columns[1].metric("静态 PE", f"{valuation.get('pe'):.2f}" if valuation.get("pe") else "-")
    columns[2].metric("PE_TTM", f"{valuation.get('pe_ttm'):.2f}" if valuation.get("pe_ttm") else "-")
    columns[3].metric("PB", f"{valuation.get('pb'):.2f}" if valuation.get("pb") else "-")

    if valuation.get("report_date"):
        st.caption(f"估值基于最新财报期 {valuation['report_date']} 与最新收盘价计算")


def _render_trend(frame: pd.DataFrame) -> None:
    st.subheader("多期财务趋势")
    st.markdown(trend_table(frame))


def build_fundamental_report_markdown(
    symbol: str,
    name: str,
    frame: pd.DataFrame,
    valuation: dict | None = None,
) -> str:
    """组装完整基本面分析报告（含综合评分段落）"""

    summary = trend_summary(frame)
    score = fundamental_score(summary, valuation)

    base = financial_report_markdown(symbol, frame, valuation)

    lines = [base]

    if score.get("data_sufficient"):
        lines.append("")
        lines.append("## 基本面综合评分")
        lines.append("")
        lines.append(f"- 综合得分：{score['score']} / 100")
        lines.append(f"- 评级：{score['grade']}")
        lines.append(f"- 风险等级：{score['risk_level']}")
        lines.append("")
        lines.append("| 评分项 | 得分 | 依据 |")
        lines.append("|---|---|---|")
        for item in score["items"]:
            lines.append(
                f"| {item['name']} | {item['score']:+d} | {item['detail']} |"
            )
    else:
        lines.append("")
        lines.append("## 基本面综合评分")
        lines.append("")
        lines.append("（核心财报数据不足，未给出评分）")

    return "\n".join(lines)


def render_fundamental_analysis() -> None:
    st.title("📊 基本面分析")

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
        key="fa_stock",
    )

    frame = _load_fundamental_frame(selected)

    if frame.empty:
        st.warning(f"{selected} 暂无财报数据，请先在「🔄 数据同步」中同步财务报表。")
        return

    summary = trend_summary(frame)

    st.caption(
        f"{label_map.get(selected, selected)}　|　最新报告期 {summary['report_date'] or '-'}　|　"
        f"披露日期 {summary['announce_date'] or '-'}　|　共 {summary['periods']} 期"
    )

    close = get_latest_close(selected)
    valuation = compute_valuation(frame, close)

    _render_metrics(summary)
    st.divider()
    _render_score(fundamental_score(summary, valuation))
    st.divider()
    _render_valuation(valuation)
    st.divider()
    _render_trend(frame)

    st.divider()
    st.subheader("基本面分析报告")

    report = build_fundamental_report_markdown(
        selected,
        label_map.get(selected, ""),
        frame,
        valuation,
    )

    st.download_button(
        "下载基本面分析报告（Markdown）",
        data=report.encode("utf-8"),
        file_name=f"基本面分析报告_{selected}.md",
        mime="text/markdown",
    )
