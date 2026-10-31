"""只读：北交所覆盖诊断（字典侧 + 数据源侧）"""

import sqlite3

from data.providers.baostock_provider import BaostockProvider

DB = r"D:\cs\python\qt\jj3\database\stockpilot.db"


def main():
    conn = sqlite3.connect(DB)

    print("字典 market 分布：")
    for row in conn.execute(
        "select market, count(*) from stock_reference group by market order by market"
    ):
        print("  ", row)

    print()
    print("北交所代码段分布：")
    for prefix in ("92", "43", "83", "87", "88"):
        count = conn.execute(
            "select count(*) from stock_reference "
            "where market = 'BJ' and code like ?",
            (prefix + "%",),
        ).fetchone()[0]
        print(f"   {prefix}xxx: {count}")

    print()
    print("北交所样本（取字典里真实存在的）：")
    samples = conn.execute(
        "select code, name from stock_reference "
        "where market = 'BJ' order by code limit 8"
    ).fetchall()

    for row in samples:
        print("  ", row)

    conn.close()

    print()
    print("数据源单只查询：")
    provider = BaostockProvider()

    probe = ["920002", "600519", "000001"] + [s[0] for s in samples[:3]]

    for code in probe:
        try:
            info = provider.get_stock_basic(code)
        except Exception as exc:
            info = f"异常: {exc}"

        print(f"   {code} -> {info}")


if __name__ == "__main__":
    main()