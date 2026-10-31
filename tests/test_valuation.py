"""估值指标计算层测试（阶段 5.3）"""

from datetime import date

import numpy as np
import pandas as pd
import pytest

from data.valuation import _compute_ttm_eps, compute_valuation, get_latest_close


def _make_frame():
    """构造 2024 年报 + 2025 Q1/H1/Q3 的累计 eps/bps 样例"""

    return pd.DataFrame(
        [
            {
                "stock_code": "600519",
                "report_date": pd.Timestamp("2024-12-31"),
                "eps": 40.0,
                "bps": 300.0,
            },
            {
                "stock_code": "600519",
                "report_date": pd.Timestamp("2025-03-31"),
                "eps": 12.0,
                "bps": 320.0,
            },
            {
                "stock_code": "600519",
                "report_date": pd.Timestamp("2025-06-30"),
                "eps": 25.0,
                "bps": 335.0,
            },
            {
                "stock_code": "600519",
                "report_date": pd.Timestamp("2025-09-30"),
                "eps": 38.0,
                "bps": 350.0,
            },
        ]
    )


class TestComputeValuation:
    def test_静态pe_pb(self):
        frame = _make_frame()
        result = compute_valuation(frame, close=1520.0)

        # 最新期 eps=38, bps=350
        assert result["pe"] == pytest.approx(1520 / 38, rel=1e-2)
        assert result["pb"] == pytest.approx(1520 / 350, rel=1e-2)
        assert result["report_date"] == "2025-09-30"

    def test_pe_ttm_口径(self):
        frame = _make_frame()
        # TTM = 25Q3累计38 + 24年报40 - 24Q3(缺) → 缺去年同期应返回 None
        result = compute_valuation(frame, close=1520.0)
        assert result["pe_ttm"] is None

    def test_pe_ttm_有去年同期(self):
        frame = _make_frame()
        frame.loc[-1] = [
            "600519",
            pd.Timestamp("2024-09-30"),
            30.0,
            290.0,
        ]
        frame = frame.sort_values("report_date").reset_index(drop=True)

        result = compute_valuation(frame, close=1520.0)
        # TTM eps = 38 + 40 - 30 = 48
        assert result["pe_ttm"] == pytest.approx(1520 / 48, rel=1e-2)

    def test_最新为年报(self):
        frame = _make_frame()
        frame = frame[frame["report_date"] == pd.Timestamp("2024-12-31")].copy()
        result = compute_valuation(frame, close=1600.0)

        assert result["pe_ttm"] == pytest.approx(1600 / 40, rel=1e-2)

    def test_除零与缺列(self):
        # eps 为 0 → pe None；缺 bps → pb None
        frame = pd.DataFrame(
            [
                {
                    "stock_code": "600519",
                    "report_date": pd.Timestamp("2025-09-30"),
                    "eps": 0.0,
                }
            ]
        )
        result = compute_valuation(frame, close=100.0)

        assert result["pe"] is None
        assert result["pb"] is None
        assert result["pe_ttm"] is None

    def test_空输入(self):
        result = compute_valuation(pd.DataFrame(), close=None)
        assert result["close"] is None
        assert result["pe"] is None

        result = compute_valuation(None, close=10.0)
        assert result["close"] == 10.0

    def test_close为None(self):
        frame = _make_frame()
        result = compute_valuation(frame, close=None)
        assert result["pe"] is None


class TestTtmEps:
    def test_年报直接取(self):
        frame = pd.DataFrame(
            [
                {
                    "stock_code": "600519",
                    "report_date": pd.Timestamp("2024-12-31"),
                    "eps": 40.0,
                }
            ]
        )
        assert _compute_ttm_eps(frame) == pytest.approx(40.0)

    def test_缺去年同期(self):
        frame = _make_frame()
        assert _compute_ttm_eps(frame) is None

    def test_无eps列(self):
        frame = pd.DataFrame(
            [{"stock_code": "600519", "report_date": pd.Timestamp("2025-09-30")}]
        )
        assert _compute_ttm_eps(frame) is None


class TestGetLatestClose:
    def test_无数据返回None(self):
        # 无效代码路径：查询不存在的库应返回 None 而不是抛错
        assert get_latest_close("000000") is None
