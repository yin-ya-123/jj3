"""市场判定规则测试（离线）"""

import pytest

from data.providers.baostock_provider import BaostockProvider
from data.utils import market_of, normalize_code


@pytest.mark.parametrize(
    "code,expected",
    [
        ("600519", "SH"),   # 沪市主板
        ("688981", "SH"),   # 科创板
        ("900901", "SH"),   # 沪市 B 股
        ("000001", "SZ"),   # 深市主板
        ("300750", "SZ"),   # 创业板
        ("920002", "BJ"),   # 北交所新代码段
        ("430047", "BJ"),   # 北交所老代码段
        ("830799", "BJ"),
        ("sh.600519", "SH"),
        ("bj.920002", "BJ"),
    ],
)
def test_market_of(code, expected):
    assert market_of(code) == expected


def test_market_of_rejects_non_stock_prefix():
    with pytest.raises(ValueError):
        market_of("700001")


def test_normalize_code_builds_baostock_symbol():
    provider = BaostockProvider()

    assert provider.normalize_code("600519") == "sh.600519"
    assert provider.normalize_code("000001") == "sz.000001"
    assert provider.normalize_code("920002") == "bj.920002"
    assert provider.normalize_code("sh.600519") == "sh.600519"


def test_normalize_code_rejects_unsupported():
    provider = BaostockProvider()

    with pytest.raises(ValueError):
        provider.normalize_code("700001")


def test_normalize_code_rejects_bad_input():
    with pytest.raises(ValueError):
        normalize_code("abc")