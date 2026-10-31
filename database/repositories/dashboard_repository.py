"""工作台统计数据：跨股票、行情、同步日志的汇总查询"""

from sqlalchemy import desc, func, select

from database.db import SessionLocal
from database.models import DailyBar, DataSyncLog, Stock


def get_dashboard_data() -> dict:
    """读取工作台需要的统计信息"""

    with SessionLocal() as session:
        stock_count = session.scalar(
            select(func.count(Stock.code))
            .where(Stock.is_active == 1)
        ) or 0

        total_bars = session.scalar(
            select(func.count(DailyBar.id))
        ) or 0

        # 项目口径：库存存不复权原始价（adjustflag=3），复权在计算层做
        raw_bars = session.scalar(
            select(func.count(DailyBar.id))
            .where(DailyBar.adjustflag == "3")
        ) or 0

        latest_trade_date = session.scalar(
            select(func.max(DailyBar.trade_date))
        )

        # 已管理股票
        stocks = list(
            session.scalars(
                select(Stock)
                .where(Stock.is_active == 1)
                .order_by(Stock.code)
            ).all()
        )

        stock_data = [
            {
                "股票代码": stock.code,
                "股票名称": stock.name or "未设置",
                "市场": stock.market,
            }
            for stock in stocks
        ]

        # 最近同步记录
        sync_logs = list(
            session.scalars(
                select(DataSyncLog)
                .order_by(desc(DataSyncLog.created_at))
                .limit(10)
            ).all()
        )

        sync_data = [
            {
                "股票代码": log.stock_code,
                "周期": log.period or "d",
                "复权口径": log.adjustflag or "3",
                "开始日期": log.start_date,
                "结束日期": log.end_date,
                "记录数量": log.record_count,
                "状态": log.status,
                "说明": log.message or "",
                "同步时间": log.created_at,
            }
            for log in sync_logs
        ]

        latest_sync = None

        if sync_logs:
            last = sync_logs[0]

            latest_sync = {
                "股票代码": last.stock_code,
                "同步记录数": last.record_count,
                "同步状态": last.status,
            }

    return {
        "stock_count": stock_count,
        "total_bars": total_bars,
        "raw_bars": raw_bars,
        "latest_trade_date": latest_trade_date,
        "stocks": stock_data,
        "sync_logs": sync_data,
        "latest_sync": latest_sync,
    }