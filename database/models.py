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

    code: Mapped[str] = mapped_column(String(6), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    market: Mapped[str] = mapped_column(String(10))

    # 阶段 2 新增：逻辑删除 / 行业 / 上市日期 / 更新时间
    is_active: Mapped[int] = mapped_column(Integer, default=1, server_default="1")
    industry: Mapped[str | None] = mapped_column(String(50), nullable=True)
    ipo_date: Mapped[date | None] = mapped_column(Date, nullable=True)
    updated_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    stock_code: Mapped[str] = mapped_column(String(6), index=True)
    trade_date: Mapped[date] = mapped_column(Date, index=True)

    # 库存不复权原始价，复权在计算层做（data/adjustment.py）
    adjustflag: Mapped[str] = mapped_column(String(1), default="3")

    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    preclose: Mapped[float | None] = mapped_column(Float)

    volume: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    turn: Mapped[float | None] = mapped_column(Float)
    pct_chg: Mapped[float | None] = mapped_column(Float)

    # 阶段 3.4 新增：交易状态（Baostock tradestatus）
    # '1'=正常交易 '0'=停牌；历史行迁移前为 NULL（未知）
    trade_status: Mapped[str | None] = mapped_column(String(2))

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
    )


class DataSyncLog(Base):
    """数据同步日志"""

    __tablename__ = "data_sync_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    stock_code: Mapped[str] = mapped_column(String(6), index=True)
    start_date: Mapped[str] = mapped_column(String(10))
    end_date: Mapped[str] = mapped_column(String(10))

    # 阶段 3 新增：同步的周期与复权口径
    # period: d / 5 / 15 / 30 / 60
    # adjustflag: 1=后复权 2=前复权 3=不复权（项目口径）
    period: Mapped[str] = mapped_column(
        String(5),
        default="d",
        server_default="d",
    )
    adjustflag: Mapped[str] = mapped_column(
        String(1),
        default="3",
        server_default="3",
    )

    record_count: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(20))
    message: Mapped[str | None] = mapped_column(String(500), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
    )


# =========================# 阶段 2 新增
# =========================

class StockGroup(Base):
    """股票分组（自选池），一只股票可属于多个分组"""

    __tablename__ = "stock_groups"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    name: Mapped[str] = mapped_column(String(50), unique=True, nullable=False)
    description: Mapped[str | None] = mapped_column(String(200), nullable=True)

    created_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
    )


class StockGroupMember(Base):
    """分组与股票的关联（多对多）"""

    __tablename__ = "stock_group_members"

    group_id: Mapped[int] = mapped_column(
        Integer,
        ForeignKey("stock_groups.id"),
        primary_key=True,
    )
    stock_code: Mapped[str] = mapped_column(
        String(6),
        ForeignKey("stocks.code"),
        primary_key=True,
    )
    added_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
    )


class StockReference(Base):
    """全市场股票字典（本地缓存，用于代码/名称搜索与校验）"""

    __tablename__ = "stock_reference"

    code: Mapped[str] = mapped_column(String(6), primary_key=True)
    name: Mapped[str | None] = mapped_column(String(50), nullable=True)
    market: Mapped[str] = mapped_column(String(10), nullable=False)
    trade_status: Mapped[str | None] = mapped_column(String(2), nullable=True)

    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        server_default=func.current_timestamp(),
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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    stock_code: Mapped[str] = mapped_column(String(6), index=True)
    period: Mapped[str] = mapped_column(String(5), nullable=False)
    trade_time: Mapped[datetime] = mapped_column(DateTime, nullable=False)

    adjustflag: Mapped[str] = mapped_column(String(1), default="3")

    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    preclose: Mapped[float | None] = mapped_column(Float)
    volume: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    turn: Mapped[float | None] = mapped_column(Float)
    pct_chg: Mapped[float | None] = mapped_column(Float)
    trade_status: Mapped[str | None] = mapped_column(String(2))


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

    calendar_date: Mapped[date] = mapped_column(Date, primary_key=True)

    is_trading_day: Mapped[int] = mapped_column(
        Integer,
        default=1,
        server_default="1",
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
    )

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    stock_code: Mapped[str] = mapped_column(String(6), index=True)
    divid_operate_date: Mapped[date] = mapped_column(Date, nullable=False)

    fore_adjust_factor: Mapped[float | None] = mapped_column(Float)
    back_adjust_factor: Mapped[float | None] = mapped_column(Float)
    adjust_factor: Mapped[float | None] = mapped_column(Float)