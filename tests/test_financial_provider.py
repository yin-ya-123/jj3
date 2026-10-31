"""财报 provider 归一化纯函数测试（离线，不触网）"""

import pandas as pd

from data.providers.akshare_financial_provider import (
    INDICATOR_ALIASES,
    derive_netcash_total,
    extract_indicators,
    merge_abstract,
    merge_report_frames,
)
from database.repositories.financial_report_repository import FLOAT_COLUMNS


def test_alias_keys_match_repository_columns():
    """provider 目标指标列必须与仓储落库列一致，防止字段漂移"""

    assert sorted(INDICATOR_ALIASES) == sorted(FLOAT_COLUMNS)


def _sheet_frame(report_dates, extra=None):
    frame = pd.DataFrame(
        {
            "REPORT_DATE": pd.to_datetime(report_dates),
            "NOTICE_DATE": pd.to_datetime(report_dates),
        }
    )
    if extra is not None:
        frame = pd.concat([frame, extra], axis=1)
    frame["report_date"] = pd.to_datetime(frame["REPORT_DATE"])
    frame["announce_date"] = pd.to_datetime(frame["NOTICE_DATE"])
    return frame


def test_merge_report_frames_joins_on_report_date():
    balance = _sheet_frame(
        ["2026-06-30", "2026-09-30"],
        pd.DataFrame({"TOTAL_ASSETS": [100.0, 120.0]}),
    )
    profit = _sheet_frame(
        ["2026-06-30"],
        pd.DataFrame({"OPERATE_INCOME": [50.0]}),
    )

    merged = merge_report_frames([balance, profit])

    # 利润表只有 06-30，outer join 后 09-30 行仍保留，OPERATE_INCOME 为空
    assert len(merged) == 2
    assert merged.loc[merged["report_date"] == "2026-09-30", "OPERATE_INCOME"].isna().all()
    assert (
        merged.loc[merged["report_date"] == "2026-06-30", "OPERATE_INCOME"].iloc[0]
        == 50.0
    )


def test_merge_report_frames_dedupes_announce_date():
    balance = _sheet_frame(
        ["2026-06-30"],
        pd.DataFrame({"TOTAL_ASSETS": [100.0]}),
    )
    profit = _sheet_frame(
        ["2026-06-30"],
        pd.DataFrame({"OPERATE_INCOME": [50.0]}),
    )

    merged = merge_report_frames([balance, profit])

    announce_columns = [
        column for column in merged.columns
        if column.startswith("announce_date")
    ]

    assert announce_columns == ["announce_date"]


def test_merge_report_frames_empty():
    assert merge_report_frames([]).empty


def test_merge_abstract_joins_chinese_date_column():
    merged = _sheet_frame(
        ["2026-06-30"],
        pd.DataFrame({"TOTAL_ASSETS": [100.0]}),
    )

    abstract = pd.DataFrame(
        {
            "日期": pd.to_datetime(["2026-06-30"]),
            "净资产收益率": [15.0],
        }
    )

    result = merge_abstract(merged, abstract)

    row = result.loc[result["report_date"] == "2026-06-30"].iloc[0]

    assert row["净资产收益率"] == 15.0
    assert row["TOTAL_ASSETS"] == 100.0


def test_merge_abstract_without_date_column_keeps_merged():
    merged = _sheet_frame(["2026-06-30"])

    result = merge_abstract(merged, pd.DataFrame({"无日期列": [1.0]}))

    assert len(result) == 1


def test_extract_indicators_maps_english_columns():
    frame = pd.DataFrame(
        {
            "report_date": pd.to_datetime(["2026-06-30"]),
            "announce_date": pd.to_datetime(["2026-08-30"]),
            "ROE": ["15.0"],
            "TOTAL_ASSETS": ["100"],
            "OPERATE_INCOME_YOY": ["10.5"],
        }
    )

    output = extract_indicators(frame)

    assert output.loc[0, "roe"] == 15.0
    assert output.loc[0, "total_assets"] == 100.0
    assert output.loc[0, "operate_income_yoy"] == 10.5


def test_extract_indicators_maps_chinese_columns():
    frame = pd.DataFrame(
        {
            "report_date": pd.to_datetime(["2026-06-30"]),
            "announce_date": pd.to_datetime(["2026-08-30"]),
            "净资产收益率": ["15.0"],
            "货币资金": ["123"],
        }
    )

    output = extract_indicators(frame)

    assert output.loc[0, "roe"] == 15.0
    assert output.loc[0, "monetary_funds"] == 123.0


def test_extract_indicators_missing_columns_become_none():
    frame = pd.DataFrame(
        {
            "report_date": pd.to_datetime(["2026-06-30"]),
            "announce_date": pd.to_datetime(["2026-08-30"]),
        }
    )

    output = extract_indicators(frame)

    assert output.loc[0, "roe"] is None
    assert output.loc[0, "netcash_operate"] is None


def test_extract_indicators_empty_frame():
    output = extract_indicators(pd.DataFrame())

    assert set(
        ["report_date", "announce_date"] + sorted(INDICATOR_ALIASES)
    ).issubset(output.columns)
    assert output.empty


def test_merge_abstract_pivot_structure():
    """透视宽表：列名为报告期、行是指标名，需 melt+pivot 对齐"""

    merged = _sheet_frame(
        ["2026-06-30"],
        pd.DataFrame({"TOTAL_ASSETS": [100.0]}),
    )

    abstract = pd.DataFrame(
        {
            "选项": ["常用指标", "常用指标", "每股指标", "每股指标"],
            "指标": [
                "净资产收益率(ROE)",
                "销售净利率",
                "基本每股收益",
                "每股净资产",
            ],
            "20260630": ["15.0", "40.0", "1.5", "10.0"],
            "20251231": ["16.0", "39.0", "1.6", "9.5"],
        }
    )

    result = merge_abstract(merged, abstract)

    # 06-30 行命中摘要指标，12-31 由摘要新增
    # （merge_abstract 不数值化，透视值仍为字符串，数值化由 extract_indicators 完成）
    row = result.loc[result["report_date"] == "2026-06-30"].iloc[0]

    assert float(row["净资产收益率(ROE)"]) == 15.0
    assert float(row["销售净利率"]) == 40.0
    assert float(row["基本每股收益"]) == 1.5
    assert row["TOTAL_ASSETS"] == 100.0

    extra = result.loc[result["report_date"] == "2025-12-31"].iloc[0]

    assert float(extra["净资产收益率(ROE)"]) == 16.0
    assert pd.isna(extra["TOTAL_ASSETS"])


def test_merge_abstract_pivot_without_indicator_keeps_merged():
    """透视结构但无指标列：保持原宽表不变"""

    merged = _sheet_frame(["2026-06-30"])

    abstract = pd.DataFrame(
        {
            "选项": ["x"],
            "20260630": ["1.0"],
        }
    )

    result = merge_abstract(merged, abstract)

    assert len(result) == 1


def test_derive_netcash_total_equivalents():
    """优先“现金及现金等价物”口径派生净增加额"""

    merged = _sheet_frame(
        ["2026-06-30"],
        pd.DataFrame(
            {
                "END_CASH_EQUIVALENTS": [200.0],
                "BEGIN_CASH_EQUIVALENTS": [150.0],
            }
        ),
    )

    result = derive_netcash_total(merged)

    assert result.loc[0, "NETCASH_TOTAL"] == 50.0


def test_derive_netcash_total_cash_fallback():
    """无等价物口径时用 END_CASH - BEGIN_CASH"""

    merged = _sheet_frame(
        ["2026-06-30"],
        pd.DataFrame(
            {
                "END_CASH": [200.0],
                "BEGIN_CASH": [150.0],
            }
        ),
    )

    result = derive_netcash_total(merged)

    assert result.loc[0, "NETCASH_TOTAL"] == 50.0


def test_derive_netcash_total_keeps_existing_column():
    """已有 NETCASH_TOTAL 列时不覆盖"""

    merged = _sheet_frame(
        ["2026-06-30"],
        pd.DataFrame(
            {
                "NETCASH_TOTAL": [888.0],
                "END_CASH": [200.0],
                "BEGIN_CASH": [150.0],
            }
        ),
    )

    result = derive_netcash_total(merged)

    assert result.loc[0, "NETCASH_TOTAL"] == 888.0


def test_derive_netcash_total_union_two_columns():
    """等价物口径缺失时回退 END_CASH 口径，两口径并集填充"""

    merged = _sheet_frame(
        ["2026-06-30", "2026-09-30"],
        pd.DataFrame(
            {
                "END_CASH_EQUIVALENTS": [200.0, None],
                "BEGIN_CASH_EQUIVALENTS": [150.0, None],
                "END_CASH": [None, 500.0],
                "BEGIN_CASH": [None, 460.0],
            }
        ),
    )

    result = derive_netcash_total(merged)

    assert result.loc[0, "NETCASH_TOTAL"] == 50.0
    assert result.loc[1, "NETCASH_TOTAL"] == 40.0


def test_extract_indicators_roe_diluted_new_source():
    """东财摘要加权 ROE 行名为“净资产收益率_平均”"""

    frame = pd.DataFrame(
        {
            "report_date": pd.to_datetime(["2026-06-30"]),
            "announce_date": pd.to_datetime(["2026-08-30"]),
            "净资产收益率_平均": ["16.0"],
        }
    )

    output = extract_indicators(frame)

    assert output.loc[0, "roe_diluted"] == 16.0


def test_extract_indicators_aliases_new_sources():
    """新增候选列名：SALE_EXPENSE / 基本每股收益 / NETCASH_TOTAL"""

    frame = pd.DataFrame(
        {
            "report_date": pd.to_datetime(["2026-06-30"]),
            "announce_date": pd.to_datetime(["2026-08-30"]),
            "SALE_EXPENSE": ["30"],
            "基本每股收益": ["1.5"],
            "NETCASH_TOTAL": ["45"],
        }
    )

    output = extract_indicators(frame)

    assert output.loc[0, "sell_expense"] == 30.0
    assert output.loc[0, "eps"] == 1.5
    assert output.loc[0, "netcash_total"] == 45.0
