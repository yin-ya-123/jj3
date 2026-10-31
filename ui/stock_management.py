"""股票管理页面：自选股列表、添加股票、批量导入、分组管理"""

import pandas as pd
import streamlit as st

from database.repositories import stock_repository as repo


# =========================
# 写操作提示
# =========================

def _flash(message: str, kind: str = "success") -> None:
    """写操作后暂存提示，配合 st.rerun() 刷新页面"""

    st.session_state["flash"] = (kind, message)


def _show_flash() -> None:
    """显示并清除上一次写操作的提示"""

    flash = st.session_state.get("flash")

    if flash:
        del st.session_state["flash"]

        getattr(st, flash[0])(flash[1])


# =========================
# 页面
# =========================

def render_stock_management():
    """股票管理页面"""

    _show_flash()

    tab_list, tab_add, tab_import, tab_group = st.tabs(
        ["自选股列表", "添加股票", "批量导入", "分组管理"]
    )

    groups = repo.list_groups()

    # ---------- 自选股列表 ----------
    with tab_list:
        col1, col2, col3 = st.columns([2, 2, 1])

        with col1:
            keyword = st.text_input(
                "搜索",
                placeholder="代码或名称，例如 600519 / 茅台",
                key="list_keyword",
            )

        with col2:
            group_names = ["全部分组"] + [g["name"] for g in groups]

            group_pick = st.selectbox(
                "分组",
                group_names,
                key="list_group",
            )

        with col3:
            only_active = st.checkbox(
                "只看未删除",
                value=True,
                key="list_active",
            )

        group_id = None

        if group_pick != "全部分组":
            group_id = next(
                g["id"] for g in groups if g["name"] == group_pick
            )

        rows = repo.list_stocks(
            keyword=keyword.strip() or None,
            group_id=group_id,
            only_active=only_active,
        )

        st.caption(f"共 {len(rows)} 只")

        if not rows:
            st.info("没有符合条件的股票。")
        else:
            table = pd.DataFrame(rows).rename(
                columns={
                    "code": "代码",
                    "name": "名称",
                    "market": "市场",
                    "industry": "行业",
                    "ipo_date": "上市日期",
                    "is_active": "状态",
                    "groups": "分组",
                }
            )

            table["状态"] = table["状态"].map(
                {1: "在用", 0: "已删除"}
            )

            table["分组"] = table["分组"].apply(
                lambda x: "、".join(x) if x else ""
            )

            st.dataframe(
                table,
                use_container_width=True,
                hide_index=True,
            )

            label_map = {
                r["code"]: f'{r["code"]} {r["name"] or ""}'
                for r in rows
            }

            selected = st.selectbox(
                "选择股票",
                list(label_map.keys()),
                format_func=lambda c: label_map[c],
                key="list_pick",
            )

            info = repo.get_stock(selected) or {}

            edit_col, action_col = st.columns(2)

            with edit_col:
                with st.form(f"edit_{selected}"):
                    new_name = st.text_input(
                        "名称",
                        value=info.get("name") or "",
                        key="edit_name",
                    )

                    new_industry = st.text_input(
                        "行业",
                        value=info.get("industry") or "",
                        key="edit_industry",
                    )

                    st.form_submit_button("💾 保存基本信息")

                if st.session_state.get(f"edit_{selected}"):
                    repo.update_stock(
                        selected,
                        name=new_name,
                        industry=new_industry,
                    )

                    _flash(f"已保存 {selected} 的基本信息")

                    st.rerun()

            with action_col:
                if info.get("is_active"):
                    if st.button("🗑️ 逻辑删除", key="act_delete"):
                        repo.set_active(selected, False)

                        _flash(
                            f"{selected} 已删除，历史行情数据不受影响"
                        )

                        st.rerun()
                else:
                    if st.button("♻️ 恢复", key="act_restore"):
                        repo.set_active(selected, True)

                        _flash(f"{selected} 已恢复")

                        st.rerun()

            if groups:
                target = st.selectbox(
                    "加入分组",
                    [g["name"] for g in groups],
                    key="list_group_add",
                )

                if st.button("➕ 加入分组", key="act_add_group"):
                    gid = next(
                        g["id"] for g in groups if g["name"] == target
                    )

                    added = repo.add_to_group(gid, selected)

                    if added:
                        _flash(f"{selected} 已加入分组 {target}")
                    else:
                        _flash(
                            f"{selected} 已在分组 {target} 中",
                            "info",
                        )

                    st.rerun()

    # ---------- 添加股票 ----------
    with tab_add:
        st.caption(
            f"本地全市场字典：{repo.reference_count()} 条"
            "（沪深两市，不含北交所）"
        )

        add_keyword = st.text_input(
            "搜索股票",
            placeholder="代码或名称，例如 600519 / 茅台",
            key="add_keyword",
        )

        if add_keyword.strip():
            found = repo.search_reference(
                add_keyword.strip(),
                limit=30,
            )

            if not found:
                st.info("字典里没有匹配的股票。")
            else:
                st.dataframe(
                    pd.DataFrame(found).rename(
                        columns={
                            "code": "代码",
                            "name": "名称",
                            "market": "市场",
                            "trade_status": "交易状态",
                        }
                    ).assign(
                        交易状态=lambda d: d["交易状态"].map(
                            {"1": "上市", "0": "退市"}
                        ).fillna("未知")
                    ),
                    use_container_width=True,
                    hide_index=True,
                )

                add_label = {
                    f["code"]: f'{f["code"]} {f["name"] or ""}'
                    for f in found
                }

                add_pick = st.selectbox(
                    "选择要添加的股票",
                    list(add_label.keys()),
                    format_func=lambda c: add_label[c],
                    key="add_pick",
                )

                if st.button("➕ 添加到自选池", key="btn_add"):
                    name = next(
                        f["name"]
                        for f in found
                        if f["code"] == add_pick
                    )

                    repo.add_stock(code=add_pick, name=name)

                    _flash(f"{add_pick} 已添加到自选池")

                    st.rerun()

    # ---------- 批量导入 ----------
    with tab_import:
        st.caption(
            "每行一个代码，支持 600519、sh.600519、sz.000001 等写法"
        )

        text = st.text_area(
            "股票代码",
            height=180,
            placeholder="600519\n000001\nsz.000002",
            key="import_text",
        )

        if st.button(
            "📥 批量导入",
            type="primary",
            key="btn_import",
        ):
            codes = [
                line.strip()
                for line in text.splitlines()
                if line.strip()
            ]

            if not codes:
                st.warning("请先输入股票代码。")
            else:
                result = repo.import_stocks(codes)

                message = (
                    f"新增 {result['imported']} 只，"
                    f"已存在 {result['updated']} 只"
                )

                kind = "success"

                if result["invalid"]:
                    message += (
                        f"，无效 {len(result['invalid'])} 只："
                        f"{'、'.join(result['invalid'][:10])}"
                    )

                    kind = "warning"

                _flash(message, kind)

                st.rerun()

    # ---------- 分组管理 ----------
    with tab_group:
        create_col, manage_col = st.columns(2)

        with create_col:
            st.markdown("**新建分组**")

            with st.form("new_group"):
                g_name = st.text_input(
                    "分组名称",
                    key="g_new_name",
                )

                g_desc = st.text_input(
                    "描述",
                    key="g_new_desc",
                )

                st.form_submit_button("➕ 创建")

            if st.session_state.get("new_group"):
                try:
                    repo.create_group(g_name, g_desc)

                    _flash(f"分组 {g_name} 已创建")

                    st.rerun()
                except ValueError as e:
                    st.error(str(e))

        with manage_col:
            st.markdown("**重命名 / 删除**")

            if not groups:
                st.info("还没有任何分组。")
            else:
                g_pick = st.selectbox(
                    "选择分组",
                    [g["name"] for g in groups],
                    key="g_pick",
                )

                gid = next(
                    g["id"] for g in groups if g["name"] == g_pick
                )

                current = next(
                    g for g in groups if g["id"] == gid
                )

                with st.form("rename_group"):
                    r_name = st.text_input(
                        "新名称",
                        value=current["name"],
                        key="g_rename_name",
                    )

                    r_desc = st.text_input(
                        "描述",
                        value=current["description"] or "",
                        key="g_rename_desc",
                    )

                    st.form_submit_button("💾 保存")

                if st.session_state.get("rename_group"):
                    try:
                        repo.rename_group(gid, r_name, r_desc)

                        _flash("分组已更新")

                        st.rerun()
                    except ValueError as e:
                        st.error(str(e))

                if st.button(
                    "🗑️ 删除分组",
                    key="btn_del_group",
                ):
                    repo.delete_group(gid)

                    _flash(
                        f"分组 {g_pick} 已删除，成员关系已清理"
                    )

                    st.rerun()

                st.divider()

                st.markdown("**成员管理**")

                members = repo.list_group_members(gid)

                if not members:
                    st.info("该分组还没有成员。")
                else:
                    st.dataframe(
                        pd.DataFrame(members).rename(
                            columns={
                                "code": "代码",
                                "name": "名称",
                                "market": "市场",
                            }
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )

                    m_label = {
                        m["code"]: f'{m["code"]} {m["name"]}'
                        for m in members
                    }

                    rm_pick = st.selectbox(
                        "移出成员",
                        list(m_label.keys()),
                        format_func=lambda c: m_label[c],
                        key="g_rm",
                    )

                    if st.button(
                        "➖ 移出分组",
                        key="btn_rm_member",
                    ):
                        repo.remove_from_group(gid, rm_pick)

                        _flash(f"{rm_pick} 已移出分组")

                        st.rerun()