import baostock as bs
import pandas as pd

from data.utils import market_of
from data.utils import normalize_code as normalize_stock_code


class BaostockProvider:
    """Baostock A股历史行情与股票基础信息数据适配器"""

    FIELDS = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "preclose",
        "volume",
        "amount",
        "turn",
        "tradestatus",
        "pctChg",
        "isST",
    ]

    def normalize_code(self, symbol: str) -> str:
        """将普通股票代码转换为 Baostock 代码"""

        code = normalize_stock_code(symbol)

        # 市场规则只在 data/utils.market_of 里维护一份
        return f"{market_of(code).lower()}.{code}"

    # =========================
    # 历史行情
    # =========================

    def get_daily_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjustflag: str = "2",
    ) -> pd.DataFrame:
        """
        获取历史日线

        adjustflag:
            1: 后复权
            2: 前复权
            3: 不复权
        """

        code = self.normalize_code(symbol)

        login_result = bs.login()

        if login_result.error_code != "0":
            raise RuntimeError(
                f"Baostock 登录失败: {login_result.error_msg}"
            )

        try:
            result = bs.query_history_k_data_plus(
                code,
                ",".join(self.FIELDS),
                start_date=start_date,
                end_date=end_date,
                frequency="d",
                adjustflag=adjustflag,
            )

            if result.error_code != "0":
                raise RuntimeError(
                    f"行情查询失败: {result.error_msg}"
                )

            rows = []

            while result.next():
                rows.append(result.get_row_data())

            df = pd.DataFrame(rows, columns=result.fields)

            if df.empty:
                return df

            # 日期统一格式
            df["date"] = pd.to_datetime(df["date"])

            # 数值字段统一转换
            numeric_columns = [
                "open",
                "high",
                "low",
                "close",
                "preclose",
                "volume",
                "amount",
                "turn",
                "pctChg",
            ]

            for column in numeric_columns:
                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

            df["stock_code"] = symbol[-6:]

            # 删除无效价格数据
            df = df.dropna(
                subset=["date", "open", "high", "low", "close"]
            )

            df = df.sort_values("date").reset_index(drop=True)

            return df

        finally:
            bs.logout()

    # =========================
    # 股票基础信息
    # =========================

    def get_stock_basic(self, symbol: str) -> dict | None:
        """查询单只股票基础信息：名称、上市日期、类型、状态"""

        code = self.normalize_code(symbol)

        login_result = bs.login()

        if login_result.error_code != "0":
            raise RuntimeError(
                f"Baostock 登录失败: {login_result.error_msg}"
            )

        try:
            result = bs.query_stock_basic(code=code)

            if result.error_code != "0":
                raise RuntimeError(
                    f"基础信息查询失败: {result.error_msg}"
                )

            rows = []

            while result.next():
                rows.append(result.get_row_data())

            if not rows:
                return None

            df = pd.DataFrame(rows, columns=result.fields)

            records = self._to_basic_list(df)

            return records[0] if records else None

        finally:
            bs.logout()

    def search_stock(self, keyword: str) -> list[dict]:
        """按名称或代码搜索股票"""

        keyword = str(keyword).strip()

        if not keyword:
            return []

        # 纯6 位代码走精确查询
        if keyword.isdigit() and len(keyword) == 6:
            info = self.get_stock_basic(keyword)
            return [info] if info else []

        # 其余按名称模糊查
        login_result = bs.login()

        if login_result.error_code != "0":
            raise RuntimeError(
                f"Baostock 登录失败: {login_result.error_msg}"
            )

        try:
            result = bs.query_stock_basic(code_name=keyword)

            if result.error_code != "0":
                raise RuntimeError(
                    f"股票搜索失败: {result.error_msg}"
                )

            rows = []

            while result.next():
                rows.append(result.get_row_data())

            df = pd.DataFrame(rows, columns=result.fields)

            return self._to_basic_list(df)

        finally:
            bs.logout()

    def list_all_stocks(self) -> pd.DataFrame:
        """获取全市场股票字典

        数据源：query_stock_basic()（不带参数，返回全部证券）
        只保留 type=1（股票），上市与退市都保留
        market 直接取原始前缀 sh./sz./bj.，不再按代码首位猜测
        """
        login_result = bs.login()

        if login_result.error_code != "0":
            raise RuntimeError(f"Baostock 登录失败: {login_result.error_msg}")

        try:
            result = bs.query_stock_basic()

            if result.error_code != "0":
                raise RuntimeError(f"股票列表查询失败: {result.error_msg}")

            rows = []

            while result.next():
                rows.append(result.get_row_data())

            df = pd.DataFrame(rows, columns=result.fields)

            if df.empty:
                return df

            # type: # 1=股票 2=指数 3=其它 4=可转债 5=ETF 6=LOF 7=基金
            df = df[df["type"] == "1"].copy()
            full_code = df["code"].astype(str)

            df["market"] = full_code.str.split(".").str[0].str.upper()
            df["code"] = full_code.str.split(".").str[-1]
            df["name"] = df["code_name"]
            df["trade_status"] = df["status"]

            return df[["code", "name", "market", "trade_status"]]
        finally:
            bs.logout()

    @staticmethod
    def _to_basic_list(df: pd.DataFrame) -> list[dict]:
        """把基础信息查询结果转成统一字典列表"""

        records = []

        for _, row in df.iterrows():
            full_code = str(row["code"])

            records.append({
                "code": full_code.split(".")[-1],
                "name": row.get("code_name"),
                # 市场取数据源原始前缀，比按代码首位猜更准
                "market": full_code.split(".")[0].upper(),
                "ipo_date": row.get("ipoDate") or None,
                "out_date": row.get("outDate") or None,
                "type": row.get("type"),
                "status": row.get("status"),
                # Baostock 没有 trade_status 字段，上市/退市状态就是 status
                "trade_status": row.get("status"),
            })

        return records