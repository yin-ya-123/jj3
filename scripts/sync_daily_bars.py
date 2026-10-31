# -*- coding: utf-8 -*-
"""行情采集入口（命令行，日线 + 分钟线）

用法（项目根目录，路径用正斜杠）：
    # 同步自选池全部股票（日线）
    .venv/Scripts/python.exe scripts/sync_daily_bars.py --start 2026-01-01 --end 2026-10-30

    # 只同步指定股票
    .venv/Scripts/python.exe scripts/sync_daily_bars.py --codes 600519,000001

    # 只补最近区间（增量：从库内最新交易日的次日开始拉）
    .venv/Scripts/python.exe scripts/sync_daily_bars.py --start 2026-10-01 --incremental

    # 增量 + 自动保障交易日历（日历覆盖到结束日，推荐增量时带上）
    .venv/Scripts/python.exe scripts/sync_daily_bars.py --incremental --ensure-calendar

    # 同步 5 分钟线
    .venv/Scripts/python.exe scripts/sync_daily_bars.py --period 5 --start 2026-01-01

注意：
    会写正式数据库。
    每只股票要发两次网络请求（因子 + 行情），全市场采集很慢，
    建议放后台跑或者分批跑。
    分钟线最早约 2020-01-02。
    增量同步只支持日线（分钟线请给完整区间重采）。
"""

import argparse
import sys
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from data.collectors.daily_collector import PERIOD_NAMES, STORED_PERIODS, DailyCollector
from database.repositories.stock_repository import list_stocks
from database.repositories.trading_calendar_repository import (
    get_max_calendar_date,
)


def ensure_calendar_cover(collector: DailyCollector, end_date: str) -> str:
    """保证交易日历覆盖到 end_date，返回说明"""

    max_date = get_max_calendar_date()
    end_key = str(end_date).strip().replace("-", "")

    if max_date is not None:
        if max_date.strftime("%Y%m%d") >= end_key:
            print(f"交易日历已覆盖至 {max_date:%Y-%m-%d}，无需同步")
            return "已覆盖"

        start = (max_date + timedelta(days=1)).strftime("%Y-%m-%d")

        print(f"交易日历最大 {max_date:%Y-%m-%d}，补齐 {start} ~ {end_date}")
        collector.sync_calendar(start, end_date)

        return "已补齐"
    else:
        print("交易日历表为空，同步 1990-01-01 起完整区间")
        collector.sync_calendar("1990-01-01", end_date)

        return "已初始化"


def main():
    parser = argparse.ArgumentParser(description="行情采集")

    parser.add_argument(
        "--codes",
        default="",
        help="逗号分隔的股票代码，留空则同步自选池全部股票",
    )
    parser.add_argument("--start", default="2026-01-01", help="开始日期")
    parser.add_argument(
        "--end",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="结束日期",
    )
    parser.add_argument(
        "--period",
        default="d",
        choices=STORED_PERIODS,
        help="采集周期：d=日线 5/15/30/60=分钟线（默认 d）",
    )
    parser.add_argument(
        "--adjustflag",
        default="3",
        help="复权口径：3=不复权（默认） 2=前复权 1=后复权",
    )
    parser.add_argument(
        "--no-factors",
        action="store_true",
        help="跳过复权因子同步（因子已同步过时可用）",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="增量同步：从库内最新交易日的次日开始拉（仅日线）",
    )
    parser.add_argument(
        "--ensure-calendar",
        action="store_true",
        help="同步前自动把交易日历补齐到结束日（增量模式推荐开启）",
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
        print("没有可同步的股票")
        return

    print(f"待同步 {len(codes)} 只")
    print(f"代码：{', '.join(codes[:10])}")
    if len(codes) > 10:
        print(f"      ... 共 {len(codes)} 只")
    print(f"区间：{args.start} ~ {args.end}")
    print(f"周期：{PERIOD_NAMES.get(args.period, args.period)}")
    print(f"复权口径：adjustflag={args.adjustflag}")
    print(f"模式：{'增量' if args.incremental else '全量'}")

    collector = DailyCollector()

    if args.ensure_calendar:
        ensure_calendar_cover(collector, args.end)

    results = collector.sync_stocks(
        symbols=codes,
        start_date=args.start,
        end_date=args.end,
        adjustflag=args.adjustflag,
        period=args.period,
        with_factors=not args.no_factors,
        incremental=args.incremental,
    )

    success = sum(
        1 for item in results
        if item["status"] == "success"
    )

    skipped = sum(
        1 for item in results
        if item["status"] == "skipped"
    )

    failed = len(results) - success - skipped

    print()
    print(f"完成：成功 {success}，跳过 {skipped}，失败 {failed}")


if __name__ == "__main__":
    main()
