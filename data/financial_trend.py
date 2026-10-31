"""财务趋势与报表分析（阶段 5.4）

输入：财务指标宽表（data.fundamentals.compute_fundamental_metrics 输出），
      可选估值指标 dict（data.valuation.compute_valuation 输出）。
输出：趋势结构化 dict / Markdown 分析报告。

约定：
- 严格区分「报告期」（report_date，财报数据所属期间）与
  「披露日期」（announce_date，公告发布日期）。
- 同比（YOY）优先取财报自带字段（akshare 东财口径），缺失时自算。
- 环比（QOQ）自算：相邻报告期对比；跨季度累计口径下仅作趋势参考。
- 纯函数、缺数据返回 None / "-"，不抛错，可离线测试。
"""

import pandas as pd

from data.fundamentals import compute_fundamental_metrics


def _fmt_price(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):.2f}"


def _fmt_pct(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):+.2f}%"


def _fmt_num(value) -> str:
    if value is None or pd.isna(value):
        return "-"
    return f"{float(value):,.2f}"


def _pct_change(current, previous):
    """环比/同比百分比：(current/previous - 1)*100，除零/缺失返回 None"""

    if current is None or previous is None or pd.isna(current) or pd.isna(previous):
        return None
    if previous == 0:
        return None
    return (float(current) / float(previous) - 1.0) * 100.0


def trend_summary(frame: pd.DataFrame) -> dict:
    """多期财务趋势摘要

    返回 dict：
      - report_date / announce_date: 最新报告期与披露日期
      - revenue / revenue_yoy / revenue_qoq: 营收及同比环比
      - net_profit / net_profit_yoy: 净利润及同比
      - gross_margin / net_margin / roe / debt_ratio: 比率指标
      - netcash_operate: 经营现金流净额
      - revenue_growth_periods: 连续同比营收增长期数（0 表示最新期同比下滑）
      - profit_growth_periods: 连续同比净利润增长期数
      - periods: 参与分析的报告期数量
    """

    empty = {
        "report_date": None,
        "announce_date": None,
        "revenue": None,
        "revenue_yoy": None,
        "revenue_qoq": None,
        "net_profit": None,
        "net_profit_yoy": None,
        "gross_margin": None,
        "net_margin": None,
        "roe": None,
        "debt_ratio": None,
        "netcash_operate": None,
        "revenue_growth_periods": 0,
        "profit_growth_periods": 0,
        "periods": 0,
    }

    if frame is None or frame.empty:
        return empty

    frame = compute_fundamental_metrics(frame)
    if frame.empty or len(frame) < 1:
        return empty

    result = dict(empty)
    latest = frame.iloc[-1]

    result["periods"] = len(frame)
    result["report_date"] = (
        latest["report_date"].strftime("%Y-%m-%d")
        if latest.get("report_date") is not None
        else None
    )
    result["announce_date"] = (
        latest["announce_date"].strftime("%Y-%m-%d")
        if latest.get("announce_date") is not None
        else None
    )

    result["revenue"] = _value(latest, "operate_income")
    result["revenue_yoy"] = _value(latest, "operate_income_yoy")
    result["net_profit"] = _value(latest, "net_profit")
    result["net_profit_yoy"] = _value(latest, "net_profit_yoy")
    result["gross_margin"] = _value(latest, "gross_profit_ratio")
    result["net_margin"] = _value(latest, "net_profit_ratio")
    result["roe"] = _value(latest, "roe")
    result["debt_ratio"] = _value(latest, "debt_ratio")
    result["netcash_operate"] = _value(latest, "netcash_operate")

    # 环比：最新期 vs 上一报告期
    if len(frame) >= 2:
        prev = frame.iloc[-2]
        result["revenue_qoq"] = _pct_change(
            _value(latest, "operate_income"), _value(prev, "operate_income")
        )

    # 连续同比增长期数（从最新往前数）
    result["revenue_growth_periods"] = _consecutive_yoy_growth(
        frame, "operate_income_yoy", "operate_income"
    )
    result["profit_growth_periods"] = _consecutive_yoy_growth(
        frame, "net_profit_yoy", "net_profit"
    )

    return result


def _value(row, column):
    """取行内某列值，NaN/缺列转 None"""

    if column not in row.index:
        return None
    value = row[column]
    if pd.isna(value):
        return None
    return float(value)


def _consecutive_yoy_growth(frame: pd.DataFrame, yoy_column: str, value_column: str) -> int:
    """从最新报告期往前统计连续同比增长期数

    优先使用自带 yoy 列；缺失时按 value 同比自算。
    """

    frame = frame.sort_values("report_date").reset_index(drop=True)
    count = 0

    for idx in range(len(frame) - 1, -1, -1):
        row = frame.iloc[idx]
        yoy = _value(row, yoy_column)

        if yoy is None and value_column in frame.columns:
            current = _value(row, value_column)
            previous = _value(frame.iloc[idx - 1], value_column) if idx > 0 else None
            yoy = _pct_change(current, previous)

        if yoy is None or yoy <= 0:
            break
        count += 1

    return count


def trend_table(frame: pd.DataFrame, periods: int = 5) -> str:
    """多期指标趋势表（Markdown，报告期倒序）"""

    if frame is None or frame.empty:
        return "（无财报数据）"

    frame = compute_fundamental_metrics(frame)
    frame = frame.sort_values("report_date", ascending=False).head(periods)
    frame = frame.iloc[::-1]  # 报告期正序展示，最新在右

    lines = [
        "| 报告期 | 披露日期 | 营收 | 营收同比 | 净利润 | 净利同比 | 毛利率 | 净利率 | ROE | 负债率 | 经营现金流 |",
        "|---|---|---|---|---|---|---|---|---|---|---|",
    ]

    for _, row in frame.iterrows():
        report_date = (
            row["report_date"].strftime("%Y-%m-%d")
            if row.get("report_date") is not None
            else "-"
        )
        announce_date = (
            row["announce_date"].strftime("%Y-%m-%d")
            if row.get("announce_date") is not None
            else "-"
        )
        lines.append(
            "| {} | {} | {} | {} | {} | {} | {} | {} | {} | {} | {} |".format(
                report_date,
                announce_date,
                _fmt_num(_value(row, "operate_income")),
                _fmt_pct(_value(row, "operate_income_yoy")),
                _fmt_num(_value(row, "net_profit")),
                _fmt_pct(_value(row, "net_profit_yoy")),
                _fmt_pct(_value(row, "gross_profit_ratio")),
                _fmt_pct(_value(row, "net_profit_ratio")),
                _fmt_pct(_value(row, "roe")),
                _fmt_pct(_value(row, "debt_ratio")),
                _fmt_num(_value(row, "netcash_operate")),
            )
        )

    return "\n".join(lines)


def financial_report_markdown(
    symbol: str,
    frame: pd.DataFrame,
    valuation: dict | None = None,
) -> str:
    """组装财务报表分析 Markdown 报告

    参数：
        symbol: 股票代码（展示用）
        frame: 财报宽表
        valuation: data.valuation.compute_valuation 输出，可选
    """

    summary = trend_summary(frame)

    lines = [
        f"# {symbol} 财务报表分析",
        "",
        f"- 最新报告期：{summary['report_date'] or '-'}",
        f"- 披露日期：{summary['announce_date'] or '-'}",
        f"- 参与分析报告期数：{summary['periods']}",
        "",
        "## 核心指标",
        "",
    ]

    rows = [
        ("营业收入", _fmt_num(summary["revenue"])),
        ("营收同比", _fmt_pct(summary["revenue_yoy"])),
        ("营收环比", _fmt_pct(summary["revenue_qoq"])),
        ("净利润", _fmt_num(summary["net_profit"])),
        ("净利润同比", _fmt_pct(summary["net_profit_yoy"])),
        ("毛利率", _fmt_pct(summary["gross_margin"])),
        ("净利率", _fmt_pct(summary["net_margin"])),
        ("ROE", _fmt_pct(summary["roe"])),
        ("资产负债率", _fmt_pct(summary["debt_ratio"])),
        ("经营现金流净额", _fmt_num(summary["netcash_operate"])),
        ("连续营收同比增长期数", str(summary["revenue_growth_periods"])),
        ("连续净利润同比增长期数", str(summary["profit_growth_periods"])),
    ]

    lines.append("| 指标 | 最新值 |")
    lines.append("|---|---|")
    for label, value in rows:
        lines.append(f"| {label} | {value} |")

    # 估值区块（可选）
    if valuation:
        lines.extend(["", "## 估值", "", "| 指标 | 数值 |", "|---|---|"])
        lines.append(
            "| 收盘价 | {} |".format(_fmt_price(valuation.get("close")))
        )
        lines.append(
            "| 静态 PE | {} |".format(_fmt_price(valuation.get("pe")))
        )
        lines.append(
            "| PE_TTM | {} |".format(_fmt_price(valuation.get("pe_ttm")))
        )
        lines.append(
            "| PB | {} |".format(_fmt_price(valuation.get("pb")))
        )

    # 趋势表
    lines.extend(["", "## 多期趋势", "", trend_table(frame)])

    return "\n".join(lines)
