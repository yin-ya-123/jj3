# -*- coding: utf-8 -*-
"""财报采集入口（阶段 5.1，命令行）

用法（项目根目录，路径用正斜杠）：
    # 同步自选池全部股票的财报（全量，UPSERT 幂等，可重复跑）
    .venv/Scripts/python.exe scripts/sync_financial_reports.py

    # 只同步指定股票
    .venv/Scripts/python.exe scripts/sync_financial_reports.py --codes 600519,000001

    # 增量（只拉库内最新报告期之后的数据）
    .venv/Scripts/python.exe scripts/sync_financial_reports.py --incremental

注意：
    会写正式数据库（financial_reports 表）。
    每只股票要发 4 次网络请求（三表 + 摘要），全市场采集很慢，
    建议放后台跑或者分批跑。
    全量模式会刷新已入库报告期（财报修订场景）；增量模式只追加新报告期。
"""

import argparse
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.stdout.reconfigure(encoding="utf-8")

from data.collectors.financial_collector import (
    FULL_END_DATE,
    FULL_START_DATE,
    FinancialCollector,
)
from database.repositories.stock_repository import list_stocks


def main():
    parser = argparse.ArgumentParser(description="财报采集")

    parser.add_argument(
        "--codes",
        default="",
        help="逗号分隔的股票代码，留空则同步自选池全部股票",
    )
    parser.add_argument(
        "--start",
        default=FULL_START_DATE,
        help=f"开始报告期（YYYYMMDD，默认 {FULL_START_DATE}）",
    )
    parser.add_argument(
        "--end",
        default=FULL_END_DATE,
        help=f"结束报告期（YYYYMMDD，默认 {FULL_END_DATE}）",
    )
    parser.add_argument(
        "--incremental",
        action="store_true",
        help="增量同步：只拉库内最新报告期之后的数据",
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
    print(f"报告期区间：{args.start} ~ {args.end}")
    print(f"模式：{'增量' if args.incremental else '全量'}")

    collector = FinancialCollector()

    results = collector.sync_stocks(
        symbols=codes,
        start_date=args.start,
        end_date=args.end,
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
