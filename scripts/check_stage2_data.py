"""阶段 2 数据层验收脚本

用法：
    uv run --no-sync python scripts/check_stage2_data.py
"""

from data.collectors.stock_collector import StockCollector
from database.repositories import stock_repository as repo


def main():
    collector = StockCollector()

    print("=" * 50)
    print("[1] 联网查单只股票基础信息")
    info = collector.fetch_basic("600519")
    print("   ", info)

    assert info and info["code"] == "600519", "基础信息查询失败"
    assert info["name"], "股票名称为空"

    print()
    print("=" * 50)
    print("[2] 同步全市场字典")
    stats = collector.sync_reference()
    total = repo.reference_count()
    non_stock = repo.reference_non_stock_count()
    print(
        f"    提交 {stats['submitted']} 条，"
        f"去重 {stats['distinct']} 条，"
        f"库中 {total} 条，"
        f"非股票 {non_stock} 条"
    )

    assert stats["submitted"] > 0, "字典同步失败，未取到数据"
    assert stats["duplicated"] == 0, f"批次内出现重复代码 {stats['duplicated']} 个"
    assert total == stats["distinct"], "库内条数与本批去重条数不一致"
    assert non_stock == 0, f"字典中残留 {non_stock} 条非股票"

    print()
    print("=" * 50)
    print("[3] 本地搜索")
    hits = repo.search_reference("茅台")
    print("    搜 茅台 ->", hits[:3])

    assert hits, "本地搜索无结果"

    print()
    print("=" * 50)
    print("[4] 写入股票（带名称和上市日期）")
    stock = repo.add_stock(
        code=info["code"],
        name=info["name"],
        ipo_date=info["ipo_date"],
    )
    print("   ", stock)

    assert stock["name"] == info["name"]

    print()
    print("=" * 50)
    print("[5] 分组（多对多）")
    group_a = repo.create_group("验收组A")
    group_b = repo.create_group("验收组B")

    repo.add_to_group(group_a["id"], "600519")
    repo.add_to_group(group_b["id"], "600519")

    groups = repo.list_stocks(group_id=group_b["id"])
    print(f"    B 组成员：{groups}")

    assert any(s["code"] == "600519" for s in groups), "多对多分组失败"

    print()
    print("=" * 50)
    print("[6] 逻辑删除不影响历史行情")
    repo.set_active("600519", False)

    active = repo.list_stocks(only_active=True)
    all_stocks = repo.list_stocks(only_active=False)

    print(f"    有效 {len(active)} 只，全部 {len(all_stocks)} 只")

    assert len(all_stocks) > len(active), "逻辑删除未生效"

    # 还原
    repo.set_active("600519", True)
    repo.delete_group(group_a["id"])
    repo.delete_group(group_b["id"])

    print()
    print("=" * 50)
    print("[7] 批量导入")
    import_codes = ["600519", "000001", "sz.000002", "600519", "abc"]
    valid_codes = {"600519", "000001", "000002"}

    before = {s["code"] for s in repo.list_stocks(only_active=False)}

    result = repo.import_stocks(import_codes)

    after = {s["code"] for s in repo.list_stocks(only_active=False)}

    # 与数据库当前状态无关：库里没有的才算新增
    expected_new = valid_codes - before

    print(
        f"    提交 5 只，新增 {result['imported']} 只，"
        f"已存在 {result['updated']} 只，"
        f"无效 {len(result['invalid'])} 个"
    )
    print(f"    无效代码: {result['invalid']}")
    print(f"    导入前 {len(before)} 只 → 导入后 {len(after)} 只")

    assert result["imported"] == len(expected_new), "批量导入新增数不对"
    assert result["updated"] == len(valid_codes) - len(expected_new), "已存在数不对"
    assert result["invalid"] == ["abc"], "非法代码未被拦截"
    assert after - before == expected_new, "新增股票没有真正落库"
    assert len(after) == len(set(after)), "批量导入产生重复股票"
    assert len(after) == len(before) + len(expected_new), "自选池数量不对"

    print(f"    导入后自选池 {len(after)} 只，代码无重复")

    print()
    print("阶段 2 数据层验收通过")


if __name__ == "__main__":
    main()
