"""只读：查看 stocks 表当前内容，定位批量导入的已存在项"""

import sqlite3

DB = r"D:\cs\python\qt\jj3\database\stockpilot.db"

conn = sqlite3.connect(DB)

print("stocks 表全部内容：")
for row in conn.execute(
    "select code, name, market, is_active, created_at from stocks order by code"
):
    print("  ", row)

print()
print("字典里这 3 个代码：")
for row in conn.execute(
    "select code, name, market, trade_status from stock_reference "
    "where code in ('000001', '000002', '600519') order by code"
):
    print("  ", row)

print()
print("日线条数（应仍为 594）：", conn.execute("select count(*) from daily_bars").fetchone()[0])
print("字典条数（应仍为 5564）：", conn.execute("select count(*) from stock_reference").fetchone()[0])

conn.close()