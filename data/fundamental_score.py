"""基本面综合评分（阶段 5.5）

输入：财务趋势摘要 dict（data.financial_trend.trend_summary 输出），
      可选估值指标 dict（data.valuation.compute_valuation 输出）。
输出：综合评分 dict（score / grade / risk_level / items / 说明）。

口径（可解释、加权、基准 50 分，0~100 封顶）：
- 成长性（25 分）：营收同比、净利同比、连续同比增长期数
- 盈利能力（30 分）：ROE、毛利率、净利率
- 财务健康（25 分）：资产负债率、经营现金流、盈利覆盖
- 估值水平（20 分，缺估值数据按 0 计，不硬算）：PE_TTM、PB

数据不足不硬算：缺少营收与净利（核心指标全空）时返回 None 评分。
风险等级：数据不足/高负债/亏损/估值过高时给出对应风险提示。
"""

import pandas as pd


def _num(value):
    """可空数值转换，缺失/NaN 返回 None"""

    if value is None or pd.isna(value):
        return None
    return float(value)


def _growth_items(summary: dict) -> list:
    """成长性（25 分）"""

    items = []

    revenue_yoy = _num(summary.get("revenue_yoy"))
    if revenue_yoy is None:
        items.append({"name": "营收同比", "score": 0, "detail": "数据缺失"})
    elif revenue_yoy >= 20:
        items.append({"name": "营收同比", "score": 8, "detail": f"{revenue_yoy:+.1f}%"})
    elif revenue_yoy > 0:
        items.append({"name": "营收同比", "score": 4, "detail": f"{revenue_yoy:+.1f}%"})
    else:
        items.append({"name": "营收同比", "score": -8, "detail": f"{revenue_yoy:+.1f}%"})

    profit_yoy = _num(summary.get("net_profit_yoy"))
    if profit_yoy is None:
        items.append({"name": "净利同比", "score": 0, "detail": "数据缺失"})
    elif profit_yoy >= 20:
        items.append({"name": "净利同比", "score": 8, "detail": f"{profit_yoy:+.1f}%"})
    elif profit_yoy > 0:
        items.append({"name": "净利同比", "score": 4, "detail": f"{profit_yoy:+.1f}%"})
    else:
        items.append({"name": "净利同比", "score": -8, "detail": f"{profit_yoy:+.1f}%"})

    growth_periods = int(summary.get("revenue_growth_periods", 0) or 0)
    if growth_periods >= 3:
        items.append(
            {"name": "连续增长", "score": 9, "detail": f"连续 {growth_periods} 期营收同比正增长"}
        )
    elif growth_periods >= 1:
        items.append(
            {"name": "连续增长", "score": 2, "detail": f"连续 {growth_periods} 期营收同比正增长"}
        )
    else:
        items.append({"name": "连续增长", "score": -5, "detail": "最新期营收同比下滑"})

    return items


def _profit_items(summary: dict) -> list:
    """盈利能力（30 分）"""

    items = []

    roe = _num(summary.get("roe"))
    if roe is None:
        items.append({"name": "ROE", "score": 0, "detail": "数据缺失"})
    elif roe >= 15:
        items.append({"name": "ROE", "score": 12, "detail": f"{roe:.1f}%"})
    elif roe >= 5:
        items.append({"name": "ROE", "score": 5, "detail": f"{roe:.1f}%"})
    elif roe >= 0:
        items.append({"name": "ROE", "score": 0, "detail": f"{roe:.1f}%"})
    else:
        items.append({"name": "ROE", "score": -8, "detail": f"{roe:.1f}%"})

    margin = _num(summary.get("gross_margin"))
    if margin is None:
        items.append({"name": "毛利率", "score": 0, "detail": "数据缺失"})
    elif margin >= 40:
        items.append({"name": "毛利率", "score": 10, "detail": f"{margin:.1f}%"})
    elif margin >= 15:
        items.append({"name": "毛利率", "score": 4, "detail": f"{margin:.1f}%"})
    elif margin >= 0:
        items.append({"name": "毛利率", "score": 0, "detail": f"{margin:.1f}%"})
    else:
        items.append({"name": "毛利率", "score": -6, "detail": f"{margin:.1f}%"})

    net_margin = _num(summary.get("net_margin"))
    if net_margin is None:
        items.append({"name": "净利率", "score": 0, "detail": "数据缺失"})
    elif net_margin >= 15:
        items.append({"name": "净利率", "score": 8, "detail": f"{net_margin:.1f}%"})
    elif net_margin >= 5:
        items.append({"name": "净利率", "score": 3, "detail": f"{net_margin:.1f}%"})
    elif net_margin >= 0:
        items.append({"name": "净利率", "score": 0, "detail": f"{net_margin:.1f}%"})
    else:
        items.append({"name": "净利率", "score": -6, "detail": f"{net_margin:.1f}%"})

    return items


def _health_items(summary: dict) -> list:
    """财务健康（25 分）"""

    items = []

    debt_ratio = _num(summary.get("debt_ratio"))
    if debt_ratio is None:
        items.append({"name": "资产负债率", "score": 0, "detail": "数据缺失"})
    elif debt_ratio <= 40:
        items.append({"name": "资产负债率", "score": 12, "detail": f"{debt_ratio:.1f}%"})
    elif debt_ratio <= 70:
        items.append({"name": "资产负债率", "score": 4, "detail": f"{debt_ratio:.1f}%"})
    else:
        items.append({"name": "资产负债率", "score": -8, "detail": f"{debt_ratio:.1f}%"})

    netcash = _num(summary.get("netcash_operate"))
    if netcash is None:
        items.append({"name": "经营现金流", "score": 0, "detail": "数据缺失"})
    elif netcash > 0:
        items.append({"name": "经营现金流", "score": 8, "detail": "为正"})
    else:
        items.append({"name": "经营现金流", "score": -8, "detail": "为负或为零"})

    net_profit = _num(summary.get("net_profit"))
    if net_profit is None:
        items.append({"name": "盈利覆盖", "score": 0, "detail": "数据缺失"})
    elif net_profit > 0:
        items.append({"name": "盈利覆盖", "score": 5, "detail": "净利润为正"})
    else:
        items.append({"name": "盈利覆盖", "score": -5, "detail": "净利润为负"})

    return items


def _valuation_items(valuation: dict | None) -> list:
    """估值水平（20 分）；缺估值数据按 0 计，不硬算"""

    if not valuation:
        return [{"name": "估值水平", "score": 0, "detail": "无估值数据"}]

    items = []

    pe_ttm = _num(valuation.get("pe_ttm"))
    if pe_ttm is None:
        items.append({"name": "PE_TTM", "score": 0, "detail": "数据缺失"})
    elif 0 < pe_ttm <= 30:
        items.append({"name": "PE_TTM", "score": 10, "detail": f"{pe_ttm:.1f}"})
    elif 0 < pe_ttm <= 50:
        items.append({"name": "PE_TTM", "score": 6, "detail": f"{pe_ttm:.1f}"})
    elif pe_ttm > 50:
        items.append({"name": "PE_TTM", "score": -6, "detail": f"{pe_ttm:.1f}"})
    else:
        items.append({"name": "PE_TTM", "score": -10, "detail": f"{pe_ttm:.1f}"})

    pb = _num(valuation.get("pb"))
    if pb is None:
        items.append({"name": "PB", "score": 0, "detail": "数据缺失"})
    elif 0 < pb <= 10:
        items.append({"name": "PB", "score": 10, "detail": f"{pb:.2f}"})
    elif 0 < pb <= 30:
        items.append({"name": "PB", "score": 5, "detail": f"{pb:.2f}"})
    elif pb > 30:
        items.append({"name": "PB", "score": -5, "detail": f"{pb:.2f}"})
    else:
        items.append({"name": "PB", "score": -10, "detail": f"{pb:.2f}"})

    return items


def _grade(score: float) -> str:
    if score >= 80:
        return "优秀"
    if score >= 65:
        return "良好"
    if score >= 50:
        return "一般"
    if score >= 35:
        return "偏弱"
    return "差"


def _risk_level(summary: dict, score: float) -> str:
    """风险等级：结合评分与负债/亏损/现金流判断"""

    risks = []

    if _num(summary.get("debt_ratio")) is not None and _num(summary.get("debt_ratio")) > 80:
        risks.append("高负债")
    if _num(summary.get("net_profit")) is not None and _num(summary.get("net_profit")) <= 0:
        risks.append("亏损")
    if _num(summary.get("netcash_operate")) is not None and _num(summary.get("netcash_operate")) <= 0:
        risks.append("经营现金流为负")

    if not risks:
        if score >= 65:
            return "低风险"
        if score >= 50:
            return "中低风险"
        return "中风险"

    return "高风险" if len(risks) >= 2 else "中高风险"


def fundamental_score(summary: dict, valuation: dict | None = None) -> dict:
    """基本面综合评分

    返回 dict：
      - score: 0~100 综合评分（None 表示核心数据不足不硬算）
      - grade: 优秀/良好/一般/偏弱
      - risk_level: 低/中低/中/中高/高风险
      - items: 各维度评分明细（name/score/detail）
      - total_revenue / total_profit: 核心数据覆盖标记
    """

    if not summary:
        return {
            "score": None,
            "grade": None,
            "risk_level": "数据不足",
            "items": [],
            "data_sufficient": False,
        }

    revenue = _num(summary.get("revenue"))
    profit = _num(summary.get("net_profit"))

    # 数据不足不硬算：营收与净利核心指标全空
    if revenue is None and profit is None:
        return {
            "score": None,
            "grade": None,
            "risk_level": "数据不足",
            "items": [],
            "data_sufficient": False,
        }

    items = (
        _growth_items(summary)
        + _profit_items(summary)
        + _health_items(summary)
        + _valuation_items(valuation)
    )

    score = 50.0 + sum(item["score"] for item in items)
    score = max(0.0, min(100.0, score))

    # 估值扣分在封顶后生效：优秀公司被高估值拉低时可见，避免满分掩盖风险
    valuation_penalty = sum(
        item["score"] for item in items if item["name"] in ("PE_TTM", "PB") and item["score"] < 0
    )
    if valuation_penalty < 0:
        score = max(0.0, score + valuation_penalty)

    return {
        "score": round(score, 1),
        "grade": _grade(score),
        "risk_level": _risk_level(summary, score),
        "items": items,
        "data_sufficient": True,
    }
