"""验证股票基础信息查询（只读，不写库）"""

from data.providers.baostock_provider import BaostockProvider


def main():
    provider = BaostockProvider()

    for code in ["920002", "600519", "000001"]:
        try:
            info = provider.get_stock_basic(code)
        except Exception as exc:
            info = f"异常: {exc}"

        print(code, "->", info)


if __name__ == "__main__":
    main()