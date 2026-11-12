"""T-02 迁移契约单元测试（先于实现编写的红测）。

覆盖 docs/design/scheduler-and-data.md 第 5 节：
- SQLite 每个连接启用 PRAGMA foreign_keys=ON，并保留 WAL / busy_timeout；
- users.username、devices.serial_number 唯一约束由数据库实际执行；
- 非法外键写入必须由数据库拒绝（而不是靠应用先查后写）。

实现前：app.database 没有 configure_sqlite_connection，生产引擎连接事件只设置
WAL / busy_timeout，SQLite 默认 foreign_keys=OFF，非法外键可以写入。
"""
import sqlite3
from pathlib import Path

import pytest
from sqlalchemy import create_engine, event, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.pool import NullPool

from app import database
from app.models import Base  # noqa: F401  确保全部模型元数据已注册


def _make_engine(db_path: Path, apply_pragma: bool):
    """在临时目录建同步引擎；apply_pragma=False 用作「修复前」对照组。"""
    eng = create_engine(f"sqlite:///{db_path.as_posix()}", poolclass=NullPool)
    if apply_pragma:
        event.listen(eng, "connect", database.configure_sqlite_connection)
    return eng


def test_configure_sqlite_connection_enables_foreign_keys_wal_and_busy_timeout(tmp_path):
    """可复用 helper 必须同时设置 FK=ON、WAL、busy_timeout。"""
    raw = sqlite3.connect(tmp_path / "direct.db")
    try:
        database.configure_sqlite_connection(raw)
        assert raw.execute("PRAGMA foreign_keys").fetchone()[0] == 1
        assert raw.execute("PRAGMA journal_mode").fetchone()[0].lower() == "wal"
        assert raw.execute("PRAGMA busy_timeout").fetchone()[0] >= 30000
    finally:
        raw.close()


def test_runtime_engine_registers_pragma_listener():
    """生产引擎的 connect 事件必须挂上该 helper（不连接真实库，仅查注册关系）。"""
    assert database.DATABASE_URL.startswith("sqlite")
    assert event.contains(
        database.engine.sync_engine, "connect", database.configure_sqlite_connection
    )


def test_pragma_is_applied_on_every_new_connection(tmp_path):
    """PRAGMA foreign_keys 是每连接设置，两个独立连接都必须为 1。"""
    eng = _make_engine(tmp_path / "every.db", apply_pragma=True)
    try:
        for _ in range(2):
            with eng.connect() as conn:
                assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
                assert conn.exec_driver_sql("PRAGMA journal_mode").scalar().lower() == "wal"
    finally:
        eng.dispose()


@pytest.fixture
def contract_engine(tmp_path):
    eng = _make_engine(tmp_path / "contract.db", apply_pragma=True)
    Base.metadata.create_all(eng)
    try:
        yield eng
    finally:
        eng.dispose()


def _insert_user(conn, username):
    conn.execute(
        text(
            "INSERT INTO users (username, password_hash, role, status) "
            "VALUES (:u, 'x', 'user', 'active')"
        ),
        {"u": username},
    )


def test_unique_username_and_serial_number_are_enforced_by_database(contract_engine):
    with contract_engine.begin() as conn:
        _insert_user(conn, "dup")
        conn.execute(
            text(
                "INSERT INTO devices (serial_number, status, pc_identifier) "
                "VALUES ('S-1', 'offline', 'pc')"
            )
        )

    with pytest.raises(IntegrityError):
        with contract_engine.begin() as conn:
            _insert_user(conn, "dup")

    with pytest.raises(IntegrityError):
        with contract_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO devices (serial_number, status, pc_identifier) "
                    "VALUES ('S-1', 'offline', 'pc')"
                )
            )


def test_illegal_foreign_key_write_is_rejected_with_pragma_on(contract_engine):
    with contract_engine.begin() as conn:
        _insert_user(conn, "owner")
        conn.execute(
            text(
                "INSERT INTO devices (serial_number, status, pc_identifier, owner_id) "
                "VALUES ('S-ok', 'offline', 'pc', "
                "(SELECT id FROM users WHERE username='owner'))"
            )
        )

    with pytest.raises(IntegrityError, match="FOREIGN KEY constraint failed"):
        with contract_engine.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO devices (serial_number, status, pc_identifier, owner_id) "
                    "VALUES ('S-orphan', 'offline', 'pc', 999999)"
                )
            )


def test_raw_sqlite_without_pragma_allows_orphan_rows(tmp_path):
    """对照/缺陷证据：未启用 PRAGMA 时 SQLite 默认 FK=OFF，孤儿行可写入。"""
    eng = _make_engine(tmp_path / "no_pragma.db", apply_pragma=False)
    Base.metadata.create_all(eng)
    try:
        with eng.connect() as conn:
            assert conn.exec_driver_sql("PRAGMA foreign_keys").scalar() == 0
        with eng.begin() as conn:
            conn.execute(
                text(
                    "INSERT INTO devices (serial_number, status, pc_identifier, owner_id) "
                    "VALUES ('S-orphan', 'offline', 'pc', 999999)"
                )
            )
        with eng.connect() as conn:
            assert conn.exec_driver_sql(
                "SELECT count(*) FROM devices WHERE owner_id=999999"
            ).scalar() == 1
    finally:
        eng.dispose()


async def test_clean_empty_db_startup_seeding_survives_foreign_keys_on(tmp_path):
    """T-02 回归测试：干净空库 + 每连接 PRAGMA foreign_keys=ON 时，
    init_db（create_all）+ seed_default_data 必须成功且无外键违反
    （证明空库首次启动不再因 seed_data 虚构 created_by=1 崩溃）。"""
    from pathlib import Path

    import sqlite3

    from sqlalchemy import select
    from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
    from sqlalchemy.pool import NullPool

    from app.models import TestModule
    from app.seed_data import seed_default_data

    db_path = Path(tmp_path) / "fresh.sqlite"
    eng = create_async_engine(
        f"sqlite+aiosqlite:///{db_path.as_posix()}", poolclass=NullPool
    )
    event.listen(eng.sync_engine, "connect", database.configure_sqlite_connection)
    maker = async_sessionmaker(eng, expire_on_commit=False)
    try:
        async with eng.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)  # 等价 init_db
        async with maker() as session:
            await seed_default_data(session)  # 空库（无任何用户）

        async with maker() as session:
            modules = (await session.execute(select(TestModule))).scalars().all()
            assert modules, "空库 seed 应创建默认模块"
            assert all(m.created_by is None for m in modules), "无用户时 created_by 必须为 NULL（不再虚构 user_id=1）"

        conn = sqlite3.connect(db_path)
        try:
            # foreign_key_check / integrity_check 与连接无关，可跨连接核查
            assert conn.execute("PRAGMA foreign_key_check").fetchall() == []
            assert conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok"
        finally:
            conn.close()

        # 应用式新连接（经 listener）外键仍是开启状态
        sync_eng = create_engine(f"sqlite:///{db_path.as_posix()}", poolclass=NullPool)
        event.listen(sync_eng, "connect", database.configure_sqlite_connection)
        try:
            with sync_eng.connect() as c:
                assert c.exec_driver_sql("PRAGMA foreign_keys").scalar() == 1
        finally:
            sync_eng.dispose()
    finally:
        await eng.dispose()
