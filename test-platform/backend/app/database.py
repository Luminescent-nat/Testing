from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from app.config import get_settings

settings = get_settings()

# 默认使用 SQLite；生产环境可通过 DATABASE_URL 切换为 PostgreSQL
DATABASE_URL = settings.DATABASE_URL

if not DATABASE_URL.startswith("sqlite"):
    # 异步 PostgreSQL
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://")

engine = create_async_engine(
    DATABASE_URL,
    echo=False,
    pool_pre_ping=True,
)

if DATABASE_URL.startswith("sqlite"):
    # 仅针对 SQLite：开启 WAL 提升多设备并行写 + WebSocket 查询的并发能力，
    # 并设置 busy_timeout 避免 "database is locked" 立即报错。
    @event.listens_for(engine.sync_engine, "connect")
    def _set_sqlite_pragma(dbapi_connection, connection_record):
        cursor = dbapi_connection.cursor()
        try:
            cursor.execute("PRAGMA journal_mode=WAL")
            cursor.execute("PRAGMA busy_timeout=30000")
        finally:
            cursor.close()

# 异步会话工厂
AsyncSessionLocal = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
    autocommit=False,
    autoflush=False,
)

# 声明基类
Base = declarative_base()


async def get_db():
    """获取数据库会话的依赖函数"""
    async with AsyncSessionLocal() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """初始化数据库表（create_all，幂等）。

    仅负责全新部署的零命令开箱：表不存在才创建，不做结构升级。
    - 全新部署：create_all 建表后执行 `alembic stamp head` 标记基线（可选，
      不标记也不影响运行，只是首次 `alembic upgrade head` 会因表已存在而报错）；
    - 存量库结构升级：走 alembic 迁移，在 backend 目录执行 `alembic upgrade head`。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
