"""股票字典写入逻辑测试（离线，用临时库）"""

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base
from database.repositories import stock_repository as repo


def _tmp_session(tmp_path, monkeypatch):
    engine = create_engine(f"sqlite:///{tmp_path / 'test.db'}")
    Base.metadata.create_all(engine)
    monkeypatch.setattr(repo, "SessionLocal", sessionmaker(bind=engine))


def test_upsert_reference_dedup(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    stats = repo.upsert_reference(
        [
            {"code": "600519", "name": "贵州茅台", "market": "SH", "trade_status": "1"},
            {"code": "600519", "name": "贵州茅台", "market": "SH", "trade_status": "1"},
        ]
    )

    assert stats == {"submitted": 2, "distinct": 1, "duplicated": 1}
    assert repo.reference_count() == 1


def test_upsert_reference_keeps_last(tmp_path, monkeypatch):
    _tmp_session(tmp_path, monkeypatch)

    repo.upsert_reference([{"code": "000001", "name": "上证指数", "market": "SH"}])
    repo.upsert_reference([{"code": "000001", "name": "平安银行", "market": "SZ"}])

    assert repo.reference_count() == 1
    assert repo.reference_non_stock_count() == 0