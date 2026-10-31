"""验证 Baostock query_stock_basic() 全量取数是否可用（只读，不写库）"""

import time
from collections import Counter

import baostock as bs


def main():
    t0 = time.time()
    lg = bs.login()
    assert lg.error_code == "0", lg.error_msg
    try:
        rs = bs.query_stock_basic()
        print("error_code:", rs.error_code, rs.error_msg)
        fields = list(rs.fields)
        print("字段:", fields)

        rows = []
        while rs.next():
            rows.append(dict(zip(fields, rs.get_row_data())))

        print("总行数:", len(rows), f"耗时 {time.time() - t0:.1f}s")
        print("type 分布:", dict(Counter(r.get("type") for r in rows)))
        print("status 分布:", dict(Counter(r.get("status") for r in rows)))

        stocks = [r for r in rows if r.get("type") == "1"]
        print("股票行数:", len(stocks))

        def bare(code):
            return str(code).split(".")[-1]

        codes = Counter(bare(r["code"]) for r in stocks)
        dups = {c: n for c, n in codes.items() if n > 1}
        print("股票重复代码数:", len(dups))
        for c in sorted(dups)[:10]:
            print(
                "  重复:",
                c,
                [(r["code"], r.get("code_name"), r.get("status"))
                 for r in stocks if bare(r["code"]) == c],
            )

        print("前缀分布:", dict(Counter(str(r["code"]).split(".")[0] for r in stocks)))
        print("样本:", stocks[:3])
    finally:
        bs.logout()


if __name__ == "__main__":
    main()