"""akshare 东方财富财报数据适配器（阶段 5.1）

数据源选型（用户确认）：akshare 东财报表为主、新浪/东财摘要为辅。

接口：
    stock_balance_sheet_by_report_em    资产负债表（by_report_em，带报告期/披露日期）
    stock_profit_sheet_by_report_em     利润表
    stock_cash_flow_sheet_by_report_em  现金流量表
    stock_financial_abstract            财务摘要（ROE/净利率/毛利率等纵向指标）

三表接口自带 REPORT_DATE（报告期）与 NOTICE_DATE（披露日期）双字段，
直接对应 financial_reports 宽表的 report_date / announce_date。

字段映射策略：东财三表为英文列名、摘要为中文列名，且不同 akshare 版本
列名有差异，因此对每个目标指标维护候选列名列表（别名兜底），
取第一个存在的候选列，其余缺失落 NULL。
"""

import pandas as pd

from data.utils import market_of, normalize_code


# 三表接口的标准日期列
REPORT_DATE_COLUMN = "REPORT_DATE"
NOTICE_DATE_COLUMN = "NOTICE_DATE"

# 目标指标 -> 数据源候选列名（东财三表英文优先，摘要中文兜底）
# key 即 financial_reports 宽表列名，需与 database/repositories/
# financial_report_repository.py 的 FLOAT_COLUMNS 保持一致（测试会断言）。
INDICATOR_ALIASES = {
    # ---- 盈利能力（财务摘要） ----
    "roe": ["ROE", "净资产收益率", "净资产收益率(ROE)"],
    "roe_diluted": ["ROE_DILUTED", "加权净资产收益率"],
    "net_profit_ratio": ["NET_PROFIT_RATIO", "销售净利率", "净利率"],
    "gross_profit_ratio": ["GROSS_PROFIT_RATIO", "销售毛利率", "毛利率"],
    "eps": ["EPS", "摊薄每股收益", "每股收益"],
    "bps": ["BPS", "每股净资产"],
    # ---- 资产负债（资产负债表） ----
    "total_assets": ["TOTAL_ASSETS", "资产总计"],
    "total_liabilities": ["TOTAL_LIABILITIES", "负债合计"],
    "total_equity": ["TOTAL_EQUITY", "股东权益合计"],
    "parent_equity": ["TOTAL_PARENT_EQUITY", "PARENT_EQUITY", "归母股东权益"],
    "monetary_funds": ["MONETARYFUNDS", "货币资金"],
    "accounts_receivable": ["ACCOUNTS_RECE", "应收账款"],
    "inventory": ["INVENTORY", "存货"],
    "fixed_asset": ["FIXED_ASSET", "固定资产"],
    "goodwill": ["GOODWILL", "商誉"],
    # ---- 利润（利润表） ----
    "operate_income": ["OPERATE_INCOME", "营业总收入"],
    "operate_cost": ["OPERATE_COST", "营业总成本"],
    "operate_profit": ["OPERATE_PROFIT", "营业利润"],
    "total_profit": ["TOTAL_PROFIT", "利润总额"],
    "net_profit": ["NETPROFIT", "净利润"],
    "parent_net_profit": ["PARENT_NETPROFIT", "归母净利润"],
    "deduct_parent_net_profit": [
        "DEDUCT_PARENT_NETPROFIT",
        "扣除非经常性损益后的净利润",
        "扣非净利润",
    ],
    "sell_expense": ["SELL_EXPENSE", "销售费用"],
    "manage_expense": ["MANAGE_EXPENSE", "管理费用"],
    "finance_expense": ["FINANCE_EXPENSE", "财务费用"],
    "research_expense": ["RESEARCH_EXPENSE", "研发费用"],
    "operate_income_yoy": ["OPERATE_INCOME_YOY", "营业总收入同比增长率", "营业总收入同比增长"],
    "net_profit_yoy": ["NETPROFIT_YOY", "净利润同比增长率", "净利润同比增长"],
    "parent_net_profit_yoy": [
        "PARENT_NETPROFIT_YOY",
        "归母净利润同比增长率",
        "归母净利润同比增长",
    ],
    "deduct_parent_net_profit_yoy": [
        "DEDUCT_PARENT_NETPROFIT_YOY",
        "扣非净利润同比增长率",
        "扣非净利润同比增长",
    ],
    # ---- 现金流（现金流量表） ----
    "netcash_operate": ["NETCASH_OPERATE", "经营活动产生的现金流量净额"],
    "netcash_invest": ["NETCASH_INVEST", "投资活动产生的现金流量净额"],
    "netcash_finance": ["NETCASH_FINANCE", "筹资活动产生的现金流量净额"],
    "netcash_total": ["NETCASH", "现金及现金等价物净增加额"],
}

# 三表接口名
_REPORT_SHEET_METHODS = (
    "stock_balance_sheet_by_report_em",
    "stock_profit_sheet_by_report_em",
    "stock_cash_flow_sheet_by_report_em",
)

# 摘要接口的日期列候选（中文“日期”/英文 REPORT_DATE）
_ABSTRACT_DATE_CANDIDATES = ("日期", "REPORT_DATE", "report_date")


def merge_report_frames(frames: list) -> pd.DataFrame:
    """按报告期横向合并多张报表（outer join on report_date）

    输入：各报表 DataFrame，已含 report_date / announce_date 两列。
    输出：合并后的宽表（report_date 对齐，announce_date 取各表首个非空）。
    """

    if not frames:
        return pd.DataFrame()

    merged = frames[0].copy()

    for frame in frames[1:]:
        if frame is None or frame.empty:
            continue

        merged = pd.merge(
            merged,
            frame,
            on="report_date",
            how="outer",
            suffixes=("", "_dup"),
        )

    # announce_date 去重合并：取第一个非空
    announce_columns = [
        column for column in merged.columns
        if column.startswith("announce_date")
    ]

    if announce_columns:
        merged["announce_date"] = (
            merged[announce_columns]
            .apply(lambda row: next(
                (value for value in row if pd.notna(value)), None
            ), axis=1)
        )

        # 清理 merge 产生的重复列（announce_date_dup 等）
        merged = merged.drop(
            columns=[
                column for column in announce_columns[1:]
            ]
        )

    merged = merged.drop_duplicates(subset=["report_date"])
    merged = merged.sort_values("report_date").reset_index(drop=True)

    return merged


def merge_abstract(merged: pd.DataFrame, abstract: pd.DataFrame) -> pd.DataFrame:
    """把财务摘要（纵向指标）并入宽表

    stock_financial_abstract 返回中文列名，日期列通常是“日期”，
    需先对齐成 report_date 再做 outer join。
    """

    if abstract is None or abstract.empty:
        return merged

    frame = abstract.copy()

    date_column = next(
        (
            column for column in _ABSTRACT_DATE_CANDIDATES
            if column in frame.columns
        ),
        None,
    )

    if date_column is None:
        return merged

    frame["report_date"] = pd.to_datetime(
        frame[date_column],
        errors="coerce",
    )

    frame = frame.dropna(subset=["report_date"])

    if frame.empty:
        return merged

    return pd.merge(
        merged,
        frame,
        on="report_date",
        how="outer",
        suffixes=("", "_dup"),
    )


def extract_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """按 INDICATOR_ALIASES 抽取宽表指标列并数值化

    输出列：report_date, announce_date, <各目标指标>。
    缺失的指标列落 None（不报错），兼容不同 akshare 版本的列名差异。
    """

    if df is None or df.empty:
        return pd.DataFrame(
            columns=["report_date", "announce_date"] + list(INDICATOR_ALIASES)
        )

    output = pd.DataFrame()
    output["report_date"] = df.get("report_date")
    output["announce_date"] = df.get("announce_date")

    for target, candidates in INDICATOR_ALIASES.items():
        source = next(
            (
                column for column in candidates
                if column in df.columns
            ),
            None,
        )

        if source is None:
            output[target] = None
            continue

        output[target] = pd.to_numeric(df[source], errors="coerce")

    return output


class AkshareFinancialProvider:
    """akshare 东方财富财报数据适配器"""

    def get_financial_reports(
        self,
        symbol: str,
        start_date: str = "19900101",
        end_date: str = "20500101",
    ) -> pd.DataFrame:
        """获取单只股票全部报告期财报，返回统一宽表

        返回列：
            stock_code, report_date, announce_date, <INDICATOR_ALIASES 各指标>

        每次联网请求：三表 + 摘要，共 4 次。
        """

        code = normalize_code(symbol)
        em_symbol = f"{market_of(code)}{code}"  # 东财格式：SH600519 / SZ000001

        import akshare as ak  # 延迟导入：离线测试不触网

        frames = []

        for method in _REPORT_SHEET_METHODS:
            raw = None

            try:
                raw = getattr(ak, method)(
                    symbol=em_symbol,
                    start_date=start_date,
                    end_date=end_date,
                )
            except TypeError:
                # 部分 akshare 版本三表接口只接受 symbol，
                # 降级为全量拉取，在内存里按报告期过滤。
                raw = getattr(ak, method)(symbol=em_symbol)

            if raw is None or raw.empty:
                continue

            if REPORT_DATE_COLUMN not in raw.columns:
                continue

            raw = raw.copy()
            raw["report_date"] = pd.to_datetime(
                raw[REPORT_DATE_COLUMN],
                errors="coerce",
            )

            if NOTICE_DATE_COLUMN in raw.columns:
                raw["announce_date"] = pd.to_datetime(
                    raw[NOTICE_DATE_COLUMN],
                    errors="coerce",
                )
            else:
                raw["announce_date"] = pd.NaT

            raw = raw.dropna(subset=["report_date"])

            # 全量模式下按报告期过滤区间
            if REPORT_DATE_COLUMN in raw.columns:
                start_ts = pd.to_datetime(start_date, errors="coerce")
                end_ts = pd.to_datetime(end_date, errors="coerce")

                if pd.notna(start_ts):
                    raw = raw[raw["report_date"] >= start_ts]
                if pd.notna(end_ts):
                    raw = raw[raw["report_date"] <= end_ts]

            frames.append(raw)

        if not frames:
            return pd.DataFrame(
                columns=["stock_code", "report_date", "announce_date"]
                + list(INDICATOR_ALIASES)
            )

        merged = merge_report_frames(frames)

        abstract = ak.stock_financial_abstract(symbol=code)

        if abstract is not None and not abstract.empty:
            merged = merge_abstract(merged, abstract)

        output = extract_indicators(merged)
        output["stock_code"] = code
        output["announce_date"] = pd.to_datetime(
            output["announce_date"], errors="coerce"
        )

        return output
