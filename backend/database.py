"""SQLite 数据库初始化与连接管理"""
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DATABASE_URL

# 创建引擎；check_same_thread=False 允许在 FastAPI 异步上下文 / 后台线程中使用
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})

# 会话工厂
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

# ORM 声明式基类
Base = declarative_base()


def init_db():
    """根据模型定义创建所有数据表"""
    Base.metadata.create_all(bind=engine)


def get_db():
    """FastAPI 依赖：获取数据库会话，请求结束自动关闭"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()
