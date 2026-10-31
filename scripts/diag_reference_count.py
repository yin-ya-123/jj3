"""诊断：全市场字典条数差异根因（只读，不写数据库）

用法：
    .venv\\Scripts\\python.exe scripts\\diag_reference_count.py
"""

from collections import Counter

import baostock as bs

DAY = "2026-10-30"


def fetch_rows(day: str) -> list[dict]:
    """原样取回 Baostock 全市场列表（保留 sh./sz./bj. 前缀）"""

    lg = bs.login()
    assert lg.error_code == "0", lg.error_msg

    try:
        rs = bs.query_all_stock(day=day)
        assert rs.error_code == "0", rs.error_msg

        fields = list(rs.fields)
        rows = []

        while rs.next():
            rows.append(dict(zip(fields, rs.get_row_data())))

        return rows
    finally:
        bs.logout()


def main():
    rows = fetch_rows(DAY)

    if not rows:
        print("当天没有数据")
        return

    print("字段:", list(rows[0].keys()))
    print("原始行数:", len(rows))

    def bare(code: str) -> str:
        """剥掉市场前缀后的 6 位代码"""

        return str(code).split(".")[-1]

    def prefix(code: str) -> str:
        return str(code).split(".")[0]

    codes = Counter(bare(row["code"]) for row in rows)
    dups = {code: n for code, n in codes.items() if n > 1}

    print("去重后代码数:", len(codes))
    print("重复代码个数:", len(dups))

    print("\n---- 重复代码明细 ----")
    for code in sorted(dups):
        group = [
            (row["code"], row.get("code_name"), row.get("tradeStatus"))
            for row in rows
            if bare(row["code"]) == code
        ]
        print(f"{code} x{dups[code]} -> {group}")

    print("\n---- 市场前缀分布 ----")
    print(dict(Counter(prefix(row["code"]) for row in rows)))

    print("\n---- 名称关键字统计 ----")
    keywords = Counter()

    for row in rows:
        name = str(row.get("code_name") or "")

        if "指数" in name:
            keywords["含指数"] += 1
        if "ETF" in name.upper():
            keywords["含ETF"] += 1
        if "LOF" in name.upper():
            keywords["含LOF"] += 1
        if "债" in name:
            keywords["含债"] += 1
        if "基金" in name:
            keywords["含基金"] += 1

    print(dict(keywords))


if __name__ == "__main__":
    main()