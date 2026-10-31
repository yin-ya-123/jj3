"""工作台页面：市场概览、数据状态、风险摘要"""

import pandas as pd
import streamlit as st

from database.repositories.dashboard_repository import get_dashboard_data


def render_dashboard():
    """工作台"""

    st.title("StockPilot")
    st.subheader("A股智能量化预测系统")

    try:
        data = get_dashboard_data()

        st.success("数据库连接正常")

        # 核心指标
        col1, col2, col3, col4 = st.columns(4)

        with col1:
            st.metric("股票数量", data["stock_count"])

        with col2:
            st.metric(
                "日线记录总数",
                f'{data["total_bars"]:,}',
            )

        with col3:
            st.metric(
                "不复权日线记录",
                f'{data["raw_bars"]:,}',
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

        status_col1, status_col2, status_col3, status_col4 = st.columns(4)

        with status_col1:
            st.info("行情数据源：Baostock")

        with status_col2:
            st.info("数据库：SQLite")

        with status_col3:
            st.info("行情口径：库存不复权原始价")

        with status_col4:
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
                st.metric("股票代码", latest_sync["股票代码"])

            with sync_col2:
                st.metric("同步记录数", latest_sync["同步记录数"])

            with sync_col3:
                st.metric("同步状态", latest_sync["同步状态"])

    except Exception as e:
        st.error(f"读取数据库失败：{e}")
        st.warning(
            "请检查 database/db.py、database/models.py "
            "以及数据库文件是否存在。"
        )