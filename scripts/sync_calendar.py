# -*- coding: utf-8 -*-
"""交易日历同步入口（命令行）

用法（项目根目录，路径用正斜杠）：
    # 同步 2020 年至今的交易日历
    .venv/Scripts/python.exe scripts/sync_calendar.py

    # 一次铺满到年底
    .venv/Scripts/python.exe scripts/sync_calendar.py --start 2020-01-01 --end 2026-12-31

注意：
    会写正式数据库的 trading_calendar 表（按主键覆盖，可重复执行）。
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from data.collectors.daily_collector import DailyCollector


def main():
    parser = argparse.ArgumentParser(description="交易日历同步")

    parser.add_argument("--start", default="2020-01-01", help="开始日期")
    parser.add_argument(
        "--end",
        default=datetime.now().strftime("%Y-%m-%d"),
        help="结束日期",
    )

    args = parser.parse_args()

    DailyCollector().sync_calendar(args.start, args.end)


if __name__ == "__main__":
    main()
