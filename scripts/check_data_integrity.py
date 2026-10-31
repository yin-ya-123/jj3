# -*- coding: utf-8 -*-
"""数据完整性检查入口（阶段 3.4）

用法（项目根目录执行）：
    # 检查自选池全部股票（默认区间 2026-01-01 ~ 今天）
    .venv/Scripts/python.exe scripts/check_data_integrity.py

    # 指定股票与区间
    .venv/Scripts/python.exe scripts/check_data_integrity.py --codes 600519,000001 --start 2026-01-01 --end 2026-10-30

    # 输出 JSON（供脚本/界面消费）
    .venv/Scripts/python.exe scripts/check_data_integrity.py --json

注意：
    只读操作，不写数据库、不联网。
    日历未覆盖区间时输出 calendar_coverage=false，
    可先执行 scripts/sync_daily_bars.py --ensure-calendar 补齐日历。
    验收标准：能报出缺失日与停牌日。
"""

import argparse
import json
import sys
from datetime import date, datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from database.repositories.data_quality_repository import check_data_integrity
from database.repositories.stock_repository import list_stocks


def _fmt_date(value) -> str:
    return value.strftime("%Y-%m-%d")


def main():
    parser = argparse.ArgumentParser(description="数据完整性检查")

    parser.add_argument(
        "--codes",
        default="",
        help="逗号分隔的股票代码，留空则检查自选池全部股票",
    )
    parser.add_argument(
        "--start",
        default="2026-01-01",
        help="开始日期（默认 2026-01-01）",
    )
    parser.add_argument(
        "--end",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="结束日期（默认今天）",
    )
    parser.add_argument(
        "--adjustflag",
        default="3",
        help="复权口径：3=不复权（默认）",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="输出 JSON 结果",
    )

    args = parser.parse_args()

    if args.codes:
        codes = [
            item.strip()[-6:]
            for item in args.codes.split(",")
            if item.strip()
        ]
    else:
        codes = [row["code"] for row in list_stocks(only_active=True)]

    if not codes:
        print("没有可检查的股票")
        return

    results = [
        check_data_integrity(
            code,
            args.start,
            args.end,
            adjustflag=args.adjustflag,
        )
        for code in codes
    ]

    if args.json:
        print(json.dumps(results, ensure_ascii=False, indent=2, default=str))
        return

    total_missing = 0
    total_suspension = 0
    total_unknown = 0
    no_coverage = 0

    for item in results:
        missing = item["missing_days"]
        suspension = item["suspension_days"]
        unknown = item["unknown_status_rows"]

        total_missing += len(missing)
        total_suspension += len(suspension)
        total_unknown += unknown

        if not item["calendar_coverage"]:
            no_coverage += 1

        print(f"\n{item['stock_code']}  "
              f"{item['start_date']} ~ {item['end_date']}  "
              f"adjustflag={item['adjustflag']}")
        print(f"  交易日 {item['trading_days']} 天，"
              f"库内 {item['bar_count']} 行")

        if not item["calendar_coverage"]:
            print("  日历未覆盖该区间，缺失列表无法计算"
                  "（可先跑 --ensure-calendar）")

        if missing:
            print(f"  缺失交易日 {len(missing)} 天："
                  f"{', '.join(_fmt_date(d) for d in missing[:10])}"
                  f"{' ...' if len(missing) > 10 else ''}")
        else:
            print("  缺失交易日：无")

        if suspension:
            print(f"  停牌日 {len(suspension)} 天："
                  f"{', '.join(_fmt_date(d) for d in suspension[:10])}"
                  f"{' ...' if len(suspension) > 10 else ''}")
        else:
            print("  停牌日：无")

        if unknown:
            print(f"  注意：{unknown} 行 trade_status 为 NULL"
                  "（3.4 前存量，重采后可回填）")

    print("\n========== 检查汇总 ==========")
    print(f"股票总数：{len(results)}")
    print(f"缺失交易日合计：{total_missing}")
    print(f"停牌日合计：{total_suspension}")
    print(f"trade_status 未知行合计：{total_unknown}")
    if no_coverage:
        print(f"日历未覆盖的股票：{no_coverage}")
    print(f"完成时间：{datetime.now()}")


if __name__ == "__main__":
    main()
