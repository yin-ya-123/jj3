
from datetime import datetime

from database.db import SessionLocal
from database.models import DataSyncLog

from database.repositories.daily_bar_repository import save_daily_bars
from data.providers.baostock_provider import BaostockProvider


class DailyCollector:
    """A股历史日线采集服务"""

    def __init__(self):
        self.provider = BaostockProvider()

    def sync_stock(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjustflag: str = "2",
    ):
        code = str(symbol).strip()[-6:]

        print(f"\n开始同步 {code}")

        record_count = 0
        status = "success"
        message = "同步成功"

        try:
            df = self.provider.get_daily_history(
                symbol=code,
                start_date=start_date,
                end_date=end_date,
                adjustflag=adjustflag,
            )

            record_count = save_daily_bars(
                df=df,
                symbol=code,
                adjustflag=adjustflag,
            )

            print(f"{code} 同步成功，处理记录：{record_count}")

        except Exception as exc:
            status = "failed"
            message = str(exc)[:500]

            print(f"{code} 同步失败：{message}")

        finally:
            with SessionLocal.begin() as session:
                session.add(
                    DataSyncLog(
                        stock_code=code,
                        start_date=start_date,
                        end_date=end_date,
                        record_count=record_count,
                        status=status,
                        message=message,
                    )
                )

        return {
            "stock_code": code,
            "status": status,
            "record_count": record_count,
            "message": message,
        }

    def sync_stocks(
        self,
        symbols: list,
        start_date: str,
        end_date: str,
        adjustflag: str = "2",
    ):
        """批量同步股票"""

        results = []

        for symbol in symbols:
            result = self.sync_stock(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                adjustflag=adjustflag,
            )

            results.append(result)

        success_count = sum(
            1 for item in results
            if item["status"] == "success"
        )

        failed_count = len(results) - success_count

        print("\n========== 同步汇总 ==========")
        print(f"股票总数：{len(results)}")
        print(f"成功数量：{success_count}")
        print(f"失败数量：{failed_count}")
        print(f"完成时间：{datetime.now()}")

        return results
