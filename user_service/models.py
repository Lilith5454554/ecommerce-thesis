from sqlalchemy import create_engine, Column, String, DateTime
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from datetime import datetime
import os


# 从环境变量读取，CI中会设置 DATABASE_URL，配置数据库连接地址
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql://postgres:postgres@localhost:5432/test_db"  # 默认用localhost
)



engine = create_engine(DATABASE_URL)#创建SQLAlchemy引擎，负责管理数据库连接池和执行SQL
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)#创建会话工厂
Base = declarative_base()#创建一个基类，所有数据库模型类都继承它

class User(Base):
    __tablename__ = "users"# 指定数据库中的表名

    id = Column(String, primary_key=True, index=True)
    username = Column(String, unique=True, index=True, nullable=False)
    email = Column(String, unique=True, index=True, nullable=False)
    password_hash = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

def get_db():
    db = SessionLocal()
    try:
        yield db # 提供会话给使用方
    finally:
        db.close()# 确保会话被关闭
#FastAPI的依赖注入函数，用于自动管理数据库会话生命周期

def init_db():
    Base.metadata.create_all(bind=engine)
# 初始化数据库。根据定义的模型类，在数据库中创建所有表
