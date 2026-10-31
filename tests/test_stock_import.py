"""股票批量导入测试（离线，用临时库）"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base
from database.repositories import stock_repository as repo


def _tmp_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(repo, "SessionLocal", sessionmaker(bind=engine))


def _seed_reference(rows):
    repo.upsert_reference(rows)


def test_import_new_stock_takes_name_from_reference(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)
    _seed_reference([
        {"code": "600519", "name": "贵州茅台", "market": "SH", "trade_status": "1"},
    ])

    result = repo.import_stocks(["600519"])

    assert result == {"imported": 1, "updated": 0, "invalid": []}

    stock = repo.get_stock("600519")
    assert stock["name"] == "贵州茅台"
    assert stock["market"] == "SH"
    assert stock["is_active"] == 1


def test_import_twice_creates_no_duplicate(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)
    _seed_reference([
        {"code": "600519", "name": "贵州茅台", "market": "SH", "trade_status": "1"},
    ])

    repo.import_stocks(["600519"])
    result = repo.import_stocks(["600519", "600519", " sh.600519 "])

    assert result == {"imported": 0, "updated": 1, "invalid": []}
    assert len(repo.list_stocks(only_active=False)) == 1


def test_import_reactivates_deleted_stock(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)
    _seed_reference([
        {"code": "600519", "name": "贵州茅台", "market": "SH", "trade_status": "1"},
    ])

    repo.add_stock("600519", name="贵州茅台")
    repo.set_active("600519", False)

    repo.import_stocks(["600519"])

    assert repo.get_stock("600519")["is_active"] == 1


def test_import_rejects_invalid_and_unknown_codes(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)
    _seed_reference([
        {"code": "600519", "name": "贵州茅台", "market": "SH", "trade_status": "1"},
    ])

    result = repo.import_stocks(["600519", "abc", "", "999999"])

    assert result["imported"] == 1
    assert sorted(result["invalid"]) == ["", "999999", "abc"]
    assert repo.get_stock("999999") is None


def test_import_market_comes_from_reference(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)
    _seed_reference([
        {"code": "920002", "name": "万达轴承", "market": "BJ", "trade_status": "1"},
    ])

    repo.import_stocks(["920002"])

    assert repo.get_stock("920002")["market"] == "BJ"