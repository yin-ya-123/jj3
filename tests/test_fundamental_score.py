"""基本面综合评分测试（阶段 5.5）"""

import pytest

from data.fundamental_score import fundamental_score


def _good_summary():
    """高质量基本面：高增长、高毛利、低负债、现金流为正"""

    return {
        "revenue": 1000.0,
        "revenue_yoy": 25.0,
        "net_profit": 200.0,
        "net_profit_yoy": 30.0,
        "gross_margin": 60.0,
        "net_margin": 20.0,
        "roe": 18.0,
        "debt_ratio": 30.0,
        "netcash_operate": 150.0,
        "revenue_growth_periods": 4,
    }


def _bad_summary():
    """差基本面：亏损、高负债、现金流为负、营收下滑"""

    return {
        "revenue": 100.0,
        "revenue_yoy": -10.0,
        "net_profit": -20.0,
        "net_profit_yoy": -50.0,
        "gross_margin": 5.0,
        "net_margin": -20.0,
        "roe": -3.0,
        "debt_ratio": 90.0,
        "netcash_operate": -5.0,
        "revenue_growth_periods": 0,
    }


class TestFundamentalScore:
    def test_优秀公司高评分(self):
        result = fundamental_score(_good_summary())

        assert result["data_sufficient"] is True
        assert result["score"] >= 80
        assert result["grade"] == "优秀"
        assert result["risk_level"] == "低风险"

    def test_差公司低评分(self):
        result = fundamental_score(_bad_summary())

        assert result["data_sufficient"] is True
        assert result["score"] < 35
        assert result["grade"] == "差"
        assert result["risk_level"] == "高风险"

    def test_封顶与保底(self):
        # 极端高分不超 100
        summary = _good_summary()
        summary.update(
            {
                "revenue_yoy": 500.0,
                "net_profit_yoy": 500.0,
                "gross_margin": 95.0,
                "net_margin": 90.0,
                "roe": 50.0,
                "debt_ratio": 5.0,
                "revenue_growth_periods": 10,
            }
        )
        result = fundamental_score(summary)
        assert result["score"] <= 100

        # 极端低分不低于 0
        result_bad = fundamental_score(_bad_summary())
        assert result_bad["score"] >= 0

    def test_估值影响评分(self):
        base = fundamental_score(_good_summary())

        # PE_TTM 极高 → 估值扣分在封顶后生效
        high_valuation = {"pe_ttm": 200.0, "pb": 50.0}
        result = fundamental_score(_good_summary(), high_valuation)

        assert result["score"] < base["score"]

        # 中等公司 base 未封顶时，合理估值 → 加分可见
        mid_summary = _good_summary()
        mid_summary.update(
            {
                "revenue_yoy": 5.0,
                "net_profit_yoy": 5.0,
                "revenue_growth_periods": 2,
                "roe": 8.0,
                "gross_margin": 25.0,
                "net_margin": 8.0,
                "debt_ratio": 60.0,
            }
        )
        mid_base = fundamental_score(mid_summary)

        assert mid_base["score"] < 100

        low_valuation = {"pe_ttm": 15.0, "pb": 3.0}
        result_low = fundamental_score(mid_summary, low_valuation)

        assert result_low["score"] > mid_base["score"]

    def test_数据不足不硬算(self):
        result = fundamental_score({})
        assert result["score"] is None
        assert result["data_sufficient"] is False

        result = fundamental_score({"gross_margin": 50.0})
        assert result["score"] is None
        assert result["data_sufficient"] is False

    def test_评分明细可解释(self):
        result = fundamental_score(_good_summary(), {"pe_ttm": 20.0, "pb": 5.0})

        names = [item["name"] for item in result["items"]]
        assert "ROE" in names
        assert "毛利率" in names
        assert "资产负债率" in names
        assert "经营现金流" in names
        assert "PE_TTM" in names

        # 每个明细带说明
        for item in result["items"]:
            assert item["detail"]
