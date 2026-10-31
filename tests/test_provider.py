
from data.providers.baostock_provider import BaostockProvider


def test_baostock_provider():
    provider = BaostockProvider()

    df = provider.get_daily_history(
        symbol="600519",
        start_date="2026-01-01",
        end_date="2026-10-30",
        adjustflag="2",
    )

    assert df is not None
    assert not df.empty

    required_columns = {
        "date",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    }

    assert required_columns.issubset(df.columns)

    print("\n贵州茅台历史行情测试成功")
    print(df.tail(5).to_string(index=False))
