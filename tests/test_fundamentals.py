"""财务指标计算层测试（阶段 5.2）"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from data.fundamentals import (
    compute_fundamental_metrics,
    get_metrics_by_report,
    reports_to_frame,
)


def _make_frame():
    """构造两年四个报告期的宽表样例（缺部分自带指标，验证兜底）"""

    return pd.DataFrame(
        [
            {
                "stock_code": "600519",
                "report_date": pd.Timestamp("2025-12-31"),
                "announce_date": pd.Timestamp("2026-04-28"),
                "operate_income": 1000.0,
                "operate_cost": 600.0,
                "net_profit": 200.0,
                "parent_net_profit": 190.0,
                "parent_equity": 1000.0,
                "total_assets": 2000.0,
                "total_liabilities": 500.0,
                "netcash_operate": 300.0,
                # 缺 gross_profit_ratio / net_profit_ratio / roe / yoy
            },
            {
                "stock_code": "600519",
                "report_date": pd.Timestamp("2024-12-31"),
                "announce_date": pd.Timestamp("2025-04-25"),
                "operate_income": 800.0,
                "operate_cost": 500.0,
                "net_profit": 150.0,
                "parent_net_profit": 140.0,
                "parent_equity": 900.0,
                "total_assets": 1800.0,
                "total_liabilities": 400.0,
                "netcash_operate": 250.0,
            },
        ]
    )


class TestComputeFundamentalMetrics:
    def test_自带指标透传_缺失指标自算兜底(self):
        frame = compute_fundamental_metrics(_make_frame())

        latest = frame[frame["report_date"] == pd.Timestamp("2025-12-31")].iloc[0]

        # 毛利率兜底：(1000-600)/1000
        assert latest["gross_profit_ratio"] == pytest.approx(40.0)
        # 净利率兜底：200/1000
        assert latest["net_profit_ratio"] == pytest.approx(20.0)
        # ROE 兜底：190/1000
        assert latest["roe"] == pytest.approx(19.0)
        # 资产负债率
        assert latest["debt_ratio"] == pytest.approx(25.0)
        # 经营现金流透传
        assert latest["netcash_operate"] == pytest.approx(300.0)

    def test_同比自算(self):
        frame = compute_fundamental_metrics(_make_frame())

        latest = frame[frame["report_date"] == pd.Timestamp("2025-12-31")].iloc[0]
        # 营收同比：(1000/800 - 1)
        assert latest["operate_income_yoy"] == pytest.approx(25.0)
        # 净利润同比：(200/150 - 1)
        assert latest["net_profit_yoy"] == pytest.approx(100 / 3 * 1.0)

    def test_自带指标优先(self):
        df = _make_frame()
        df.loc[0, "gross_profit_ratio"] = 55.0
        df.loc[0, "roe"] = 30.0
        df.loc[0, "operate_income_yoy"] = 30.0

        frame = compute_fundamental_metrics(df)
        latest = frame[frame["report_date"] == pd.Timestamp("2025-12-31")].iloc[0]

        assert latest["gross_profit_ratio"] == pytest.approx(55.0)
        assert latest["roe"] == pytest.approx(30.0)
        assert latest["operate_income_yoy"] == pytest.approx(30.0)

    def test_除零保护(self):
        df = _make_frame()
        df.loc[0, "operate_income"] = 0.0
        df.loc[0, "total_assets"] = 0.0

        frame = compute_fundamental_metrics(df)
        latest = frame[frame["report_date"] == pd.Timestamp("2025-12-31")].iloc[0]

        assert np.isnan(latest["gross_profit_ratio"])
        assert np.isnan(latest["debt_ratio"])

    def test_缺列容错(self):
        df = pd.DataFrame(
            [
                {
                    "stock_code": "600519",
                    "report_date": pd.Timestamp("2025-12-31"),
                    "operate_income": 100.0,
                }
            ]
        )
        frame = compute_fundamental_metrics(df)

        assert "operate_income" in frame.columns
        assert "debt_ratio" not in frame.columns

    def test_空输入(self):
        assert compute_fundamental_metrics(pd.DataFrame()).empty
        assert compute_fundamental_metrics(None) is None

    def test_净利缺失用归母兜底(self):
        df = _make_frame()
        df.loc[0, "net_profit"] = np.nan
        df.loc[0, "parent_net_profit"] = 190.0

        frame = compute_fundamental_metrics(df)
        latest = frame[frame["report_date"] == pd.Timestamp("2025-12-31")].iloc[0]

        assert latest["net_profit"] == pytest.approx(190.0)


class TestReportsToFrame:
    class _FakeRecord:
        def __init__(self, **kwargs):
            self.stock_code = kwargs.get("stock_code", "600519")
            self.report_date = kwargs.get("report_date", date(2025, 12, 31))
            self.announce_date = kwargs.get("announce_date", date(2026, 4, 28))
            self.operate_income = kwargs.get("operate_income", 1000.0)
            self.roe = kwargs.get("roe", None)

    def test_记录列表转宽表(self):
        records = [
            self._FakeRecord(report_date=date(2025, 12, 31)),
            self._FakeRecord(report_date=date(2024, 12, 31), operate_income=800.0),
        ]
        frame = reports_to_frame(records)

        assert len(frame) == 2
        assert frame["operate_income"].tolist() == [800.0, 1000.0]
        assert frame["report_date"].iloc[-1] == pd.Timestamp("2025-12-31")
        assert np.isnan(frame["roe"].iloc[0])

    def test_空记录(self):
        assert reports_to_frame([]).empty


class TestGetMetricsByReport:
    def test_按报告期取指标(self):
        frame = compute_fundamental_metrics(_make_frame())
        metrics = get_metrics_by_report("2025-12-31", frame)

        assert metrics["operate_income"] == pytest.approx(1000.0)
        assert metrics["gross_profit_ratio"] == pytest.approx(40.0)

    def test_找不到报告期(self):
        frame = compute_fundamental_metrics(_make_frame())
        assert get_metrics_by_report("2023-12-31", frame) == {}
