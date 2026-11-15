"""V1-05 迁移闭环永久回归测试（T-02 增补 / V1-04 数据模型基础）。

覆盖：
1. 新装空库只走 `alembic upgrade head` 成功、结构（逐表/列/索引/FK/唯一）与
   app.models 完全一致、再次 upgrade head 幂等；
2. 存量 create_all 库（无 alembic_version）经完整 DDL 指纹核对后 stamp 并升级，
   数据保留；
3. 存量初始 revision 结构库（引入幂等表之前）经指纹核对后 stamp 初始 revision
   再 upgrade head，数据保留；
4. revision 级可逆回滚：head → downgrade 0817df993d8b 只删 idempotency_records，
   test_tasks/test_records 数据保留 → 再 upgrade head 表恢复且数据保留（R20）；
5. downgrade base 非空库保护：存在业务数据时拒绝并保留数据；真正空库允许回滚。
"""
import asyncio
import sqlite3

import pytest
from alembic import command as alembic_command
from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

import app.models as models
from app import database

INITIAL_REVISION = "0817df993d8b"
HEAD_REVISION = "005_daily_task_templates"


@pytest.fixture
def db_path(tmp_path, monkeypatch):
    """独立临时 SQLite 库；DATABASE_URL 指向它（init_db / alembic 都读该变量）。"""
    path = (tmp_path / "migration.db").resolve()
    monkeypatch.setenv("DATABASE_URL", "sqlite:///" + path.as_posix())
    monkeypatch.setenv("SECRET_KEY", "migration-test-only-secret-key-0123456789")
    return path


def _connect(path):
    conn = sqlite3.connect(str(path))
    return conn


def _tables(path):
    conn = _connect(path)
    try:
        return [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
    finally:
        conn.close()


def _version(path):
    conn = _connect(path)
    try:
        if not conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone():
            return None
        row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
        return row[0] if row else None
    finally:
        conn.close()


def _counts(path):
    conn = _connect(path)
    try:
        return {
            table: conn.execute(f"SELECT count(*) FROM {table}").fetchone()[0]
            for table in ("test_tasks", "test_records")
        }
    finally:
        conn.close()


def _run_init_db():
    asyncio.run(database.init_db())


def _create_all(path):
    engine = create_engine("sqlite:///" + path.as_posix(), poolclass=NullPool)
    try:
        with engine.begin() as conn:
            models.Base.metadata.create_all(conn)
    finally:
        engine.dispose()


def _seed_rows(path):
    """写入一组最小业务数据（users/devices/test_tasks/test_records 等）。"""
    conn = _connect(path)
    try:
        conn.execute(
            "INSERT INTO users (username,password_hash,role,status) "
            "VALUES ('v1_mig_user','x','user','active')"
        )
        conn.execute(
            "INSERT INTO devices (serial_number,status,pc_identifier,owner_id) "
            "VALUES ('v1-mig-serial','offline','pc',"
            "(SELECT id FROM users WHERE username='v1_mig_user'))"
        )
        conn.execute("INSERT INTO test_modules (name) VALUES ('v1_mig_module')")
        conn.execute(
            "INSERT INTO test_items (module_id,name,exec_type,exec_command) "
            "VALUES ((SELECT id FROM test_modules WHERE name='v1_mig_module'),"
            "'v1_mig_item','adb_shell','echo ok')"
        )
        conn.execute(
            "INSERT INTO test_tasks (user_id,device_id,selected_items,status,schedule_type) "
            "VALUES ((SELECT id FROM users WHERE username='v1_mig_user'),"
            "(SELECT id FROM devices WHERE serial_number='v1-mig-serial'),"
            "'[1]','pending','immediate')"
        )
        conn.execute(
            "INSERT INTO test_records (task_id,item_id,status) "
            "SELECT t.id,i.id,'pending' FROM test_tasks t, test_items i "
            "WHERE i.name='v1_mig_item'"
        )
        conn.commit()
    finally:
        conn.close()


def _fingerprint(path):
    engine = create_engine("sqlite:///" + path.as_posix(), poolclass=NullPool)
    try:
        with engine.connect() as conn:
            return database._schema_fingerprint(conn)
    finally:
        engine.dispose()


def _assert_schema_matches_models(path):
    diffs = database._fingerprint_diffs(_fingerprint(path), database._reference_fingerprint())
    assert diffs == [], f"结构与 app.models 不一致: {diffs}"


# ---------------------------------------------------------------- 1. 新装 upgrade
def test_fresh_install_upgrade_creates_head_schema_matching_models(db_path):
    assert _tables(db_path) == [] or not db_path.exists()
    _run_init_db()
    assert _version(db_path) == HEAD_REVISION
    assert "idempotency_records" in _tables(db_path)
    _assert_schema_matches_models(db_path)


def test_upgrade_head_is_idempotent_when_already_at_head(db_path):
    _run_init_db()
    before = _tables(db_path)
    # 再次执行必须成功且不重复建表/不改版本
    alembic_command.upgrade(database._alembic_config(), "head")
    _run_init_db()
    assert _version(db_path) == HEAD_REVISION
    assert _tables(db_path) == before
    _assert_schema_matches_models(db_path)


def test_idempotency_records_unique_constraint_enforced_by_db(db_path):
    _run_init_db()
    conn = _connect(db_path)
    try:
        conn.execute("PRAGMA foreign_keys=ON")
        conn.execute(
            "INSERT INTO users (username,password_hash,role,status) "
            "VALUES ('v1_key_user','x','user','active')"
        )
        uid = conn.execute("SELECT id FROM users WHERE username='v1_key_user'").fetchone()[0]
        sha = "a" * 64
        conn.execute(
            "INSERT INTO idempotency_records "
            "(user_id,operation,idempotency_key,request_sha256) "
            f"VALUES ({uid},'task_create','key-0001','{sha}')"
        )
        conn.commit()
        with pytest.raises(sqlite3.IntegrityError):
            conn.execute(
                "INSERT INTO idempotency_records "
                "(user_id,operation,idempotency_key,request_sha256) "
                f"VALUES ({uid},'task_create','key-0001','{'b' * 64}')"
            )
        conn.rollback()
    finally:
        conn.close()


# ------------------------------------------------- 2. 存量 create_all 库（head 结构）
def test_legacy_create_all_db_stamps_head_and_preserves_data(db_path):
    _create_all(db_path)
    _seed_rows(db_path)
    before = _counts(db_path)
    assert _version(db_path) is None  # create_all 不写 alembic_version

    _run_init_db()

    assert _version(db_path) == HEAD_REVISION
    assert _counts(db_path) == before
    _assert_schema_matches_models(db_path)


# ------------------------------------------- 3. 存量初始 revision 结构（无幂等表）
def test_legacy_initial_revision_db_stamps_initial_then_upgrades(db_path):
    # 建初始 revision 结构，删除 alembic_version 模拟历史 create_all 库（无幂等表）
    alembic_command.upgrade(database._alembic_config(), INITIAL_REVISION)
    conn = _connect(db_path)
    try:
        conn.execute("DROP TABLE alembic_version")
        conn.commit()
    finally:
        conn.close()
    _seed_rows(db_path)
    before = _counts(db_path)
    assert "idempotency_records" not in _tables(db_path)

    _run_init_db()

    assert _version(db_path) == HEAD_REVISION
    assert "idempotency_records" in _tables(db_path)
    assert _counts(db_path) == before
    _assert_schema_matches_models(db_path)


# ------------------------------------------- 4. 同表名不同 DDL → 明确失败
def test_legacy_mismatched_schema_is_refused_without_stamp(db_path):
    _create_all(db_path)
    _seed_rows(db_path)
    conn = _connect(db_path)
    try:
        conn.execute("ALTER TABLE users ADD COLUMN rogue_col INTEGER")
        conn.commit()
    finally:
        conn.close()
    before = _counts(db_path)

    with pytest.raises(database.SchemaMismatchError) as excinfo:
        _run_init_db()

    assert "rogue_col" in str(excinfo.value)
    assert _version(db_path) is None  # 未静默 stamp
    assert _counts(db_path) == before  # 未破坏数据


# ------------------------------------------- 5. revision 级可逆回滚（R20）
def test_revision_rollback_preserves_data_and_drops_only_idempotency(db_path):
    _run_init_db()
    _seed_rows(db_path)
    before = _counts(db_path)
    cfg = database._alembic_config()

    alembic_command.downgrade(cfg, INITIAL_REVISION)
    assert _version(db_path) == INITIAL_REVISION
    assert "idempotency_records" not in _tables(db_path)  # 仅删本 revision 新表
    assert _counts(db_path) == before  # 历史数据保留

    alembic_command.upgrade(cfg, "head")
    assert _version(db_path) == HEAD_REVISION
    assert "idempotency_records" in _tables(db_path)
    assert _counts(db_path) == before
    _assert_schema_matches_models(db_path)


# ------------------------------------------- 6. downgrade base 非空库保护
def test_downgrade_base_refuses_to_drop_non_empty_database(db_path):
    _run_init_db()
    _seed_rows(db_path)
    before = _counts(db_path)
    cfg = database._alembic_config()

    alembic_command.downgrade(cfg, INITIAL_REVISION)
    with pytest.raises(RuntimeError) as excinfo:
        alembic_command.downgrade(cfg, "base")

    assert "拒绝 downgrade base" in str(excinfo.value)
    # 数据与结构完整保留
    assert _counts(db_path) == before
    assert _version(db_path) == INITIAL_REVISION
    assert set(_tables(db_path)) >= {"users", "test_tasks", "test_records"}


def test_downgrade_base_allowed_on_truly_empty_database(db_path):
    _run_init_db()
    conn = _connect(db_path)
    try:
        for table in (
            "idempotency_records", "test_records", "baselines", "golden_cases",
            "test_tasks", "test_items", "test_tools", "test_modules",
            "knowledge_entries", "failure_patterns", "devices", "users",
        ):
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone():
                conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()

    alembic_command.downgrade(database._alembic_config(), "base")
    assert [t for t in _tables(db_path) if t != "alembic_version"] == []
