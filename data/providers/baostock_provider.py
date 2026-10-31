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

        if code.startswith("6"):
            return f"sh.{code}"

        if code.startswith(("0", "3")):
            return f"sz.{code}"

        if code.startswith(("4", "8")):
            return f"bj.{code}"

        raise ValueError(f"暂不支持的股票代码: {symbol}")

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

    def list_all_stocks(self, day: str) -> pd.DataFrame:
        """获取指定交易日的全市场股票列表"""

        login_result = bs.login()

        if login_result.error_code != "0":
            raise RuntimeError(
                f"Baostock 登录失败: {login_result.error_msg}"
            )

        try:
            result = bs.query_all_stock(day=day)

            if result.error_code != "0":
                raise RuntimeError(
                    f"股票列表查询失败: {result.error_msg}"
                )

            rows = []

            while result.next():
                rows.append(result.get_row_data())

            df = pd.DataFrame(rows, columns=result.fields)

            if df.empty:
                return df

            df = df.rename(
                columns={"code_name": "name", "tradeStatus": "trade_status"}
            )

            df["code"] = df["code"].astype(str).str.split(".").str[-1]
            df["market"] = df["code"].map(market_of)

            return df[["code", "name", "market", "trade_status"]]

        finally:
            bs.logout()

    @staticmethod
    def _to_basic_list(df: pd.DataFrame) -> list[dict]:
        """把基础信息查询结果转成统一字典列表"""

        records = []

        for _, row in df.iterrows():
            code = str(row["code"]).split(".")[-1]

            records.append({
                "code": code,
                "name": row.get("code_name"),
                "market": market_of(code),
                "ipo_date": row.get("ipoDate") or None,
                "out_date": row.get("outDate") or None,
                "type": row.get("type"),
                "status": row.get("status"),
                "trade_status": row.get("trade_status"),
            })

        return records