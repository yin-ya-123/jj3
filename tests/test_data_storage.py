
from database.db import SessionLocal, init_db
from database.models import Stock, DailyBar, DataSyncLog


def test_stockpilot_data_storage():
    init_db()

    with SessionLocal() as session:
        stocks = session.query(Stock).all()
        bars = session.query(DailyBar).all()
        logs = session.query(DataSyncLog).all()

        print("\n========== 数据库检查 ==========")
        print("股票数量:", len(stocks))
        print("日线记录数量:", len(bars))
        print("同步日志数量:", len(logs))

        assert len(stocks) > 0
        assert len(bars) > 0
        assert len(logs) > 0

        for stock in stocks:
            print("股票:", stock.code, stock.market)

        for bar in bars[:5]:
            print(
                bar.stock_code,
                bar.trade_date,
                bar.open,
                bar.close,
            )
