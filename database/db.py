
from pathlib import Path

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker

from database.models import Base


# 数据库文件固定放在项目 database 目录
DATABASE_PATH = Path(__file__).resolve().parent / "stockpilot.db"

DATABASE_URL = f"sqlite:///{DATABASE_PATH.as_posix()}"

engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},
    echo=False,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    expire_on_commit=False,
)


def init_db():
    """初始化数据库及数据表"""
    DATABASE_PATH.parent.mkdir(parents=True, exist_ok=True)
    Base.metadata.create_all(bind=engine)
    print(f"数据库初始化成功: {DATABASE_PATH}")


def get_db():
    """获取数据库会话"""
    return SessionLocal()
