"""StockPilot 入口：侧边栏导航和页面分发"""

import streamlit as st

from ui.dashboard import render_dashboard
from ui.data_sync import render_data_sync
from ui.stock_management import render_stock_management


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
# 页面分发
# =========================

if page == "🏠 工作台":
    render_dashboard()

elif page == "📋 股票管理":
    render_stock_management()

elif page == "📊 行情中心":
    st.title("📊 行情中心")
    st.info("下一阶段开发：历史行情查询、K线图、成交量分析。")

elif page == "🔄 数据同步":
    render_data_sync()

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