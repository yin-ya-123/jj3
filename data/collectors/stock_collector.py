"""股票基础信息采集：全市场字典同步、单只股票信息补全"""

from datetime import datetime, timedelta

from data.providers.baostock_provider import BaostockProvider
from database.repositories.stock_repository import (
    add_stock,
    upsert_reference,
)


class StockCollector:
    """股票基础信息采集服务"""

    def __init__(self):
        self.provider = BaostockProvider()

    def sync_reference(self, day: str | None = None) -> int:
        """同步全市场股票字典到本地库，返回写入条数"""

        days = [day] if day else self._candidate_days()

        for one_day in days:
            df = self.provider.list_all_stocks(one_day)

            if df.empty:
                continue

            return upsert_reference(df.to_dict("records"))

        return 0

    def fetch_basic(self, code: str) -> dict | None:
        """联网查询单只股票基础信息"""

        return self.provider.get_stock_basic(code)

    def search_stock(self, keyword: str) -> list[dict]:
        """联网按名称或代码搜索股票"""

        return self.provider.search_stock(keyword)

    def add_stock(self, code: str, name: str | None = None) -> dict:
        """联网补全信息后写入本地股票表"""

        info = self.fetch_basic(code)

        if info is None:
            raise ValueError(f"数据源查不到该股票: {code}")

        return add_stock(
            code=info["code"],
            name=name or info.get("name"),
            ipo_date=info.get("ipo_date"),
        )

    @staticmethod
    def _candidate_days() -> list[str]:
        """最近几个工作日，当天数据没发布时自动往前回退"""

        days = []
        day = datetime.now()

        for _ in range(7):
            if day.weekday() < 5:
                days.append(day.strftime("%Y-%m-%d"))

            day -= timedelta(days=1)

        return days