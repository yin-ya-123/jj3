"""基本面分析页面测试（阶段 5.6）

页面渲染函数依赖 streamlit 运行态，不做单测；
此处覆盖纯函数：build_fundamental_report_markdown 报告组装、_load_fundamental_frame 宽表加载。
"""

from types import SimpleNamespace
from unittest.mock import patch

import pandas as pd
import pytest

from ui.fundamental_analysis import _load_fundamental_frame, build_fundamental_report_markdown
from data.fundamentals import reports_to_frame


def _sample_records() -> list[SimpleNamespace]:
    """模拟 FinancialReport 记录对象（report_date 用 date 对象）"""

    return [
        SimpleNamespace(
            stock_code="600519",
            report_date=pd.Timestamp("2025-12-31"),
            announce_date=pd.Timestamp("2026-04-03"),
            operate_income=1500.0,
            operate_income_yoy=10.0,
            net_profit=600.0,
            net_profit_yoy=12.0,
            gross_profit_ratio=80.0,
            net_profit_ratio=40.0,
            roe=20.0,
            debt_ratio=20.0,
            netcash_operate=500.0,
            eps=40.0,
            bps=150.0,
        ),
        SimpleNamespace(
            stock_code="600519",
            report_date=pd.Timestamp("2026-09-30"),
            announce_date=pd.Timestamp("2026-10-27"),
            operate_income=1200.0,
            operate_income_yoy=15.0,
            net_profit=500.0,
            net_profit_yoy=10.0,
            gross_profit_ratio=85.0,
            net_profit_ratio=42.0,
            roe=18.0,
            debt_ratio=18.0,
            netcash_operate=400.0,
            eps=35.0,
            bps=160.0,
        ),
    ]


class TestFundamentalAnalysis:
    def test_load_fundamental_frame(self):
        with patch(
            "ui.fundamental_analysis.get_financial_reports", return_value=[]
        ) as mock_get:
            frame = _load_fundamental_frame("600519")
            mock_get.assert_called_once_with("600519")
            assert frame.empty

        with patch(
            "ui.fundamental_analysis.get_financial_reports",
            return_value=_sample_records(),
        ):
            frame = _load_fundamental_frame("600519")
            assert len(frame) == 2
            # 按报告期升序
            assert frame["report_date"].iloc[0] == pd.Timestamp("2025-12-31")
            assert frame["report_date"].iloc[-1] == pd.Timestamp("2026-09-30")

    def test_build_report_含评分段(self):
        frame = reports_to_frame(_sample_records())
        report = build_fundamental_report_markdown(
            "600519", "贵州茅台", frame, {"pe_ttm": 21.2, "pb": 6.42, "pe": 27.0, "close": 1392.05}
        )

        assert "600519 财务报表分析" in report
        assert "基本面综合评分" in report
        assert "综合得分" in report
        assert "评级" in report
        assert "评分项" in report
        assert "ROE" in report

    def test_build_report_数据不足时不含评分明细(self):
        empty_frame = pd.DataFrame()
        report = build_fundamental_report_markdown("600519", "贵州茅台", empty_frame)

        assert "600519 财务报表分析" in report
        assert "基本面综合评分" in report
        assert "未给出评分" in report

    def test_build_report_估值区块(self):
        frame = reports_to_frame(_sample_records())
        report = build_fundamental_report_markdown(
            "600519", "贵州茅台", frame, {"pe_ttm": 21.2, "pb": 6.42, "pe": 27.0, "close": 1392.05}
        )

        assert "## 估值" in report
        assert "PE_TTM" in report
        assert "21.2" in report
