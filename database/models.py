from datetime import datetime, date

from sqlalchemy import (
    String,
    Float,
    Integer,
    Date,
    DateTime,
    UniqueConstraint,
    ForeignKey,
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

    adjustflag: Mapped[str] = mapped_column(String(1), default="2")

    open: Mapped[float | None] = mapped_column(Float)
    high: Mapped[float | None] = mapped_column(Float)
    low: Mapped[float | None] = mapped_column(Float)
    close: Mapped[float | None] = mapped_column(Float)
    preclose: Mapped[float | None] = mapped_column(Float)

    volume: Mapped[float | None] = mapped_column(Float)
    amount: Mapped[float | None] = mapped_column(Float)
    turn: Mapped[float | None] = mapped_column(Float)
    pct_chg: Mapped[float | None] = mapped_column(Float)

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