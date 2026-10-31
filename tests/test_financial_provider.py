"""财报 provider 归一化纯函数测试（离线，不触网）"""

import pandas as pd

from data.providers.akshare_financial_provider import (
    INDICATOR_ALIASES,
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
