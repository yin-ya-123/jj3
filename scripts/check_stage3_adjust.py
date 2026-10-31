# -*- coding: utf-8 -*-
"""阶段 3 · 复权因子与换算口径验收

会写正式库（adjust_factors 表），必须由用户手动执行。

用法（项目根目录）：
    .venv\\Scripts\\python.exe scripts\\check_stage3_adjust.py
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from data.providers.baostock_provider import BaostockProvider

from data.adjustment import apply_adjust, latest_back_factor

from database.repositories.adjust_factor_repository import (
    get_adjust_factor_frame,
    save_adjust_factors,
)


CODE = "600519"


def main():
    provider = BaostockProvider()

    print("=" * 60)
    print("[1] 拉取复权因子")
    factors = provider.get_adjust_factors(
        symbol=CODE,
        start_date="2001-01-01",
        end_date="2026-10-30",
    )
    print(f"    事件行数：{len(factors)}")
    if not factors.empty:
        print(f"    首行：{factors.iloc[0].to_dict()}")
        print(f"    末行：{factors.iloc[-1].to_dict()}")

    print("=" * 60)
    print("[2] 写入 adjust_factors 表")
    written = save_adjust_factors(factors, CODE)
    print(f"    写入 {written} 条")

    print("=" * 60)
    print("[3] 读回校验")
    frame = get_adjust_factor_frame(CODE)
    print(f"    读回 {len(frame)} 行")
    if not frame.empty:
        print(f"    末行：{frame.iloc[-1].to_dict()}")
    print(f"    最新后复权因子：{latest_back_factor(frame)}")

    print("=" * 60)
    print("[4] 本地换算前复权价 vs Baostock adjustflag=2")
    raw = provider.get_daily_history(
        symbol=CODE,
        start_date="2026-01-01",
        end_date="2026-10-30",
        adjustflag="3",
    )
    remote = provider.get_daily_history(
        symbol=CODE,
        start_date="2026-01-01",
        end_date="2026-10-30",
        adjustflag="2",
    )

    if raw.empty or remote.empty:
        print("    行情为空，跳过")
        return

    local = apply_adjust(raw, frame, mode="qfq")

    compare = local[["date", "close"]].merge(
        remote[["date", "close"]],
        on="date",
        suffixes=("_local", "_remote"),
    )

    compare["diff"] = (
        compare["close_local"] - compare["close_remote"]
    ).abs()

    print(f"    比对 {len(compare)} 个交易日")
    print(f"    最大误差：{compare['diff'].max():.10f}")
    print(f"    误差超 1e-6 的天数：{(compare['diff'] > 1e-6).sum()}")

    if not compare.empty:
        print("    样本：")
        for _, row in compare.head(3).iterrows():
            print(
                f"      {row['date'].date()} "
                f"local={row['close_local']} "
                f"remote={row['close_remote']} "
                f"diff={row['diff']:.10f}"
            )

    print("=" * 60)
    print("[5] 与库里已有的前复权数据对比（600519）")
    import sqlite3

    conn = sqlite3.connect("../database/stockpilot.db")
    stored = dict(
        conn.execute(
            "select trade_date, close from daily_bars "
            "where stock_code='600519' and adjustflag='2'"
        ).fetchall()
    )
    conn.close()

    mismatch = 0
    checked = 0

    for _, row in compare.iterrows():
        key = row["date"].strftime("%Y-%m-%d")

        if key in stored:
            checked += 1

            if abs(stored[key] - row["close_local"]) > 1e-6:
                mismatch += 1

    print(f"    库内可比对 {checked} 天，不一致 {mismatch} 天")

    print("=" * 60)
    print("完成")


if __name__ == "__main__":
    main()
