"""财报采集服务（阶段 5.1）

数据源：akshare 东方财富三表 + 财务摘要（data/providers/akshare_financial_provider.py）。
入库：financial_reports 宽表，UNIQUE(stock_code, report_date)，
      报告期 report_date 与披露日期 announce_date 双字段，UPSERT 幂等。

增量同步：
    incremental=True 时以库内最新报告期为界，只拉该报告期之后的数据
    （东财接口 start_date 按报告期筛选）。
    注意：财报修订会改写同一报告期内容，增量模式不重拉已入库报告期，
    如需刷新旧报告期请用全量模式（UPSERT 会更新）。
"""

from datetime import timedelta

from data.providers.akshare_financial_provider import AkshareFinancialProvider
from database.repositories.financial_report_repository import (
    get_latest_report_date,
    save_financial_reports,
)

FULL_START_DATE = "19900101"
FULL_END_DATE = "20500101"


class FinancialCollector:
    """财报采集服务"""

    def __init__(self):
        self.provider = AkshareFinancialProvider()

    def _resolve_incremental_start(
        self,
        code: str,
        start_date: str,
    ) -> str:
        """算增量同步的实际起点（库内最新报告期的次日）"""

        latest = get_latest_report_date(code)

        if latest is None:
            return start_date

        next_day = (latest + timedelta(days=1)).strftime("%Y%m%d")
        start_key = str(start_date).strip().replace("-", "")

        if next_day > start_key:
            return next_day

        return start_date

    def sync_stock(
        self,
        symbol: str,
        start_date: str = FULL_START_DATE,
        end_date: str = FULL_END_DATE,
        incremental: bool = False,
    ) -> dict:
        """同步单只股票财报，返回统计

        不写行情同步日志（data_sync_logs 语义是行情），
        财报同步结果直接由返回值与 CLI 打印呈现。
        """

        code = str(symbol).strip()[-6:]

        if incremental:
            start_date = self._resolve_incremental_start(code, start_date)

        try:
            df = self.provider.get_financial_reports(
                symbol=code,
                start_date=start_date,
                end_date=end_date,
            )

            record_count = save_financial_reports(df, code)

            if record_count:
                status = "success"
                message = f"写入 {record_count} 条"
            else:
                status = "skipped"
                message = "无新数据"

        except Exception as exc:
            status = "failed"
            record_count = 0
            message = str(exc)[:500]

        return {
            "stock_code": code,
            "status": status,
            "record_count": record_count,
            "message": message,
        }

    def sync_stocks(
        self,
        symbols: list,
        start_date: str = FULL_START_DATE,
        end_date: str = FULL_END_DATE,
        incremental: bool = False,
    ) -> list:
        """批量同步股票财报"""

        results = []

        for symbol in symbols:
            result = self.sync_stock(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                incremental=incremental,
            )

            print(
                f"{result['stock_code']} {result['status']}："
                f"{result['message']}"
            )

            results.append(result)

        success_count = sum(
            1 for item in results
            if item["status"] == "success"
        )
        skipped_count = sum(
            1 for item in results
            if item["status"] == "skipped"
        )
        failed_count = len(results) - success_count - skipped_count

        print("\n========== 财报同步汇总 ==========")
        print(f"股票总数：{len(results)}")
        print(f"成功数量：{success_count}")
        print(f"跳过数量：{skipped_count}")
        print(f"失败数量：{failed_count}")

        return results
