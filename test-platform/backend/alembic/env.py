"""Alembic 环境：基于 app.models 的元数据做结构迁移。

URL 推导：优先环境变量 DATABASE_URL，其次 app 配置默认值；
异步驱动（sqlite+aiosqlite / postgresql+asyncpg）统一替换为同步驱动
（sqlite / postgresql），迁移走同步引擎，与应用运行时异步引擎互不影响。

注意导入顺序：app.database 在模块导入时就会用 DATABASE_URL 创建异步引擎，
因此导入 app 之前要先把环境变量规范化为异步 URL，迁移本身仍用同步 URL。
"""

import os
import sys
from logging.config import fileConfig

from alembic import context
from sqlalchemy import engine_from_config, event, pool

# 让 alembic 在 backend 目录下能找到 app 包
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# 迁移目标 URL（同步驱动形式在 _sync_database_url 中推导）
_REQUESTED_URL = os.environ.get("DATABASE_URL")


def _to_async_url(url: str) -> str:
    """转换为应用运行时的异步驱动 URL（供 app.database 导入期建引擎）。"""
    if url.startswith("sqlite") and "+aiosqlite" not in url:
        return url.replace("sqlite://", "sqlite+aiosqlite://", 1)
    if url.startswith("postgresql://"):
        return url.replace("postgresql://", "postgresql+asyncpg://", 1)
    return url


def _sync_database_url() -> str:
    """迁移使用的同步驱动 URL。"""
    url = _REQUESTED_URL or get_settings().DATABASE_URL
    return url.replace("+aiosqlite", "").replace("+asyncpg", "")


# app.database 导入即建异步引擎：先把环境变量规范化为异步 URL，避免导入失败
if _REQUESTED_URL:
    os.environ["DATABASE_URL"] = _to_async_url(_REQUESTED_URL)

from app.config import get_settings  # noqa: E402
from app.models import Base  # noqa: E402  全量模型元数据

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """离线模式：只生成 SQL 脚本，不连接数据库。"""
    context.configure(
        url=_sync_database_url(),
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        render_as_batch=True,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    """在线模式：连接数据库执行迁移。"""
    configuration = config.get_section(config.config_ini_section, {})
    configuration["sqlalchemy.url"] = _sync_database_url()
    connectable = engine_from_config(
        configuration,
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    if connectable.dialect.name == "sqlite":
        # 迁移连接也启用与运行时一致的 SQLite PRAGMA（foreign_keys=ON / WAL /
        # busy_timeout），使迁移期间的外键与表重建行为可验证。
        # 注意：SQLite 要求 foreign_keys 只在连接建立（事务外）时设置；本迁移的
        # batch 操作仅涉及索引，不触发影子表重建。若未来新增需要重建被引用表的
        # batch 迁移，必须在事务外显式关闭外键、完成重建后再恢复（见设计第 5 节
        # “迁移事务中按 SQLite 要求管理外键与表重建”）。
        from app.database import configure_sqlite_connection

        event.listen(connectable, "connect", configure_sqlite_connection)

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            # SQLite 不支持直接 ALTER COLUMN/DROP COLUMN，
            # 用 batch 模式（建影子表搬迁）兼容存量库结构升级
            render_as_batch=True,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
