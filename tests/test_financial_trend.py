"""财务趋势与报表分析测试（阶段 5.4）"""

import pandas as pd
import pytest

from data.financial_trend import (
    _pct_change,
    financial_report_markdown,
    trend_summary,
    trend_table,
)


def _make_frame():
    """三年 12 个报告期：营收/净利逐年增长，毛利率稳定，负债率平稳"""

    rows = []
    base = 1000.0
    for year in (2023, 2024, 2025):
        for month, day in ((3, 31), (6, 30), (9, 30), (12, 31)):
            rows.append(
                {
                    "stock_code": "600519",
                    "report_date": pd.Timestamp(f"{year}-{month:02d}-{day}"),
                    "announce_date": pd.Timestamp(
                        f"{year + 1}-{month:02d}-{min(day + 20, 28)}"
                    ),
                    "operate_income": base,
                    "operate_cost": base * 0.6,
                    "net_profit": base * 0.2,
                    "parent_net_profit": base * 0.19,
                    "parent_equity": base * 1.0,
                    "total_assets": base * 2.0,
                    "total_liabilities": base * 0.5,
                    "netcash_operate": base * 0.25,
                }
            )
            base *= 1.1
    return pd.DataFrame(rows)


class TestTrendSummary:
    def test_核心指标(self):
        frame = _make_frame()
        summary = trend_summary(frame)

        assert summary["periods"] == 12
        assert summary["report_date"] == "2025-12-31"
        # 最新期营收为第 12 期
        assert summary["revenue"] is not None
        assert summary["revenue_yoy"] is not None
        assert summary["net_profit_yoy"] is not None
        assert summary["gross_margin"] is not None
        assert summary["net_margin"] is not None
        assert summary["roe"] is not None
        assert summary["debt_ratio"] is not None

    def test_连续增长期数(self):
        frame = _make_frame()
        summary = trend_summary(frame)

        # 全部期数同比正增长（yoy 自算）
        assert summary["revenue_growth_periods"] >= 11
        assert summary["profit_growth_periods"] >= 11

    def test_最新期同比下滑(self):
        frame = _make_frame()
        # 最新期营收设为去年同期的 0.9 倍 → 同比下滑
        frame.loc[frame.index[-1], "operate_income"] = frame.loc[
            frame.index[-8], "operate_income"
        ] * 0.9
        summary = trend_summary(frame)

        assert summary["revenue_growth_periods"] == 0

    def test_空输入(self):
        summary = trend_summary(pd.DataFrame())
        assert summary["report_date"] is None
        assert summary["periods"] == 0

    def test_环比(self):
        frame = _make_frame()
        summary = trend_summary(frame)

        # 最新营收比上一期高约 10%
        assert summary["revenue_qoq"] == pytest.approx(10.0, rel=0.5)


class TestTrendTable:
    def test_输出含表头与最新期(self):
        frame = _make_frame()
        table = trend_table(frame)

        assert "报告期" in table
        assert "披露日期" in table
        assert "2025-12-31" in table
        assert "2025-09-30" in table
        # 最新 5 期，不含 2024-06-30 之前的报告期
        assert "2024-06-30" not in table

    def test_空输入(self):
        assert "无财报数据" in trend_table(pd.DataFrame())


class TestFinancialReportMarkdown:
    def test_报告结构(self):
        frame = _make_frame()
        text = financial_report_markdown("600519", frame)

        assert "# 600519 财务报表分析" in text
        assert "## 核心指标" in text
        assert "## 多期趋势" in text
        assert "连续营收同比增长期数" in text
        assert "最新报告期：2025-12-31" in text
        assert "披露日期：" in text

    def test_带估值(self):
        frame = _make_frame()
        valuation = {"close": 100.0, "pe": 25.0, "pe_ttm": 22.0, "pb": 5.0}
        text = financial_report_markdown("600519", frame, valuation)

        assert "## 估值" in text
        assert "静态 PE" in text
        assert "PE_TTM" in text
        assert "PB" in text


class TestPctChange:
    def test_正常(self):
        assert _pct_change(110.0, 100.0) == pytest.approx(10.0)

    def test_除零(self):
        assert _pct_change(100.0, 0.0) is None

    def test_缺失(self):
        assert _pct_change(None, 100.0) is None
        assert _pct_change(100.0, None) is None
