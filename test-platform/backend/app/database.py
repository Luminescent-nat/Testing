from sqlalchemy import event
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base
from sqlalchemy.pool import NullPool
from app.config import get_settings

import asyncio
import os
import shutil
import tempfile
from pathlib import Path

import sqlalchemy as sa
from sqlalchemy import create_engine
from sqlalchemy.dialects import sqlite as sqlite_dialect

from alembic import command as alembic_command
from alembic.config import Config as AlembicConfig

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

def configure_sqlite_connection(dbapi_connection, connection_record=None):
    """SQLite 每个连接必须执行的 PRAGMA（T-02 / 设计文档第 5 节）。

    - foreign_keys=ON：SQLite 默认关闭外键，必须由数据库实际拒绝孤儿行与
      违反唯一约束的写入；该 PRAGMA 是「每连接」设置，且不能在事务内切换，
      因此只能在 connect 事件（事务外）执行。
    - journal_mode=WAL / busy_timeout=30000：保留原有并发与锁等待能力。

    该函数同时供运行时异步引擎、alembic 迁移连接和验证脚本/单元测试直接复用；
    connection_record 保留 SQLAlchemy connect 事件签名，省略时便于裸连接调用。
    """
    cursor = dbapi_connection.cursor()
    try:
        cursor.execute("PRAGMA foreign_keys=ON")
        cursor.execute("PRAGMA journal_mode=WAL")
        cursor.execute("PRAGMA busy_timeout=30000")
    finally:
        cursor.close()


if DATABASE_URL.startswith("sqlite"):
    # 仅针对 SQLite：开启外键强制、WAL 提升多设备并行写 + WebSocket 查询的并发能力，
    # 并设置 busy_timeout 避免 "database is locked" 立即报错。
    # 直接注册可复用 helper，便于 event.contains() 与隔离测试核对注册关系。
    event.listen(engine.sync_engine, "connect", configure_sqlite_connection)

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


BACKEND_DIR = Path(__file__).resolve().parents[1]
_INITIAL_REVISION = "0817df993d8b"


class SchemaMismatchError(RuntimeError):
    """数据库结构与 app.models 不一致（stamp 前置校验 / 升级后核验失败）。"""


def _sync_database_url() -> str:
    """迁移/结构核对使用的同步驱动 URL（与应用异步 URL 指向同一数据库）。

    优先读取当前 DATABASE_URL 环境变量（alembic/env.py 使用同一来源，
    保证进程内升级与结构核验指向同一库）；未设置时回退模块导入期配置。
    """
    url = os.environ.get("DATABASE_URL") or DATABASE_URL
    return url.replace("+aiosqlite", "").replace("+asyncpg", "")


def _alembic_config() -> AlembicConfig:
    """进程内运行 alembic 命令的配置（URL 由 alembic/env.py 推导）。"""
    cfg = AlembicConfig(str(BACKEND_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BACKEND_DIR / "alembic"))
    return cfg


def _alembic_upgrade_head_sync() -> None:
    alembic_command.upgrade(_alembic_config(), "head")


def _alembic_stamp_sync(revision: str) -> None:
    alembic_command.stamp(_alembic_config(), revision)


def _alembic_stamp_head_sync() -> None:
    _alembic_stamp_sync("head")


def _revision_fingerprint(revision: str) -> dict:
    """在隔离临时库上执行 `alembic upgrade <revision>`，返回该 revision 的结构指纹。

    用于判定无 alembic_version 的存量库到底对应哪个历史 revision（例如初始
    revision 0817df993d8b），从而 stamp 正确的基线后再 upgrade head。
    """
    tmpdir = Path(tempfile.mkdtemp(prefix="schema_ref_"))
    db = tmpdir / "ref.db"
    saved = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = "sqlite:///" + db.as_posix()
    try:
        alembic_command.upgrade(_alembic_config(), revision)
        engine = create_engine("sqlite:///" + db.as_posix(), poolclass=NullPool)
        try:
            with engine.connect() as conn:
                return _schema_fingerprint(conn)
        finally:
            engine.dispose()
    finally:
        if saved is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = saved
        shutil.rmtree(tmpdir, ignore_errors=True)


def _schema_fingerprint(conn) -> dict:
    """对数据库当前结构取 DDL 指纹：逐表/列/索引/外键/唯一/CHECK/PK。

    alembic_version 表不计入指纹（它是迁移状态而非业务结构）。
    """
    insp = sa.inspect(conn)
    fingerprint: dict = {}
    for table in sorted(insp.get_table_names()):
        if table == "alembic_version":
            continue
        columns = {
            col["name"]: {
                "type": col["type"].compile(dialect=sqlite_dialect.dialect()),
                "nullable": bool(col["nullable"]),
                "default": col["default"],
            }
            for col in insp.get_columns(table)
        }
        pk = insp.get_pk_constraint(table)
        indexes = sorted(
            (idx["name"], tuple(idx["column_names"]), bool(idx["unique"]))
            for idx in insp.get_indexes(table)
        )
        foreign_keys = sorted(
            (
                tuple(sorted(fk["constrained_columns"])),
                fk["referred_table"],
                tuple(sorted(fk["referred_columns"])),
            )
            for fk in insp.get_foreign_keys(table)
        )
        uniques = sorted(
            (uq["name"], tuple(uq["column_names"]))
            for uq in insp.get_unique_constraints(table)
        )
        checks = sorted(
            (chk["name"], chk["sqltext"]) for chk in insp.get_check_constraints(table)
        )
        fingerprint[table] = {
            "columns": columns,
            "primary_key": tuple(pk["constrained_columns"] or []),
            "indexes": indexes,
            "foreign_keys": foreign_keys,
            "uniques": uniques,
            "checks": checks,
        }
    return fingerprint


def _reference_fingerprint() -> dict:
    """以 app.models 元数据在内存 SQLite 中建表，得到「期望结构」指纹。"""
    engine = create_engine("sqlite://", poolclass=NullPool)
    try:
        with engine.connect() as conn:
            Base.metadata.create_all(conn)
            return _schema_fingerprint(conn)
    finally:
        engine.dispose()


def _fingerprint_diffs(current: dict, reference: dict) -> list:
    """对比两组结构指纹，返回人类可读差异列表（仅结构名，不含数据）。"""
    diffs: list = []
    for table in sorted(set(reference) | set(current)):
        if table not in current:
            diffs.append(f"缺少表: {table}")
            continue
        if table not in reference:
            diffs.append(f"多余表: {table}")
            continue
        cur, ref = current[table], reference[table]
        for col in sorted(set(ref["columns"]) | set(cur["columns"])):
            if col not in cur["columns"]:
                diffs.append(f"表 {table} 缺少列: {col}")
            elif col not in ref["columns"]:
                diffs.append(f"表 {table} 多余列: {col}")
            elif cur["columns"][col] != ref["columns"][col]:
                diffs.append(
                    f"表 {table} 列 {col} 定义不一致: "
                    f"db={cur['columns'][col]} models={ref['columns'][col]}"
                )
        if cur["primary_key"] != ref["primary_key"]:
            diffs.append(f"表 {table} 主键不一致: db={cur['primary_key']} models={ref['primary_key']}")
        if cur["indexes"] != ref["indexes"]:
            diffs.append(f"表 {table} 索引不一致: db={cur['indexes']} models={ref['indexes']}")
        if cur["foreign_keys"] != ref["foreign_keys"]:
            diffs.append(f"表 {table} 外键不一致: db={cur['foreign_keys']} models={ref['foreign_keys']}")
        if cur["uniques"] != ref["uniques"]:
            diffs.append(f"表 {table} 唯一约束不一致: db={cur['uniques']} models={ref['uniques']}")
        if cur["checks"] != ref["checks"]:
            diffs.append(f"表 {table} CHECK 约束不一致: db={cur['checks']} models={ref['checks']}")
    return diffs


def _verify_schema_matches_models(action: str) -> None:
    """当前 DATABASE_URL 的库结构必须与 app.models 完全一致（仅 SQLite）。"""
    url = _sync_database_url()
    if not url.startswith("sqlite"):
        return  # 非 SQLite 的类型编译差异大，指纹核验仅覆盖 SQLite 部署
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            current = _schema_fingerprint(conn)
        diffs = _fingerprint_diffs(current, _reference_fingerprint())
        if diffs:
            raise SchemaMismatchError(
                f"数据库结构与 app.models 不一致（init_db action={action}）："
                + "；".join(diffs[:20])
            )
    finally:
        engine.dispose()


def _init_db_sync() -> str:
    """生产启动迁移初始化（同步部分，见 init_db 文档）。"""
    url = _sync_database_url()
    engine = create_engine(url, poolclass=NullPool)
    try:
        with engine.connect() as conn:
            all_tables = sa.inspect(conn).get_table_names()
        user_tables = [t for t in all_tables if t != "alembic_version"]
        has_version = "alembic_version" in all_tables

        if not user_tables:
            # 空库（新装）：只走 alembic upgrade head，不再 create_all
            _alembic_upgrade_head_sync()
            action = "empty-upgrade-head"
        elif not has_version:
            # 已有业务表但无 alembic_version（历史 create_all 建立的存量库）：
            # 先做完整 DDL 指纹比对（逐表/列/索引/外键/唯一/CHECK）。
            #   - 与 head（app.models）完全一致 → stamp head 后 upgrade head；
            #   - 否则若与初始 revision 结构完全一致（典型：引入幂等表之前的
            #     存量库）→ stamp 初始 revision 后 upgrade head 补齐后续 revision；
            #   - 两者都不一致 → 明确失败，绝不静默 stamp 一套未登记结构。
            with engine.connect() as conn:
                current = _schema_fingerprint(conn)
            head_diffs = _fingerprint_diffs(current, _reference_fingerprint())
            if not head_diffs:
                _alembic_stamp_head_sync()
                _alembic_upgrade_head_sync()
                action = "legacy-stamp-head-then-upgrade"
            else:
                initial_diffs = _fingerprint_diffs(current, _revision_fingerprint(_INITIAL_REVISION))
                if initial_diffs:
                    raise SchemaMismatchError(
                        "存量库结构与 app.models（head）及初始 revision 均不一致，拒绝 stamp："
                        "head 差异=" + "；".join(head_diffs[:10])
                        + " | 初始 revision 差异=" + "；".join(initial_diffs[:10])
                    )
                _alembic_stamp_sync(_INITIAL_REVISION)
                _alembic_upgrade_head_sync()
                action = "legacy-stamp-initial-then-upgrade"
        else:
            # 已登记迁移版本：升级到 head（已在 head 时为幂等 no-op）
            _alembic_upgrade_head_sync()
            action = "upgrade-head"
        return action
    finally:
        engine.dispose()


async def init_db():
    """生产启动数据库初始化（V1-05：新装/存量/升级三态闭环，不再 create_all）。

    - 空库（无业务表）：执行 `alembic upgrade head`，新装只走 Alembic，
      不再由应用建立一套未登记结构；
    - 已有业务表但无 alembic_version（历史 create_all 存量库）：
      先做完整 DDL 指纹比对（逐表/列/索引/外键/唯一/CHECK）：
        * 与 head（app.models）完全一致 → `stamp head` 并 upgrade；
        * 否则若与初始 revision 0817df993d8b 结构完全一致（引入幂等表之前
          的典型存量库）→ `stamp 0817df993d8b` 后 upgrade head 补齐后续 revision；
        * 两者都不一致 → 明确抛出 SchemaMismatchError 拒绝启动，绝不静默 stamp；
    - 已有迁移版本：执行 `alembic upgrade head`（幂等，已在 head 时为 no-op）。
    - 全部路径结束后核验库结构与 app.models 一致（SQLite）。

    测试环境不受影响：tests/conftest.py 直接使用 Base.metadata.create_all
    建立每用例独立库，不调用本函数。
    """
    action = await asyncio.to_thread(_init_db_sync)
    await asyncio.to_thread(_verify_schema_matches_models, action)


async def close_db():
    """关闭数据库连接"""
    await engine.dispose()
