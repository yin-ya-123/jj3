"""股票、分组、全市场字典的数据访问"""

from datetime import date, datetime

from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from database.db import SessionLocal
from database.models import (
    Stock,
    StockGroup,
    StockGroupMember,
    StockReference,
)
from data.utils import market_of, normalize_code


# =========================
# 股票
# =========================

def list_stocks(
    keyword: str | None = None,
    group_id: int | None = None,
    only_active: bool = True,
) -> list[dict]:
    """列出股票，可按关键字和分组过滤"""

    with SessionLocal() as session:
        stmt = select(Stock)

        if only_active:
            stmt = stmt.where(Stock.is_active == 1)

        if keyword:
            text = f"%{keyword.strip()}%"

            stmt = stmt.where(
                or_(
                    Stock.code.like(text),
                    Stock.name.like(text),
                )
            )

        if group_id is not None:
            member_codes = select(StockGroupMember.stock_code).where(
                StockGroupMember.group_id == group_id
            )

            stmt = stmt.where(Stock.code.in_(member_codes))

        stmt = stmt.order_by(Stock.code)

        stocks = list(session.scalars(stmt).all())

        groups_map = _group_map(session)

        return [
            {
                "code": stock.code,
                "name": stock.name,
                "market": stock.market,
                "industry": stock.industry,
                "ipo_date": stock.ipo_date,
                "is_active": stock.is_active,
                "groups": groups_map.get(stock.code, []),
            }
            for stock in stocks
        ]


def get_stock(code: str) -> dict | None:
    """查询单只股票"""

    code = normalize_code(code)

    with SessionLocal() as session:
        stock = session.get(Stock, code)

        if stock is None:
            return None

        return {
            "code": stock.code,
            "name": stock.name,
            "market": stock.market,
            "industry": stock.industry,
            "ipo_date": stock.ipo_date,
            "is_active": stock.is_active,
            "updated_at": stock.updated_at,
        }


def add_stock(
    code: str,
    name: str | None = None,
    industry: str | None = None,
    ipo_date=None,
) -> dict:
    """新增或重新启用股票（纯存储，不联网）"""

    code = normalize_code(code)

    with SessionLocal.begin() as session:
        stock = session.get(Stock, code)

        if stock is None:
            stock = Stock(code=code, market=market_of(code))
            session.add(stock)

        stock.is_active = 1
        stock.updated_at = datetime.now()

        if name:
            stock.name = str(name).strip()[:50]

        if industry:
            stock.industry = str(industry).strip()[:50]

        if ipo_date:
            stock.ipo_date = _parse_date(ipo_date)

    return get_stock(code)


def update_stock(code: str, **fields) -> dict:
    """更新股票基本信息，只接受白名单字段"""

    code = normalize_code(code)

    allowed = {"name", "industry"}

    with SessionLocal.begin() as session:
        stock = session.get(Stock, code)

        if stock is None:
            raise ValueError(f"股票不存在: {code}")

        for key, value in fields.items():
            if key not in allowed or value is None:
                continue

            setattr(stock, key, str(value).strip()[:50])

        stock.updated_at = datetime.now()

    return get_stock(code)


def set_active(code: str, active: bool = True) -> bool:
    """逻辑删除或恢复股票，历史行情不受影响"""

    code = normalize_code(code)

    with SessionLocal.begin() as session:
        stock = session.get(Stock, code)

        if stock is None:
            return False

        stock.is_active = 1 if active else 0
        stock.updated_at = datetime.now()

    return True


# =========================
# 分组
# =========================

def list_groups() -> list[dict]:
    """列出全部分组及成员数量"""

    with SessionLocal() as session:
        rows = session.execute(
            select(
                StockGroup,
                func.count(StockGroupMember.stock_code),
            )
            .outerjoin(
                StockGroupMember,
                StockGroupMember.group_id == StockGroup.id,
            )
            .group_by(StockGroup.id)
            .order_by(StockGroup.id)
        ).all()

        return [
            {
                "id": group.id,
                "name": group.name,
                "description": group.description,
                "member_count": count,
                "created_at": group.created_at,
            }
            for group, count in rows
        ]


def create_group(name: str, description: str | None = None) -> dict:
    """新建分组"""

    name = str(name).strip()

    if not name:
        raise ValueError("分组名称不能为空")

    with SessionLocal.begin() as session:
        exists = session.scalar(
            select(StockGroup.id).where(StockGroup.name == name)
        )

        if exists:
            raise ValueError(f"分组已存在: {name}")

        group = StockGroup(name=name[:50], description=description)
        session.add(group)
        session.flush()

        group_id = group.id

    return {
        "id": group_id,
        "name": name,
        "description": description,
        "member_count": 0,
    }


def rename_group(
    group_id: int,
    name: str,
    description: str | None = None,
) -> dict:
    """重命名分组"""

    name = str(name).strip()

    if not name:
        raise ValueError("分组名称不能为空")

    with SessionLocal.begin() as session:
        group = session.get(StockGroup, group_id)

        if group is None:
            raise ValueError(f"分组不存在: {group_id}")

        clash = session.scalar(
            select(StockGroup.id).where(
                StockGroup.name == name,
                StockGroup.id != group_id,
            )
        )

        if clash:
            raise ValueError(f"分组已存在: {name}")

        group.name = name[:50]
        group.description = description

    return {
        "id": group_id,
        "name": name,
        "description": description,
    }


def delete_group(group_id: int) -> bool:
    """删除分组，先清成员再删组"""

    with SessionLocal.begin() as session:
        session.execute(
            delete(StockGroupMember).where(
                StockGroupMember.group_id == group_id
            )
        )

        group = session.get(StockGroup, group_id)

        if group is None:
            return False

        session.delete(group)

    return True


def add_to_group(group_id: int, code: str) -> bool:
    """把股票加入分组，已存在返回 False"""

    code = normalize_code(code)

    with SessionLocal.begin() as session:
        if session.get(StockGroup, group_id) is None:
            raise ValueError(f"分组不存在: {group_id}")

        if session.get(Stock, code) is None:
            raise ValueError(f"股票不存在: {code}")

        exists = session.scalar(
            select(StockGroupMember.stock_code).where(
                StockGroupMember.group_id == group_id,
                StockGroupMember.stock_code == code,
            )
        )

        if exists:
            return False

        session.add(
            StockGroupMember(group_id=group_id, stock_code=code)
        )

    return True


def remove_from_group(group_id: int, code: str) -> bool:
    """把股票移出分组"""

    code = normalize_code(code)

    with SessionLocal.begin() as session:
        result = session.execute(
            delete(StockGroupMember).where(
                StockGroupMember.group_id == group_id,
                StockGroupMember.stock_code == code,
            )
        )

        return result.rowcount > 0


def set_group_members(group_id: int, codes: list) -> int:
    """用给定股票列表整体覆盖分组成员"""

    codes = list(dict.fromkeys(normalize_code(c) for c in codes))

    with SessionLocal.begin() as session:
        if session.get(StockGroup, group_id) is None:
            raise ValueError(f"分组不存在: {group_id}")

        for code in codes:
            if session.get(Stock, code) is None:
                raise ValueError(f"股票不存在: {code}")

        session.execute(
            delete(StockGroupMember).where(
                StockGroupMember.group_id == group_id
            )
        )

        for code in codes:
            session.add(
                StockGroupMember(group_id=group_id, stock_code=code)
            )

    return len(codes)


def list_group_members(group_id: int) -> list[dict]:
    """列出分组内成员"""

    with SessionLocal() as session:
        rows = session.execute(
            select(
                StockGroupMember.stock_code,
                Stock.name,
                Stock.market,
            )
            .join(Stock, Stock.code == StockGroupMember.stock_code)
            .where(StockGroupMember.group_id == group_id)
            .order_by(StockGroupMember.stock_code)
        ).all()

        return [
            {
                "code": code,
                "name": name or "未设置",
                "market": market,
            }
            for code, name, market in rows
        ]


# =========================
# 全市场字典
# =========================

def search_reference(keyword: str, limit: int = 50) -> list[dict]:
    """在本地全市场字典里搜索代码或名称"""

    text = f"%{str(keyword).strip()}%"

    with SessionLocal() as session:
        stmt = (
            select(StockReference)
            .where(
                or_(
                    StockReference.code.like(text),
                    StockReference.name.like(text),
                )
            )
            .order_by(StockReference.code)
            .limit(limit)
        )

        rows = list(session.scalars(stmt).all())

        return [
            {
                "code": row.code,
                "name": row.name,
                "market": row.market,
                "trade_status": row.trade_status,
            }
            for row in rows
        ]


def upsert_reference(rows: list[dict]) -> int:
    """批量写入或更新全市场字典"""

    records = []

    for row in rows:
        if not row.get("code"):
            continue

        code = normalize_code(row["code"])

        records.append({
            "code": code,
            "name": row.get("name") or None,
            "market": row.get("market") or market_of(code),
            "trade_status": row.get("trade_status") or None,
        })

    if not records:
        return 0

    with SessionLocal.begin() as session:
        statement = sqlite_insert(StockReference).values(records)

        statement = statement.on_conflict_do_update(
            index_elements=["code"],
            set_={
                "name": statement.excluded.name,
                "market": statement.excluded.market,
                "trade_status": statement.excluded.trade_status,
                "updated_at": func.current_timestamp(),
            },
        )

        session.execute(statement)

    return len(records)


def reference_count() -> int:
    """字典条目数量"""

    with SessionLocal() as session:
        return session.scalar(
            select(func.count(StockReference.code))
        ) or 0


# =========================
# 内部工具
# =========================

def _group_map(session) -> dict:
    """代码到分组名列表的映射"""

    rows = session.execute(
        select(StockGroupMember.stock_code, StockGroup.name)
        .join(StockGroup, StockGroup.id == StockGroupMember.group_id)
    ).all()

    result = {}

    for code, name in rows:
        result.setdefault(code, []).append(name)

    return result


def _parse_date(value) -> date | None:
    """把字符串转成日期，失败返回 None"""

    if value is None or value == "":
        return None

    if isinstance(value, date):
        return value

    try:
        return datetime.strptime(
            str(value).strip(), "%Y-%m-%d"
        ).date()
    except ValueError:
        return None