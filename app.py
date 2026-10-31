
import streamlit as st
import pandas as pd

from sqlalchemy import func, desc

from database.db import SessionLocal
from database.models import Stock, DailyBar, DataSyncLog


# =========================
# 页面基础配置
# =========================

st.set_page_config(
    page_title="StockPilot",
    page_icon="📈",
    layout="wide",
    initial_sidebar_state="expanded",
)


# =========================
# 数据库统计
# =========================

def get_dashboard_data():
    """读取工作台需要的数据库统计信息"""

    db = SessionLocal()

    try:
        stock_count = db.query(func.count(Stock.code)).scalar() or 0

        total_bars = db.query(func.count(DailyBar.id)).scalar() or 0

        adjusted_bars = (
            db.query(func.count(DailyBar.id))
            .filter(DailyBar.adjustflag == "2")
            .scalar()
            or 0
        )

        latest_trade_date = db.query(
            func.max(DailyBar.trade_date)
        ).scalar()

        latest_sync = (
            db.query(DataSyncLog)
            .order_by(desc(DataSyncLog.created_at))
            .first()
        )

        # 股票列表
        stocks = (
            db.query(Stock)
            .order_by(Stock.code)
            .all()
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
        sync_logs = (
            db.query(DataSyncLog)
            .order_by(desc(DataSyncLog.created_at))
            .limit(10)
            .all()
        )

        sync_data = [
            {
                "股票代码": log.stock_code,
                "开始日期": log.start_date,
                "结束日期": log.end_date,
                "记录数量": log.record_count,
                "状态": log.status,
                "说明": log.message or "",
                "同步时间": log.created_at,
            }
            for log in sync_logs
        ]

        return {
            "stock_count": stock_count,
            "total_bars": total_bars,
            "adjusted_bars": adjusted_bars,
            "latest_trade_date": latest_trade_date,
            "latest_sync": latest_sync,
            "stocks": stock_data,
            "sync_logs": sync_data,
        }

    finally:
        db.close()


# =========================
# 侧边栏导航
# =========================

st.sidebar.title("📈 StockPilot")

st.sidebar.caption("A股智能量化预测系统")

page = st.sidebar.radio(
    "功能导航",
    [
        "🏠 工作台",
        "📋 股票管理",
        "📊 行情中心",
        "🔄 数据同步",
        "🔮 明日预测",
        "⚡ 盘中监控",
        "📈 历史回测",
        "🤖 模型管理",
    ],
)

st.sidebar.divider()

st.sidebar.caption("运行模式：本地预测")
st.sidebar.caption("自动交易：已关闭")

if st.sidebar.button("🔄 刷新数据", use_container_width=True):
    st.rerun()


# =========================
# 工作台
# =========================

if page == "🏠 工作台":

    st.title("StockPilot")
    st.subheader("A股智能量化预测系统")

    try:
        data = get_dashboard_data()

        st.success("数据库连接正常")

        # 核心指标
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric(
                "股票数量",
                data["stock_count"],
            )

        with col2:
            st.metric(
                "日线记录总数",
                f"{data['total_bars']:,}",
            )

        with col3:
            st.metric(
                "前复权日线记录",
                f"{data['adjusted_bars']:,}",
            )

        with col4:
            latest_date = data["latest_trade_date"]

            st.metric(
                "最新行情日期",
                str(latest_date) if latest_date else "暂无数据",
            )

        st.divider()

        # 系统状态
        st.subheader("🖥️ 系统状态")

        status_col1, status_col2, status_col3 = st.columns(3)

        with status_col1:
            st.info("行情数据源：Baostock")

        with status_col2:
            st.info("数据库：SQLite")

        with status_col3:
            st.info("自动交易：已关闭")

        st.divider()

        # 股票列表
        st.subheader("📋 已管理股票")

        if data["stocks"]:
            st.dataframe(
                pd.DataFrame(data["stocks"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.warning("当前还没有股票记录。")

        st.divider()

        # 最近同步记录
        st.subheader("🔄 最近数据同步记录")

        if data["sync_logs"]:
            st.dataframe(
                pd.DataFrame(data["sync_logs"]),
                use_container_width=True,
                hide_index=True,
            )
        else:
            st.info("暂时没有数据同步记录。")

        # 最近一次同步状态
        latest_sync = data["latest_sync"]

        if latest_sync:
            st.divider()
            st.subheader("最近一次同步")

            sync_col1, sync_col2, sync_col3 = st.columns(3)

            with sync_col1:
                st.metric("股票代码", latest_sync.stock_code)

            with sync_col2:
                st.metric("同步记录数", latest_sync.record_count)

            with sync_col3:
                st.metric("同步状态", latest_sync.status)

    except Exception as e:
        st.error(f"读取数据库失败：{e}")
        st.warning(
            "请检查 database/db.py、database/models.py "
            "以及数据库文件是否存在。"
        )


# =========================
# 其他功能页面：暂时占位
# =========================

elif page == "📋 股票管理":
    st.title("📋 股票管理")
    st.info("下一阶段开发：添加股票、删除股票、维护股票信息。")

elif page == "📊 行情中心":
    st.title("📊 行情中心")
    st.info("下一阶段开发：历史行情查询、K线图、成交量分析。")

elif page == "🔄 数据同步":
    st.title("🔄 数据同步")
    st.info("下一阶段开发：选择股票、设置日期范围、手动同步行情。")

elif page == "🔮 明日预测":
    st.title("🔮 明日预测")
    st.info("后续接入量化预测模型。")

elif page == "⚡ 盘中监控":
    st.title("⚡ 盘中监控")
    st.info("后续接入盘中行情监控和买卖提醒。")

elif page == "📈 历史回测":
    st.title("📈 历史回测")
    st.info("后续开发策略回测、收益分析和风险评估。")

elif page == "🤖 模型管理":
    st.title("🤖 模型管理")
    st.info("后续开发模型训练、评估和版本管理。")
