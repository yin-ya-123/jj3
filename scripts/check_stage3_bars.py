"""阶段 3 验收脚本：多周期行情链路（provider -> bars 表）

注意：本脚本会写入正式数据库 stockpilot.db，请手动执行

用法：
    .venv\\Scripts\\python.exe scripts\\check_stage3_bars.py
"""

import sys

from database.db import DATABASE_PATH
from database.repositories import bar_repository as repo
from data.providers.baostock_provider import BaostockProvider

sys.stdout.reconfigure(encoding="utf-8")

SYMBOL = "600519"
DAY = "2026-10-30"


def main():
    print(f"数据库：{DATABASE_PATH}")

    provider = BaostockProvider()

    print("\n[1] 拉 5 分钟线")
    df = provider.get_period_history(
        symbol=SYMBOL,
        period="5",
        start_date=DAY,
        end_date=DAY,
        adjustflag="3",
    )

    print(f"    行数={len(df)}")
    print(f"    列={list(df.columns)}")

    if df.empty:
        raise SystemExit("没有拿到数据，终止")

    print(f"    首行 trade_time={df.iloc[0]['trade_time']}")
    print(f"    末行 trade_time={df.iloc[-1]['trade_time']}")

    print("\n[2] 写入 bars 表")
    count = repo.save_bars(df, SYMBOL, "5", adjustflag="3")
    print(f"    写入 {count} 条")

    print("\n[3] 读回验证")
    bars = repo.get_bars(SYMBOL, period="5", limit=5)
    print(f"    读回 {len(bars)} 条")

    for bar in bars[:3]:
        print(
            f"    {bar.trade_time}  O={bar.open} H={bar.high} "
            f"L={bar.low} C={bar.close} V={bar.volume}"
        )

    print("\n[4] 重复写入不产生重复行")
    repo.save_bars(df, SYMBOL, "5", adjustflag="3")
    total = repo.get_bars(SYMBOL, period="5", limit=10000)
    print(f"    当前该股 5 分钟线总条数={len(total)}")
    print(f"    （{DAY} 单日应为 48 条）")


if __name__ == "__main__":
    main()
