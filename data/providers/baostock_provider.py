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
    # 各周期 Baostock 实际支持的字段（实测，见 scripts/diag_period_fields.py）
    # 传错字段会报 10004012「xx线指标参数传入错误:字段名」
    _MINUTE_FIELDS = [
        "date",
        "time",
        "code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
    ]

    _WEEK_MONTH_FIELDS = [
        "date",
        "code",
        "open",
        "high",
        "low",
        "close",
        "volume",
        "amount",
        "turn",
        "pctChg",
    ]

    PERIOD_FIELDS = {
        "d": FIELDS,
        "w": _WEEK_MONTH_FIELDS,
        "m": _WEEK_MONTH_FIELDS,
        "5": _MINUTE_FIELDS,
        "15": _MINUTE_FIELDS,
        "30": _MINUTE_FIELDS,
        "60": _MINUTE_FIELDS,
    }

    def normalize_code(self, symbol: str) -> str:
        """将普通股票代码转换为 Baostock 代码"""

        code = normalize_stock_code(symbol)

        # 市场规则只在 data/utils.market_of 里维护一份
        return f"{market_of(code).lower()}.{code}"

    # =========================
    # 历史行情
    # =========================

    def _query_kline(
        self,
        code: str,
        fields: list,
        start_date: str,
        end_date: str,
        frequency: str,
        adjustflag: str,
    ) -> pd.DataFrame:
        """执行一次 K 线查询，返回原始 DataFrame（未做类型转换）"""

        login_result = bs.login()

        if login_result.error_code != "0":
            raise RuntimeError(
                f"Baostock 登录失败: {login_result.error_msg}"
            )

        try:
            result = bs.query_history_k_data_plus(
                code,
                ",".join(fields),
                start_date=start_date,
                end_date=end_date,
                frequency=frequency,
                adjustflag=adjustflag,
            )

            if result.error_code != "0":
                raise RuntimeError(
                    f"行情查询失败: {result.error_msg}"
                )

            rows = []

            while result.next():
                rows.append(result.get_row_data())

            return pd.DataFrame(rows, columns=result.fields)

        finally:
            bs.logout()

    def get_daily_history(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        adjustflag: str = "3",
    ) -> pd.DataFrame:
        """
        获取历史日线

        adjustflag:
            1: 后复权
            2: 前复权
            3: 不复权（项目默认口径）

        注意：前复权价锚定当前日期，除权后会整体漂移，
        不能拿来做增量同步；库里存不复权原始价，复权在计算层做。
        """

        code = self.normalize_code(symbol)

        df = self._query_kline(
            code,
            self.FIELDS,
            start_date,
            end_date,
            "d",
            adjustflag,
        )

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

    def get_period_history(
        self,
        symbol: str,
        period: str,
        start_date: str,
        end_date: str,
        adjustflag: str = "3",
    ) -> pd.DataFrame:
        """
        获取指定周期的历史行情，返回统一结构

        period: d / w / m / 5 / 15 / 30 / 60

        返回列：
            trade_time, stock_code, open, high, low, close, preclose,
            volume, amount, turn, pct_chg, trade_status, is_st
        """

        period = str(period).strip().lower()

        if period not in self.PERIOD_FIELDS:
            raise ValueError(
                f"不支持的周期: {period}，"
                f"可用: {', '.join(self.PERIOD_FIELDS)}"
            )

        code = self.normalize_code(symbol)

        df = self._query_kline(
            code,
            self.PERIOD_FIELDS[period],
            start_date,
            end_date,
            period,
            adjustflag,
        )

        if df.empty:
            return df

        # 分钟线用 time 字段（YYYYMMDDHHMMSSmmm），日/周/月线用 date
        if "time" in df.columns:
            df["trade_time"] = pd.to_datetime(
                df["time"].astype(str),
                format="%Y%m%d%H%M%S%f",
                errors="coerce",
            )
        else:
            df["trade_time"] = pd.to_datetime(
                df["date"],
                errors="coerce",
            )

        for column in [
            "open",
            "high",
            "low",
            "close",
            "preclose",
            "volume",
            "amount",
            "turn",
            "pctChg",
        ]:
            if column in df.columns:
                df[column] = pd.to_numeric(
                    df[column],
                    errors="coerce",
                )

        df["stock_code"] = str(symbol).strip()[-6:]

        df["pct_chg"] = (
            df["pctChg"] if "pctChg" in df.columns else None
        )
        df["trade_status"] = (
            df["tradestatus"] if "tradestatus" in df.columns else None
        )
        df["is_st"] = df["isST"] if "isST" in df.columns else None

        df = df.dropna(
            subset=["trade_time", "open", "high", "low", "close"]
        )

        return df.sort_values("trade_time").reset_index(drop=True)

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

    def get_adjust_factors(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """获取复权因子（除权除息事件）

        返回列：
            stock_code, divid_operate_date,
            fore_adjust_factor, back_adjust_factor, adjust_factor
        """

        code = self.normalize_code(symbol)

        login_result = bs.login()

        if login_result.error_code != "0":
            raise RuntimeError(f"Baostock 登录失败: {login_result.error_msg}")

        try:
            result = bs.query_adjust_factor(
                code=code,
                start_date=start_date,
                end_date=end_date,
            )

            if result.error_code != "0":
                raise RuntimeError(f"复权因子查询失败: {result.error_msg}")

            rows = []

            while result.next():
                rows.append(result.get_row_data())

            columns = [
                "stock_code",
                "divid_operate_date",
                "fore_adjust_factor",
                "back_adjust_factor",
                "adjust_factor",
            ]

            if not rows:
                return pd.DataFrame(columns=columns)

            df = pd.DataFrame(rows, columns=result.fields)

            df["divid_operate_date"] = pd.to_datetime(
                df["dividOperateDate"],
                errors="coerce",
            )

            df["fore_adjust_factor"] = pd.to_numeric(
                df["foreAdjustFactor"],
                errors="coerce",
            )

            df["back_adjust_factor"] = pd.to_numeric(
                df["backAdjustFactor"],
                errors="coerce",
            )

            df["adjust_factor"] = pd.to_numeric(
                df["adjustFactor"],
                errors="coerce",
            )

            df["stock_code"] = str(symbol).strip()[-6:]

            df = df.dropna(subset=["divid_operate_date"])

            df = df.sort_values("divid_operate_date").reset_index(drop=True)

            return df[columns]
        finally:
            bs.logout()

    @staticmethod
    def _dash_date(value: str) -> str:
        """把 YYYYMMDD 统一成 YYYY-MM-DD（交易日历接口要带横杠）"""

        text = str(value).strip()

        if len(text) == 8 and text.isdigit():
            return f"{text[:4]}-{text[4:6]}-{text[6:]}"

        return text

    def get_trade_dates(
        self,
        start_date: str,
        end_date: str,
    ) -> pd.DataFrame:
        """获取交易日历

        返回列：
            calendar_date  日历日
            is_trading_day 1=交易日，0=非交易日

        实测：一次查 12 年（4383 行）不报错，可按整段拉取。
        """

        login_result = bs.login()

        if login_result.error_code != "0":
            raise RuntimeError(f"Baostock 登录失败: {login_result.error_msg}")

        try:
            result = bs.query_trade_dates(
                start_date=self._dash_date(start_date),
                end_date=self._dash_date(end_date),
            )

            if result.error_code != "0":
                raise RuntimeError(f"交易日历查询失败: {result.error_msg}")

            rows = []

            while result.next():
                rows.append(result.get_row_data())

            columns = ["calendar_date", "is_trading_day"]

            if not rows:
                return pd.DataFrame(columns=columns)

            df = pd.DataFrame(rows, columns=result.fields)

            df["calendar_date"] = pd.to_datetime(
                df["calendar_date"],
                errors="coerce",
            )

            df["is_trading_day"] = pd.to_numeric(
                df["is_trading_day"],
                errors="coerce",
            ).fillna(0).astype(int)

            df = df.dropna(subset=["calendar_date"])

            return df[columns].sort_values("calendar_date").reset_index(drop=True)
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