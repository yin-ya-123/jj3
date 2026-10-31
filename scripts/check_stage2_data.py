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
    count = collector.sync_reference()
    print(f"    写入 {count} 条，库中现有 {repo.reference_count()} 条")

    assert count > 0, "字典同步失败"
    assert repo.reference_count() == count, "字典条数不一致"

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
    print("阶段 2 数据层验收通过")


if __name__ == "__main__":
    main()