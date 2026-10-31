"""技术分析报告生成（阶段 4.6）

把行情最新值、量价、趋势、支撑压力、综合评分组装为结构化 Markdown 报告。

不依赖 Streamlit，纯函数可离线测试；页面负责传参与下载。
"""

from datetime import datetime

import pandas as pd


def _fmt_price(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}"


def _fmt_pct(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):+.2f}%"


def _latest_value(df: pd.DataFrame, column: str):
    if column not in df.columns:
        return None
    value = df[column].iloc[-1]
    if pd.isna(value):
        return None
    return float(value)


def _indicator_table(df: pd.DataFrame) -> str:
    """指标明细表格（Markdown）"""

    rows = []

    def add(label, value, unit=""):
        if value is not None:
            rows.append((label, f"{value:.2f}{unit}" if isinstance(value, float) else str(value)))

    add("收盘价", _latest_value(df, "close"))
    add("涨跌幅", _latest_value(df, "pct_chg"), "%")

    for window in (5, 10, 20, 60):
        add(f"MA{window}", _latest_value(df, f"ma_{window}"))

    add("EMA12", _latest_value(df, "ema_12"))
    add("EMA26", _latest_value(df, "ema_26"))
    add("DIF", _latest_value(df, "dif"))
    add("DEA", _latest_value(df, "dea"))
    add("MACD 柱", _latest_value(df, "macd"))
    add("RSI(14)", _latest_value(df, "rsi_14"))
    add("KDJ-K", _latest_value(df, "kdj_k"))
    add("KDJ-D", _latest_value(df, "kdj_d"))
    add("KDJ-J", _latest_value(df, "kdj_j"))
    add("BOLL 中轨", _latest_value(df, "boll_mid"))
    add("BOLL 上轨", _latest_value(df, "boll_upper"))
    add("BOLL 下轨", _latest_value(df, "boll_lower"))
    add("ATR(14)", _latest_value(df, "atr_14"))
    add("成交量", _latest_value(df, "volume"))
    add("量比", _latest_value(df, "volume_ratio"))
    add("换手率", _latest_value(df, "turn"), "%")

    lines = ["| 指标 | 数值 |", "|---|---|"]

    for label, value in rows:
        lines.append(f"| {label} | {value} |")

    return "\n".join(lines)


def _signal_impact_mark(impact: str) -> str:
    mapping = {
        "positive": "利多",
        "negative": "利空",
        "neutral": "中性",
    }
    return mapping.get(impact, impact)


def build_technical_report(
    stock: dict,
    df: pd.DataFrame,
    trend: dict,
    sr: dict,
    score: dict,
) -> str:
    """组装技术分析报告

    参数：
    - stock：{code, name} 股票信息
    - df：已含指标列与量价列的日线 DataFrame（最新一根为报告基准）
    - trend：analyze_trend 返回值
    - sr：find_support_resistance 返回值
    - score：score_technical 返回值
    """

    if df is None or df.empty:
        return f"# 技术分析报告\n\n股票 {stock.get('code', '-')} 无行情数据，无法生成报告。\n"

    code = stock.get("code", "-")
    name = stock.get("name", "")
    date_text = datetime.now().strftime("%Y-%m-%d %H:%M")

    close = _latest_value(df, "close")
    pct = _latest_value(df, "pct_chg")

    lines = []
    lines.append(f"# 技术分析报告：{name or code}（{code}）")
    lines.append("")
    lines.append(f"> 生成时间：{date_text}　|　数据截至：{df['date'].iloc[-1].date() if 'date' in df.columns else '-'}")
    lines.append("> 本报告由技术指标自动生成，仅供研究参考，不构成投资建议。")
    lines.append("")

    # 一、当前行情
    lines.append("## 一、当前行情")
    lines.append("")
    lines.append(f"- 最新收盘价：{_fmt_price(close)}　涨跌幅：{_fmt_pct(pct)}")
    lines.append(f"- 趋势判断：**{trend.get('trend', '数据不足')}**（{trend.get('alignment', '-')}）")
    lines.append(f"- 近 20 日涨跌幅：{_fmt_pct(trend.get('recent_percent'))}")
    lines.append(f"- 距 MA20 偏离：{_fmt_pct(trend.get('price_vs_ma20'))}　距 MA60 偏离：{_fmt_pct(trend.get('price_vs_ma60'))}")
    lines.append("")

    # 二、技术指标
    lines.append("## 二、技术指标明细")
    lines.append("")
    lines.append(_indicator_table(df))
    lines.append("")

    # 三、综合评分
    lines.append("## 三、综合评分")
    lines.append("")
    lines.append(f"- 综合得分：**{score.get('score')}/100**")
    lines.append(f"- 信号：**{score.get('signal')}**　风险等级：**{score.get('risk_level')}**")
    lines.append("")

    if score.get("items"):
        lines.append("| 信号项 | 方向 | 依据 |")
        lines.append("|---|---|---|")

        for item in score["items"]:
            lines.append(
                f"| {item.get('name', '-')} | {_signal_impact_mark(item.get('impact', 'neutral'))} | {item.get('detail', '')} |"
            )

        lines.append("")

    lines.append(score.get("note", ""))
    lines.append("")

    # 四、支撑位与压力位
    lines.append("## 四、支撑位与压力位")
    lines.append("")

    if sr.get("supports") or sr.get("resistances"):
        if sr.get("supports"):
            lines.append("### 支撑位")
            lines.append("")
            lines.append("| 价格 | 类型 | 说明 |")
            lines.append("|---|---|---|")

            for item in sr["supports"]:
                lines.append(
                    f"| {item.get('price')} | {item.get('type', '-')} | {item.get('detail', '')} |"
                )

            lines.append("")

        if sr.get("resistances"):
            lines.append("### 压力位")
            lines.append("")
            lines.append("| 价格 | 类型 | 说明 |")
            lines.append("|---|---|---|")

            for item in sr["resistances"]:
                lines.append(
                    f"| {item.get('price')} | {item.get('type', '-')} | {item.get('detail', '')} |"
                )

            lines.append("")
    else:
        lines.append("数据不足，未识别出支撑/压力位。")
        lines.append("")

    # 五、综合研判与观望建议
    lines.append("## 五、综合研判与观望建议")
    lines.append("")
    lines.append(_build_advice(trend, sr, score))
    lines.append("")
    lines.append("---")
    lines.append("")
    lines.append("*免责声明：本报告由规则化指标自动生成，不承诺收益、不构成投资建议；市场有风险，决策需谨慎。*")

    return "\n".join(lines)


def _build_advice(trend: dict, sr: dict, score: dict) -> str:
    """基于评分与趋势生成观望/关注建议（允许观望，不强制信号）"""

    signal = score.get("signal", "数据不足")
    risk = score.get("risk_level", "数据不足")
    trend_text = trend.get("trend", "数据不足")

    parts = []

    if signal == "看多":
        parts.append(f"当前技术面偏多（{trend_text}），可关注趋势延续与量能配合情况。")
    elif signal == "看空":
        parts.append(f"当前技术面偏空（{trend_text}），建议谨慎，等待企稳信号。")
    else:
        parts.append("当前多空信号不强，建议观望，等待方向明朗后跟进。")

    supports = sr.get("supports", [])
    resistances = sr.get("resistances", [])

    if supports:
        nearest = supports[0]
        parts.append(f"下方首要支撑参考 {nearest.get('price')}（{nearest.get('type')}），跌破需警惕趋势走弱。")

    if resistances:
        nearest = resistances[0]
        parts.append(f"上方首要压力参考 {nearest.get('price')}（{nearest.get('type')}），突破或打开上行空间。")

    parts.append(f"风险等级：{risk}。评分与信号仅为规则化参考，建议结合基本面与市场环境综合判断。")

    return "\n".join(f"- {part}" for part in parts)
