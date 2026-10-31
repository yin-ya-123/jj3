from datetime import datetime, date


from sqlalchemy import (
    String,
    Float,
    Integer,
    Date,
    DateTime,
    UniqueConstraint,
    ForeignKey,
    Index,
    func,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class Stock(Base):
    """股票基础信息"""

    __tablename__ = "stocks"

    __table_args__ = {"comment": "股票基础信息（自选池在册股票）"}

    code: Mapped[str] = mapped_column(
        String(6),
        primary_key=True,
        comment="股票代码（6 位）",
    )
    name: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="股票名称"
    )
    market: Mapped[str] = mapped_column(String(10), comment="市场代码（sh/sz/bj）")

    # 阶段 2 新增：逻辑删除 / 行业 / 上市日期 / 更新时间
    is_active: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        comment="是否在用：1=在用 0=已删除（逻辑删除）",
    )
    industry: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="所属行业"
    )
    ipo_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="上市日期"
    )
    updated_at: Mapped[datetime | None] = mapped_column(
        DateTime, nullable=True, comment="更新时间"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        comment="创建时间",
    )


class DailyBar(Base):
    """股票历史日线"""

    __tablename__ = "daily_bars"

    __table_args__ = (
        UniqueConstraint(
            "stock_code",
            "trade_date",
            "adjustflag",
            name="uq_daily_bar",
        ),
        {"comment": "股票历史日线（库存不复权原始价，复权在计算层做）"},
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="自增主键"
    )

    stock_code: Mapped[str] = mapped_column(
        String(6), index=True, comment="股票代码（6 位）"
    )
    trade_date: Mapped[date] = mapped_column(
        Date, index=True, comment="交易日"
    )

    # 库存不复权原始价，复权在计算层做（data/adjustment.py）
    adjustflag: Mapped[str] = mapped_column(
        String(1), default="3", comment="复权口径：1=后复权 2=前复权 3=不复权"
    )

    open: Mapped[float | None] = mapped_column(Float, comment="开盘价")
    high: Mapped[float | None] = mapped_column(Float, comment="最高价")
    low: Mapped[float | None] = mapped_column(Float, comment="最低价")
    close: Mapped[float | None] = mapped_column(Float, comment="收盘价")
    preclose: Mapped[float | None] = mapped_column(Float, comment="昨收价")

    volume: Mapped[float | None] = mapped_column(Float, comment="成交量（股）")
    amount: Mapped[float | None] = mapped_column(Float, comment="成交额（元）")
    turn: Mapped[float | None] = mapped_column(Float, comment="换手率（%）")
    pct_chg: Mapped[float | None] = mapped_column(Float, comment="涨跌幅（%）")

    # 阶段 3.4 新增：交易状态（Baostock tradestatus）
    # '1'=正常交易 '0'=停牌；历史行迁移前为 NULL（未知）
    trade_status: Mapped[str | None] = mapped_column(
        String(2), comment="交易状态：1=正常 0=停牌 NULL=未知（迁移前存量）"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        comment="创建时间",
    )


class DataSyncLog(Base):
    """数据同步日志"""

    __tablename__ = "data_sync_logs"

    __table_args__ = {"comment": "数据同步日志（CLI 与界面同步均写入）"}

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="自增主键"
    )

    stock_code: Mapped[str] = mapped_column(
        String(6), index=True, comment="股票代码（6 位）"
    )
    start_date: Mapped[str] = mapped_column(
        String(10), comment="同步开始日期"
    )
    end_date: Mapped[str] = mapped_column(
        String(10), comment="同步结束日期"
    )

    # 阶段 3 新增：同步的周期与复权口径
    # period: d / 5 / 15 / 30 / 60
    # adjustflag: 1=后复权 2=前复权 3=不复权（项目口径）
    period: Mapped[str] = mapped_column(
        String(5),
        default="d",
        server_default="d",
        comment="周期：d=日线 5/15/30/60=分钟线",
    )
    adjustflag: Mapped[str] = mapped_column(
        String(1),
        default="3",
        server_default="3",
        comment="复权口径：1=后复权 2=前复权 3=不复权",
    )

    record_count: Mapped[int] = mapped_column(
        Integer, default=0, comment="本次同步入库记录数"
    )
    status: Mapped[str] = mapped_column(
        String(20), comment="状态：success/skipped/failed"
    )
    message: Mapped[str | None] = mapped_column(
        String(500), nullable=True, comment="说明（失败原因/跳过原因）"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        comment="创建时间（同步时间）",
    )


# =========================# 阶段 2 新增
# =========================

class StockGroup(Base):
    """股票分组（自选池），一只股票可属于多个分组"""

    __tablename__ = "stock_groups"

    __table_args__ = {"comment": "股票分组（自选池）"}

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="自增主键"
    )

    name: Mapped[str] = mapped_column(
        String(50), unique=True, nullable=False, comment="分组名称"
    )
    description: Mapped[str | None] = mapped_column(
        String(200), nullable=True, comment="分组描述"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        comment="创建时间",
    )


class StockGroupMember(Base):
    """分组与股票的关联（多对多）"""

    __tablename__ = "stock_group_members"

    __table_args__ = {"comment": "分组与股票的多对多关联"}

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stock_groups.id"),
        primary_key=True,
        comment="分组 ID",
    )
    stock_code: Mapped[str] = mapped_column(
        String(6),
        ForeignKey("stocks.code"),
        primary_key=True,
        comment="股票代码（6 位）",
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        comment="加入时间",
    )


class StockReference(Base):
    """全市场股票字典（本地缓存，用于代码/名称搜索与校验）"""

    __tablename__ = "stock_reference"

    __table_args__ = {"comment": "全市场股票字典（本地缓存）"}

    code: Mapped[str] = mapped_column(
        String(6), primary_key=True, comment="股票代码（6 位）"
    )
    name: Mapped[str | None] = mapped_column(
        String(50), nullable=True, comment="股票名称"
    )
    market: Mapped[str] = mapped_column(
        String(10), nullable=False, comment="市场代码（sh/sz）"
    )
    trade_status: Mapped[str | None] = mapped_column(
        String(2), nullable=True, comment="交易状态：1=上市 0=退市 NULL=未知"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        comment="更新时间",
    )

class Bar(Base):
    """股票多周期行情（只存分钟线）

    日线仍在 daily_bars；周线/月线不入库，由日线聚合得到。
    """

    __tablename__ = "bars"

    __table_args__ = (
        UniqueConstraint(
            "stock_code",
            "period",
            "trade_time",
            "adjustflag",
            name="uq_bar",
        ),
        Index(
            "ix_bar_stock_period",
            "stock_code",
            "period",
            "trade_time",
        ),
        {"comment": "股票多周期行情（只存分钟线，日线在 daily_bars）"},
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="自增主键"
    )

    stock_code: Mapped[str] = mapped_column(
        String(6), index=True, comment="股票代码（6 位）"
    )
    period: Mapped[str] = mapped_column(
        String(5), nullable=False, comment="周期：5/15/30/60 分钟"
    )
    trade_time: Mapped[datetime] = mapped_column(
        DateTime, nullable=False, comment="交易时间"
    )

    adjustflag: Mapped[str] = mapped_column(
        String(1), default="3", comment="复权口径：1=后复权 2=前复权 3=不复权"
    )

    open: Mapped[float | None] = mapped_column(Float, comment="开盘价")
    high: Mapped[float | None] = mapped_column(Float, comment="最高价")
    low: Mapped[float | None] = mapped_column(Float, comment="最低价")
    close: Mapped[float | None] = mapped_column(Float, comment="收盘价")
    preclose: Mapped[float | None] = mapped_column(Float, comment="昨收价")
    volume: Mapped[float | None] = mapped_column(Float, comment="成交量（股）")
    amount: Mapped[float | None] = mapped_column(Float, comment="成交额（元）")
    turn: Mapped[float | None] = mapped_column(Float, comment="换手率（%）")
    pct_chg: Mapped[float | None] = mapped_column(Float, comment="涨跌幅（%）")
    trade_status: Mapped[str | None] = mapped_column(
        String(2), comment="交易状态：1=正常 0=停牌 NULL=未知"
    )


# =========================# 阶段 3 新增
# =========================

class TradingCalendar(Base):
    """交易日历

    每个日历日一行：is_trading_day=1 表示当天开市，0 表示休市。
    用途：
        增量同步时判断区间内有没有交易日（没有就不必请求数据源）
        数据完整性检查时找缺失的交易日（阶段 3.4）
    """

    __tablename__ = "trading_calendar"

    __table_args__ = {"comment": "交易日历（每个日历日一行，标定是否开市）"}

    calendar_date: Mapped[date] = mapped_column(
        Date, primary_key=True, comment="日历日期"
    )

    is_trading_day: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
        comment="是否交易日：1=开市 0=休市",
    )


class AdjustFactor(Base):
    """复权因子（除权除息事件表）

    每只股票每次除权除息产生一行：
        back_adjust_factor  该日之后生效的累积后复权因子，单调递增，历史永不变
        fore_adjust_factor  该日之后生效的前复权因子，随最新除权事件漂移（仅作采集快照）

    换算公式（实测验证，见 scripts/diag_factor_semantics.py）：
        后复权价 = 不复权价 * back_adjust_factor(date)
        前复权价 = 不复权价 * back_adjust_factor(date) / back_adjust_factor(latest)
    """

    __tablename__ = "adjust_factors"

    __table_args__ = (
        UniqueConstraint(
            "stock_code",
            "divid_operate_date",
            name="uq_adjust_factor",
        ),
        {"comment": "复权因子（除权除息事件表）"},
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="自增主键"
    )

    stock_code: Mapped[str] = mapped_column(
        String(6), index=True, comment="股票代码（6 位）"
    )
    divid_operate_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="除权除息日"
    )

    fore_adjust_factor: Mapped[float | None] = mapped_column(
        Float, comment="前复权因子（随最新除权事件漂移，仅作快照）"
    )
    back_adjust_factor: Mapped[float | None] = mapped_column(
        Float, comment="后复权因子（单调递增，历史永不变）"
    )
    adjust_factor: Mapped[float | None] = mapped_column(
        Float, comment="调整因子（Baostock 原始字段）"
    )


class SchemaComment(Base):
    """表/字段注释元数据

    SQLite 无原生 COMMENT 语法（MySQL/Oracle 的 COMMENT ON 不支持），
    本表用于把 models.py 中 Table/Column 的 comment 参数持久化到库里，
    供数据库工具查询、导出文档使用。column_name 为 NULL 表示表注释。
    """

    __tablename__ = "schema_comments"

    __table_args__ = (
        UniqueConstraint(
            "table_name",
            "column_name",
            name="uq_schema_comment",
        ),
        {"comment": "表/字段注释元数据（SQLite 注释持久化）"},
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="自增主键"
    )

    table_name: Mapped[str] = mapped_column(
        String(100), nullable=False, comment="表名"
    )
    column_name: Mapped[str | None] = mapped_column(
        String(100), nullable=True, comment="列名（NULL=表注释）"
    )
    comment: Mapped[str] = mapped_column(
        String(500), comment="注释内容"
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        comment="更新时间",
    )


# =========================# 阶段 5.1 新增
# =========================

class FinancialReport(Base):
    """财报宽表（报告期 × 核心财务指标）

    每只股票每个报告期一行，双日期字段：
        report_date   报告期（如 2026-06-30，STAT_DATE）
        announce_date 披露日期（NOTICE_DATE，财报实际公开日）

    历史回测只用 announce_date <= 回测日 的数据，避免未来函数。
    数据源：akshare 东方财富三表 + 财务摘要（阶段 5.1 选型）。
    数值单位随数据源原值（元），比率类为百分比（%），增速类为百分比（%）。
    """

    __tablename__ = "financial_reports"

    __table_args__ = (
        UniqueConstraint(
            "stock_code",
            "report_date",
            name="uq_financial_report",
        ),
        Index(
            "ix_financial_report_code_date",
            "stock_code",
            "report_date",
        ),
        {"comment": "财报宽表（报告期 × 核心财务指标，双日期字段）"},
    )

    id: Mapped[int] = mapped_column(
        Integer, primary_key=True, autoincrement=True, comment="自增主键"
    )

    stock_code: Mapped[str] = mapped_column(
        String(6), index=True, comment="股票代码（6 位）"
    )
    report_date: Mapped[date] = mapped_column(
        Date, nullable=False, comment="报告期（如 2026-06-30）"
    )
    announce_date: Mapped[date | None] = mapped_column(
        Date, nullable=True, comment="披露日期（财报实际公开日，回测防未来函数）"
    )

    # ---- 盈利能力（财务摘要） ----
    roe: Mapped[float | None] = mapped_column(Float, comment="净资产收益率 ROE（%）")
    roe_diluted: Mapped[float | None] = mapped_column(
        Float, comment="加权净资产收益率（%）"
    )
    net_profit_ratio: Mapped[float | None] = mapped_column(
        Float, comment="销售净利率（%）"
    )
    gross_profit_ratio: Mapped[float | None] = mapped_column(
        Float, comment="销售毛利率（%）"
    )
    eps: Mapped[float | None] = mapped_column(Float, comment="每股收益（元）")
    bps: Mapped[float | None] = mapped_column(Float, comment="每股净资产（元）")

    # ---- 资产负债（资产负债表） ----
    total_assets: Mapped[float | None] = mapped_column(Float, comment="资产总计（元）")
    total_liabilities: Mapped[float | None] = mapped_column(
        Float, comment="负债合计（元）"
    )
    total_equity: Mapped[float | None] = mapped_column(
        Float, comment="股东权益合计（元）"
    )
    parent_equity: Mapped[float | None] = mapped_column(
        Float, comment="归母股东权益（元）"
    )
    monetary_funds: Mapped[float | None] = mapped_column(Float, comment="货币资金（元）")
    accounts_receivable: Mapped[float | None] = mapped_column(
        Float, comment="应收账款（元）"
    )
    inventory: Mapped[float | None] = mapped_column(Float, comment="存货（元）")
    fixed_asset: Mapped[float | None] = mapped_column(Float, comment="固定资产（元）")
    goodwill: Mapped[float | None] = mapped_column(Float, comment="商誉（元）")

    # ---- 利润（利润表） ----
    operate_income: Mapped[float | None] = mapped_column(
        Float, comment="营业总收入（元）"
    )
    operate_cost: Mapped[float | None] = mapped_column(Float, comment="营业总成本（元）")
    operate_profit: Mapped[float | None] = mapped_column(Float, comment="营业利润（元）")
    total_profit: Mapped[float | None] = mapped_column(Float, comment="利润总额（元）")
    net_profit: Mapped[float | None] = mapped_column(Float, comment="净利润（元）")
    parent_net_profit: Mapped[float | None] = mapped_column(
        Float, comment="归母净利润（元）"
    )
    deduct_parent_net_profit: Mapped[float | None] = mapped_column(
        Float, comment="扣非归母净利润（元）"
    )
    sell_expense: Mapped[float | None] = mapped_column(Float, comment="销售费用（元）")
    manage_expense: Mapped[float | None] = mapped_column(Float, comment="管理费用（元）")
    finance_expense: Mapped[float | None] = mapped_column(Float, comment="财务费用（元）")
    research_expense: Mapped[float | None] = mapped_column(Float, comment="研发费用（元）")
    operate_income_yoy: Mapped[float | None] = mapped_column(
        Float, comment="营业总收入同比增长（%）"
    )
    net_profit_yoy: Mapped[float | None] = mapped_column(
        Float, comment="净利润同比增长（%）"
    )
    parent_net_profit_yoy: Mapped[float | None] = mapped_column(
        Float, comment="归母净利润同比增长（%）"
    )
    deduct_parent_net_profit_yoy: Mapped[float | None] = mapped_column(
        Float, comment="扣非归母净利润同比增长（%）"
    )

    # ---- 现金流（现金流量表） ----
    netcash_operate: Mapped[float | None] = mapped_column(
        Float, comment="经营活动现金流量净额（元）"
    )
    netcash_invest: Mapped[float | None] = mapped_column(
        Float, comment="投资活动现金流量净额（元）"
    )
    netcash_finance: Mapped[float | None] = mapped_column(
        Float, comment="筹资活动现金流量净额（元）"
    )
    netcash_total: Mapped[float | None] = mapped_column(
        Float, comment="现金及现金等价物净增加额（元）"
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
        comment="创建时间",
    )