"""行情采集服务：日线 + 分钟线

口径：
    库存不复权原始价（adjustflag=3），复权在计算层做（data/adjustment.py）。
    每只股票先同步复权因子再采行情；因子同步失败就中止，
    避免存下算不出复权价的半成品数据。

存储位置：
    日线 -> daily_bars；分钟线 -> bars；周线/月线不入库，由日线聚合。

增量同步：
    incremental=True 时按库里每只股票已有的最新交易日往后拉，
    而不是每次从 start_date 全量重采。
    因为库存是不复权原始价，除权不会改写历史价，增量追加是安全的。
"""

from datetime import datetime, timedelta

from database.db import SessionLocal
from database.models import DataSyncLog

from database.repositories.adjust_factor_repository import save_adjust_factors
from database.repositories.bar_repository import save_bars
from database.repositories.daily_bar_repository import (
    get_latest_trade_date,
    save_daily_bars,
)
from database.repositories.trading_calendar_repository import (
    has_trading_day,
    save_trade_dates,
)
from data.providers.baostock_provider import BaostockProvider


# 复权因子是「事件表」，后复权因子自上市以来累积，
# 区间取得太窄会漏掉早期除权事件，换算出来的复权价就是错的
FACTOR_START_DATE = "1990-01-01"

DAILY_PERIOD = "d"
MINUTE_PERIODS = ("5", "15", "30", "60")
STORED_PERIODS = (DAILY_PERIOD,) + MINUTE_PERIODS

PERIOD_NAMES = {
    "d": "日线",
    "5": "5分钟",
    "15": "15分钟",
    "30": "30分钟",
    "60": "60分钟",
}


class DailyCollector:
    """行情采集服务（日线 / 分钟线）"""

    def __init__(self):
        self.provider = BaostockProvider()

    def sync_factors(self, code: str, end_date: str) -> int:
        """同步复权因子，返回写入条数"""

        df = self.provider.get_adjust_factors(
            symbol=code,
            start_date=FACTOR_START_DATE,
            end_date=end_date,
        )

        return save_adjust_factors(df, code)

    def sync_calendar(self, start_date: str, end_date: str) -> dict:
        """同步交易日历，返回统计"""

        df = self.provider.get_trade_dates(
            start_date=start_date,
            end_date=end_date,
        )

        total = save_trade_dates(df)

        trading_days = int(df["is_trading_day"].sum()) if not df.empty else 0

        print(
            f"交易日历同步完成：{start_date}~{end_date} "
            f"共 {total} 天，其中交易日 {trading_days} 天"
        )

        return {
            "start_date": start_date,
            "end_date": end_date,
            "total_days": total,
            "trading_days": trading_days,
        }

    def _resolve_incremental_range(
        self,
        code: str,
        start_date: str,
        end_date: str,
        adjustflag: str,
        period: str,
    ):
        """算增量同步的实际起点

        返回 (实际起点, 跳过原因)；跳过原因为 None 表示要拉。
        """

        if period != DAILY_PERIOD:
            raise ValueError("增量同步目前仅支持日线")

        # 日期有两种写法（20261029 / 2026-10-29），混着比大小会算错，
        # 统一成不带横杠的再比
        start_key = str(start_date).strip().replace("-", "")
        end_key = str(end_date).strip().replace("-", "")

        latest = get_latest_trade_date(code, adjustflag)

        if latest is not None:
            next_day = (latest + timedelta(days=1)).strftime("%Y%m%d")

            if next_day > start_key:
                start_key = next_day

                print(
                    f"{code} 库内最新交易日 {latest:%Y-%m-%d}，"
                    f"增量从 {next_day} 开始拉"
                )

        if start_key > end_key:
            return start_key, f"已是最新，无需同步（结束日 {end_date}）"

        if not has_trading_day(start_key, end_key):
            return start_key, (
                f"{start_date}~{end_date} 区间内无交易日（日历已知），跳过"
            )

        return start_key, None

    def sync_stock(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjustflag: str = "3",
        period: str = DAILY_PERIOD,
        with_factors: bool = True,
        incremental: bool = False,
    ):
        code = str(symbol).strip()[-6:]
        period = str(period).strip().lower()

        record_count = 0
        status = "success"
        message = "同步成功"

        print(f"\n开始同步 {code} {PERIOD_NAMES.get(period, period)}")

        try:
            if period not in STORED_PERIODS:
                raise ValueError(
                    f"不支持入库的周期: {period}"
                    "（周线/月线不入库，由日线聚合）"
                )

            skip_message = None

            if incremental:
                start_date, skip_message = self._resolve_incremental_range(
                    code=code,
                    start_date=start_date,
                    end_date=end_date,
                    adjustflag=adjustflag,
                    period=period,
                )

            if skip_message is not None:
                status = "skipped"
                message = skip_message

                print(f"{code} 跳过：{message}")

            else:
                if with_factors:
                    # 因子先同步：失败就中止，否则会存下算不出复权价的原始价
                    try:
                        factor_count = self.sync_factors(code, end_date)
                    except Exception as exc:
                        raise RuntimeError(
                            f"复权因子同步失败: {exc}"
                        ) from exc

                    print(f"{code} 复权因子写入 {factor_count} 条")

                if period == DAILY_PERIOD:
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
                else:
                    df = self.provider.get_period_history(
                        symbol=code,
                        period=period,
                        start_date=start_date,
                        end_date=end_date,
                        adjustflag=adjustflag,
                    )

                    record_count = save_bars(
                        df=df,
                        symbol=code,
                        period=period,
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
                        period=period,
                        adjustflag=str(adjustflag),
                        record_count=record_count,
                        status=status,
                        message=message,
                    )
                )

        return {
            "stock_code": code,
            "period": period,
            "adjustflag": str(adjustflag),
            "status": status,
            "record_count": record_count,
            "message": message,
        }

    def sync_stocks(
        self,
        symbols: list,
        start_date: str,
        end_date: str,
        adjustflag: str = "3",
        period: str = DAILY_PERIOD,
        with_factors: bool = True,
        incremental: bool = False,
    ):
        """批量同步股票"""

        results = []

        for symbol in symbols:
            result = self.sync_stock(
                symbol=symbol,
                start_date=start_date,
                end_date=end_date,
                adjustflag=adjustflag,
                period=period,
                with_factors=with_factors,
                incremental=incremental,
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

        print("\n========== 同步汇总 ==========")
        print(f"股票总数：{len(results)}")
        print(f"成功数量：{success_count}")
        print(f"跳过数量：{skipped_count}")
        print(f"失败数量：{failed_count}")
        print(f"完成时间：{datetime.now()}")

        return results
