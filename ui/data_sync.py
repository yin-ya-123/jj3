"""数据同步页面（阶段 3.5）

三个页签：
    同步行情   选择股票 / 区间 / 周期，手动发起一次同步（联网写库）
    同步日志   查看最近同步记录（data_sync_logs）
    数据质量   只读完整性检查：缺失交易日 / 停牌日 / 未知状态

同步与检查均复用服务层 / 仓储，页面只负责收集参数与展示结果。
"""

from datetime import date, timedelta

import pandas as pd
import streamlit as st

from data.sync_service import run_daily_sync
from database.repositories.dashboard_repository import get_sync_logs
from database.repositories.data_quality_repository import (
    check_data_integrity,
)
from database.repositories.stock_repository import list_stocks

PERIOD_OPTIONS = {
    "日线": "d",
    "5 分钟": "5",
    "15 分钟": "15",
    "30 分钟": "30",
    "60 分钟": "60",
}


def _load_active_stocks() -> list[dict]:
    """自选池在用股票（code/name/market）"""

    return list_stocks(only_active=True)


def _label_map(rows: list[dict]) -> dict[str, str]:
    return {r["code"]: f'{r["code"]} {r["name"] or ""}' for r in rows}


def _fmt_days(days: list) -> str:
    if not days:
        return "-"

    head = [d.strftime("%Y-%m-%d") for d in days[:8]]
    text = "、".join(head)

    if len(days) > 8:
        text += f" 等 {len(days)} 天"

    return text


# =========================
# 页签一：同步行情
# =========================

def _render_sync_tab() -> None:
    st.subheader("发起同步")
    st.caption("同步会连接 Baostock 并写入正式数据库，耗时较长，请耐心等待。")

    rows = _load_active_stocks()

    if not rows:
        st.info("自选池还没有股票，请先到「股票管理」添加。")

        return

    label = _label_map(rows)

    col1, col2 = st.columns(2)

    with col1:
        sync_all = st.checkbox(
            "同步全部自选池股票",
            value=True,
            key="sync_all",
        )

        if sync_all:
            codes = [r["code"] for r in rows]
            st.caption(f"共 {len(codes)} 只：{'、'.join(codes[:10])}")
        else:
            picked = st.multiselect(
                "选择股票",
                list(label.keys()),
                format_func=lambda c: label[c],
                key="sync_pick",
            )

            codes = list(picked)

    with col2:
        period_label = st.selectbox(
            "周期",
            list(PERIOD_OPTIONS.keys()),
            key="sync_period",
        )

        period = PERIOD_OPTIONS[period_label]

        default_end = date.today()
        default_start = default_end - timedelta(days=365)

        start = st.date_input("开始日期", value=default_start, key="sync_start")
        end = st.date_input("结束日期", value=default_end, key="sync_end")

        if start > end:
            st.error("开始日期不能晚于结束日期。")

            return

    st.divider()

    c1, c2, c3 = st.columns(3)

    with c1:
        incremental = st.checkbox(
            "增量模式（从库内最新交易日的次日开始拉）",
            value=True,
            key="sync_incremental",
            disabled=period != "d",
            help="仅日线支持增量；分钟线请用完整区间重采。",
        )

    with c2:
        ensure_calendar = st.checkbox(
            "自动保障交易日历",
            value=True,
            key="sync_calendar",
            help="同步前把交易日历补齐到结束日（增量模式推荐开启）。",
        )

    with c3:
        with_factors = st.checkbox(
            "同步复权因子",
            value=True,
            key="sync_factors",
        )

    if not codes:
        st.warning("请至少选择一只股票。")

        return

    note = (
        f"{len(codes)} 只 · {period_label} · "
        f"{start:%Y-%m-%d} ~ {end:%Y-%m-%d} · "
        f"{'增量' if incremental else '全量'}"
    )

    st.caption(note)

    if st.button(
        "🚀 开始同步",
        type="primary",
        key="btn_sync",
    ):
        with st.spinner("正在同步行情数据，请稍候……"):
            result = run_daily_sync(
                codes=codes,
                start=start.strftime("%Y-%m-%d"),
                end=end.strftime("%Y-%m-%d"),
                period=period,
                adjustflag="3",
                with_factors=with_factors,
                incremental=incremental,
                ensure_calendar=ensure_calendar,
            )

        summary = result["summary"]

        m1, m2, m3, m4 = st.columns(4)
        m1.metric("待同步", f"{summary['total']} 只")
        m2.metric("成功", f"{summary['success']} 只")
        m3.metric("跳过", f"{summary['skipped']} 只")
        m4.metric("失败", f"{summary['failed']} 只")

        if result["calendar"]:
            st.info(f"交易日历：{result['calendar']}")

        rows_out = []

        for item in result["results"]:
            rows_out.append(
                {
                    "股票代码": item.get("stock_code", item.get("code", "")),
                    "状态": item.get("status", ""),
                    "记录数": item.get("record_count", 0),
                    "说明": item.get("message", ""),
                }
            )

        st.dataframe(
            pd.DataFrame(rows_out),
            use_container_width=True,
            hide_index=True,
        )

        st.success("同步完成，可在「同步日志」页签查看明细。")


# =========================
# 页签二：同步日志
# =========================

def _render_log_tab() -> None:
    st.subheader("同步日志")
    st.caption("最近写入 data_sync_logs 的同步记录（含 CLI 与界面触发）。")

    col1, col2 = st.columns([1, 3])

    with col1:
        limit = st.selectbox(
            "显示条数",
            [10, 50, 100, 200],
            index=1,
            key="log_limit",
        )

    with col2:
        if st.button("🔄 刷新", key="btn_log_refresh"):
            st.rerun()

    logs = get_sync_logs(limit=limit)

    if not logs:
        st.info("还没有任何同步记录。")

        return

    table = pd.DataFrame(logs)

    if not table.empty and "同步时间" in table.columns:
        table["同步时间"] = pd.to_datetime(
            table["同步时间"], errors="coerce"
        )

    st.dataframe(
        table,
        use_container_width=True,
        hide_index=True,
    )


# =========================
# 页签三：数据质量
# =========================

def _render_quality_tab() -> None:
    st.subheader("数据完整性检查")
    st.caption(
        "只读检查：缺失交易日 / 停牌日（trade_status=0）/ "
        "未知状态行（3.4 迁移前存量，建议重采回填）。"
    )

    rows = _load_active_stocks()

    if not rows:
        st.info("自选池还没有股票。")

        return

    label = _label_map(rows)

    col1, col2 = st.columns(2)

    with col1:
        check_all = st.checkbox(
            "检查全部自选池股票",
            value=True,
            key="quality_all",
        )

        if not check_all:
            picked = st.multiselect(
                "选择股票",
                list(label.keys()),
                format_func=lambda c: label[c],
                key="quality_pick",
            )

            codes = list(picked)
        else:
            codes = [r["code"] for r in rows]

    with col2:
        default_end = date.today()
        default_start = date(default_end.year, 1, 1)

        q_start = st.date_input(
            "检查区间开始",
            value=default_start,
            key="quality_start",
        )
        q_end = st.date_input(
            "检查区间结束",
            value=default_end,
            key="quality_end",
        )

        if q_start > q_end:
            st.error("开始日期不能晚于结束日期。")

            return

    if not codes:
        st.warning("请至少选择一只股票。")

        return

    if st.button(
        "🔍 运行检查",
        type="primary",
        key="btn_quality",
    ):
        results = []

        for code in codes:
            with st.spinner(f"检查 {code} ……"):
                results.append(
                    check_data_integrity(
                        code,
                        q_start.strftime("%Y-%m-%d"),
                        q_end.strftime("%Y-%m-%d"),
                        adjustflag="3",
                    )
                )

        rows_out = [
            {
                "股票代码": r["stock_code"],
                "交易日数": r["trading_days"],
                "库内行数": r["bar_count"],
                "缺失日数": len(r["missing_days"]),
                "停牌日数": len(r["suspension_days"]),
                "未知状态行": r["unknown_status_rows"],
                "日历覆盖": "是" if r["calendar_coverage"] else "否",
            }
            for r in results
        ]

        st.dataframe(
            pd.DataFrame(rows_out),
            use_container_width=True,
            hide_index=True,
        )

        if not any(r["calendar_coverage"] for r in results):
            st.warning(
                "交易日历未覆盖所选区间，缺失统计无意义。"
                "请在「同步行情」勾选“自动保障交易日历”后重试。"
            )

        for r in results:
            with st.expander(
                f"{r['stock_code']}：缺失 {len(r['missing_days'])} 天，"
                f"停牌 {len(r['suspension_days'])} 天"
            ):
                st.markdown(f"**缺失交易日**：{_fmt_days(r['missing_days'])}")
                st.markdown(f"**停牌日**：{_fmt_days(r['suspension_days'])}")
                st.caption(
                    f"区间 {r['start_date']} ~ {r['end_date']}，"
                    f"日历交易日 {r['trading_days']} 天，"
                    f"库内行 {r['bar_count']} 行。"
                )


# =========================
# 页面入口
# =========================

def render_data_sync() -> None:
    """数据同步页面入口"""

    st.title("🔄 数据同步")

    tab_sync, tab_log, tab_quality = st.tabs(
        ["同步行情", "同步日志", "数据质量"]
    )

    with tab_sync:
        _render_sync_tab()

    with tab_log:
        _render_log_tab()

    with tab_quality:
        _render_quality_tab()
