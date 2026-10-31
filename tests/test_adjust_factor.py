"""复权换算离线测试（不联网、不写正式库）"""

import pandas as pd
import pytest

from data.adjustment import (
    apply_adjust,
    build_back_factor,
    latest_back_factor,
)


FACTORS = pd.DataFrame(
    {
        "divid_operate_date": pd.to_datetime(
            ["2020-01-01", "2021-01-01", "2022-01-01"]
        ),
        "back_adjust_factor": [1.0, 2.0, 4.0],
        "fore_adjust_factor": [0.25, 0.5, 1.0],
    }
)


def make_bars():
    return pd.DataFrame(
        {
            "date": pd.to_datetime(
                ["2019-12-31", "2020-06-01", "2021-06-01", "2022-06-01"]
            ),
            "open": [10.0, 20.0, 20.0, 40.0],
            "close": [10.0, 20.0, 20.0, 40.0],
        }
    )


def test_latest_back_factor():
    assert latest_back_factor(FACTORS) == 4.0


def test_latest_back_factor_empty():
    assert latest_back_factor(pd.DataFrame()) == 1.0


def test_build_back_factor_is_stepwise():
    dates = make_bars()["date"]

    result = build_back_factor(dates, FACTORS)

    # 早于第一个除权日 → 1.0
    assert result.iloc[0] == 1.0
    assert result.iloc[1] == 1.0
    assert result.iloc[2] == 2.0
    assert result.iloc[3] == 4.0


def test_build_back_factor_handles_unsorted_dates():
    dates = pd.Series(pd.to_datetime(["2022-06-01", "2020-06-01"]))

    result = build_back_factor(dates, FACTORS)

    assert list(result) == [4.0, 1.0]


def test_build_back_factor_without_factors():
    dates = make_bars()["date"]

    result = build_back_factor(dates, pd.DataFrame())

    assert list(result) == [1.0, 1.0, 1.0, 1.0]


def test_apply_adjust_hfq():
    result = apply_adjust(make_bars(), FACTORS, mode="hfq")

    assert list(result["close"]) == [10.0, 20.0, 40.0, 160.0]


def test_apply_adjust_qfq():
    result = apply_adjust(make_bars(), FACTORS, mode="qfq")

    assert list(result["close"]) == [2.5, 5.0, 10.0, 40.0]


def test_apply_adjust_none_keeps_price():
    result = apply_adjust(make_bars(), FACTORS, mode="none")

    assert list(result["close"]) == [10.0, 20.0, 20.0, 40.0]


def test_apply_adjust_rejects_unknown_mode():
    with pytest.raises(ValueError):
        apply_adjust(make_bars(), FACTORS, mode="xxx")


def test_apply_adjust_empty_frame():
    empty = pd.DataFrame()

    result = apply_adjust(empty, FACTORS, mode="qfq")

    assert result.empty


def test_apply_adjust_records_multiplier():
    result = apply_adjust(make_bars(), FACTORS, mode="qfq")

    assert list(result["adjust_factor"]) == [0.25, 0.25, 0.5, 1.0]


def test_apply_adjust_qfq_rounds_to_six_decimals():
    """Baostock 前复权因子只有 6 位小数，本地同样舍入才能逐位对齐"""

    factors = pd.DataFrame(
        {
            "divid_operate_date": pd.to_datetime(
                ["2020-01-01", "2021-01-01"]
            ),
            "back_adjust_factor": [1.0, 3.0],
            "fore_adjust_factor": [0.333333, 1.0],
        }
    )

    bars = pd.DataFrame(
        {
            "date": pd.to_datetime(["2020-06-01", "2021-06-01"]),
            "close": [10.0, 10.0],
        }
    )

    result = apply_adjust(bars, factors, mode="qfq")

    assert list(result["adjust_factor"]) == [0.333333, 1.0]
    assert list(result["close"]) == [3.33333, 10.0]
