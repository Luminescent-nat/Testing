#!/usr/bin/env python3
"""T-02 Alembic + SQLite 迁移演练（只在隔离临时目录/副本上执行）。

用法（在 backend 目录）：
    python scripts/verify_migrations.py --report docs/verification/tasks/T-02/migration-summary.json

安全红线（见 docs/design/scheduler-and-data.md 第 5 节）：
- 源库（默认 backend/test_platform.db）只读：只用只读连接 + sqlite3 backup API
  生成一致性快照（覆盖 WAL 中已提交数据），演练前后源库与 WAL/SHM sidecar 的
  SHA-256 必须完全一致；
- 所有 alembic 子进程的 DATABASE_URL 都指向 tempfile 隔离目录内的 .db 空库/副本，
  绝不修改真实库，绝不对真实库执行 create_all / stamp / upgrade / downgrade；
- 任一 alembic 步骤失败都保留原始输出并以非 0 退出码结束，不静默吞掉。

V1-05 强化后的演练内容：
1. 空库（路径 A）：
   a. `alembic upgrade head` 成功 → 逐表/列/索引/FK/唯一/CHECK 的 DDL 指纹必须与
      app.models 完全一致；再次 upgrade head 幂等（版本不变、无重复建表）；
   b. --sql 离线核对包含全部业务表（含 idempotency_records）；
   c. revision 级可逆回滚演练：head → downgrade 0817df993d8b（只删
      idempotency_records，test_tasks/test_records 数据保留）→ upgrade head（数据保留）；
   d. downgrade base 非空库保护：存在业务数据时 downgrade base 必须失败且数据完整；
   e. 清空数据后 downgrade base 成功 → 再 upgrade head 恢复全部表。
2. 存量库（路径 B）：
   a. B1 真实源库：用 sqlite3 backup API 生成 WAL 一致性快照（不是裸 copy 主库文件），
      核对源库只读计数、备份 integrity_check、行数与 SHA-256；对备份做 DDL 指纹比对，
      真实库若与初始 revision/head 不一致则记录漂移诊断，并验证生产 init_db 明确拒绝
      stamp（同表名不同 DDL 反例，绝不静默登记）；
   b. B2 规范化存量副本：以初始 revision 结构建库并逐表搬运真实源库数据（只读源库），
      结构 DDL 指纹与初始 revision 完全一致后经生产 init_db stamp 初始 revision →
      upgrade head → 数据保留；
   c. revision 级回滚/再升级数据保留；非空库 downgrade base 必须被保护代码拒绝，
      数据完整、版本回退。
3. 两个路径都验证：唯一键（users.username、devices.serial_number、
   idempotency_records 三元组）与非法外键由数据库实际拒绝。
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.pool import NullPool

BACKEND_DIR = Path(__file__).resolve().parents[1]

# 初始迁移 0817df993d8b + 002_idempotency 建成的全部业务表
EXPECTED_TABLES = [
    "baselines",
    "devices",
    "failure_patterns",
    "golden_cases",
    "idempotency_records",
    "knowledge_entries",
    "test_items",
    "test_modules",
    "test_records",
    "test_tasks",
    "test_tools",
    "users",
]
COUNT_TABLES = ("test_tasks", "test_records")
INITIAL_REVISION = "0817df993d8b"
HEAD_REVISION = "005_daily_task_templates"
SOURCE_PATH: Path | None = None
FP = None  # 由 load_fingerprint_helpers 注入 app.database 的结构指纹函数


class StepError(RuntimeError):
    """某个 alembic 步骤失败（已记录原始输出）。"""


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as fh:
        for chunk in iter(lambda: fh.read(1 << 20), b""):
            digest.update(chunk)
    return digest.hexdigest()


def sidecar_hashes(source: Path) -> dict:
    out = {}
    for suffix in ("-wal", "-shm", "-journal"):
        side = source.with_name(source.name + suffix)
        out[side.name] = sha256_file(side) if side.exists() else None
    return out


def db_url(path: Path) -> str:
    return "sqlite:///" + path.resolve().as_posix()


def build_env(url: str) -> dict:
    env = os.environ.copy()
    env["DATABASE_URL"] = url
    # 独立于生产：仅用于 app.config 的占位，避免未来 Settings 校验阻断迁移进程。
    env["SECRET_KEY"] = "migration-verification-only-secret-key-32chars"
    env["PYTHONIOENCODING"] = "utf-8"
    return env


def run_alembic(label, url, args, checks, expect_success=True):
    if SOURCE_PATH is not None and str(SOURCE_PATH) in url:
        raise SystemExit(f"[安全中断] 拒绝把真实源库传入 alembic: {url}")
    cmd = [sys.executable, "-m", "alembic", *args]
    print(f"\n[{label}] $ {' '.join(cmd)}")
    print(f"[{label}] DATABASE_URL={url}")
    proc = subprocess.run(
        cmd,
        cwd=str(BACKEND_DIR),
        env=build_env(url),
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
    )
    print(f"[{label}] exit={proc.returncode}")
    if proc.stdout.strip():
        print(f"[{label}] stdout:\n{proc.stdout}")
    if proc.stderr.strip():
        print(f"[{label}] stderr:\n{proc.stderr}")
    ok = proc.returncode == 0 if expect_success else proc.returncode != 0
    checks.append((f"{label}:exit-{proc.returncode}", ok, "" if ok else f"expected_success={expect_success}"))
    if expect_success and proc.returncode != 0:
        raise StepError(f"{label} 失败 (exit {proc.returncode})")
    return proc


def read_state(path: Path, label: str, checks=None) -> dict:
    conn = sqlite3.connect(str(path))
    try:
        conn.execute("PRAGMA busy_timeout=30000")
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' ORDER BY name"
            )
        ]
        has_av = "alembic_version" in tables
        version = None
        if has_av:
            row = conn.execute("SELECT version_num FROM alembic_version").fetchone()
            version = row[0] if row else None
        user_tables = [t for t in tables if t != "alembic_version"]
        counts = {
            t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in COUNT_TABLES
            if t in user_tables
        }
        integrity = [r[0] for r in conn.execute("PRAGMA integrity_check")]
        fk_violations = [tuple(r) for r in conn.execute("PRAGMA foreign_key_check")]
        state = {
            "label": label,
            "tables": user_tables,
            "alembic_version": version,
            "counts": counts,
            "integrity_check": integrity,
            "foreign_key_violations": fk_violations,
        }
        print(f"[{label}] state={json.dumps(state, ensure_ascii=False)}")
        return state
    finally:
        conn.close()


def load_fingerprint_helpers():
    """注入 app.database 的结构指纹函数（与生产启动核验使用同一实现）。"""
    global FP
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    from app import database as app_db  # noqa: WPS433
    import app.models  # noqa: F401,WPS433  确保 Base.metadata 注册全部模型

    class _FP:
        schema_fingerprint = staticmethod(app_db._schema_fingerprint)
        reference_fingerprint = staticmethod(app_db._reference_fingerprint)
        revision_fingerprint = staticmethod(app_db._revision_fingerprint)
        diffs = staticmethod(app_db._fingerprint_diffs)

    FP = _FP()
    return FP


def ddl_fingerprint_diffs(path: Path, reference: dict | None = None) -> list:
    """返回目标库结构与参考结构的差异列表（默认参考=head/app.models）。"""
    engine = create_engine(db_url(path), poolclass=NullPool)
    try:
        with engine.connect() as conn:
            current = FP.schema_fingerprint(conn)
        return FP.diffs(current, reference if reference is not None else FP.reference_fingerprint())
    finally:
        engine.dispose()


def check_ddl_fingerprint(path: Path, label: str, checks, reference: dict | None = None) -> list:
    diffs = ddl_fingerprint_diffs(path, reference)
    checks.append(
        (
            f"{label}:ddl-fingerprint-ok",
            not diffs,
            "" if not diffs else "；".join(diffs[:12]),
        )
    )
    return diffs


def check_offline_sql(sql: str, prefix: str, checks) -> None:
    missing = [t for t in EXPECTED_TABLES if f"CREATE TABLE {t}" not in sql]
    checks.append(
        (
            f"{prefix}:offline-sql-creates-all-tables",
            not missing,
            f"missing={missing}",
        )
    )


def _try_integrity_error(conn, sql: str) -> bool:
    try:
        conn.execute(sql)
        conn.commit()
        return False
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        print(f"    expected IntegrityError: {exc}")
        return True
    except Exception:
        conn.rollback()
        raise


def _try_success(conn, sql: str) -> bool:
    try:
        conn.execute(sql)
        conn.commit()
        return True
    except sqlite3.IntegrityError as exc:
        conn.rollback()
        print(f"    unexpected IntegrityError: {exc}")
        return False


def probe_constraints(path: Path, label: str, checks, apply_pragma) -> dict:
    """在迁移后的库副本上验证唯一键/非法外键由数据库实际拒绝。"""
    conn = sqlite3.connect(str(path))
    try:
        apply_pragma(conn)  # 与 app/database.py 一致的每连接 PRAGMA 语义
        fk_pragma = conn.execute("PRAGMA foreign_keys").fetchone()[0]
        checks.append((f"{label}:foreign_keys_pragma_on", fk_pragma == 1, f"got={fk_pragma}"))

        conn.execute(
            "INSERT INTO users (username, password_hash, role, status) "
            "VALUES ('t02_probe_user', 'x', 'user', 'active')"
        )
        conn.commit()
        uid = conn.execute(
            "SELECT id FROM users WHERE username='t02_probe_user'"
        ).fetchone()[0]

        dup_user = _try_integrity_error(
            conn,
            "INSERT INTO users (username, password_hash, role, status) "
            "VALUES ('t02_probe_user', 'y', 'user', 'active')",
        )
        checks.append((f"{label}:duplicate_username_rejected", dup_user, ""))

        conn.execute(
            "INSERT INTO devices (serial_number, status, pc_identifier) "
            "VALUES ('t02-serial', 'offline', 'pc')"
        )
        conn.commit()
        dup_serial = _try_integrity_error(
            conn,
            "INSERT INTO devices (serial_number, status, pc_identifier) "
            "VALUES ('t02-serial', 'offline', 'pc')",
        )
        checks.append((f"{label}:duplicate_serial_number_rejected", dup_serial, ""))

        legal = _try_success(
            conn,
            "INSERT INTO devices (serial_number, status, pc_identifier, owner_id) "
            f"VALUES ('t02-legal', 'offline', 'pc', {uid})",
        )
        checks.append((f"{label}:legal_foreign_key_accepted", legal, ""))

        illegal = _try_integrity_error(
            conn,
            "INSERT INTO devices (serial_number, status, pc_identifier, owner_id) "
            "VALUES ('t02-orphan', 'offline', 'pc', 999999)",
        )
        checks.append((f"{label}:illegal_foreign_key_rejected", illegal, ""))

        # idempotency_records：三元组唯一约束由数据库拒绝重复
        sha_a = "a" * 64
        first_idem = _try_success(
            conn,
            "INSERT INTO idempotency_records "
            "(user_id, operation, idempotency_key, request_sha256) "
            f"VALUES ({uid}, 'task_create', 'probe-key-0001', '{sha_a}')",
        )
        checks.append((f"{label}:idempotency_first_insert_accepted", first_idem, ""))
        dup_idem = _try_integrity_error(
            conn,
            "INSERT INTO idempotency_records "
            "(user_id, operation, idempotency_key, request_sha256) "
            f"VALUES ({uid}, 'task_create', 'probe-key-0001', '{'b' * 64}')",
        )
        checks.append((f"{label}:idempotency_duplicate_key_rejected", dup_idem, ""))
        idem_fk = _try_integrity_error(
            conn,
            "INSERT INTO idempotency_records "
            "(user_id, operation, idempotency_key, request_sha256, task_id) "
            f"VALUES ({uid}, 'task_create', 'probe-key-fk', '{sha_a}', 999999)",
        )
        checks.append((f"{label}:idempotency_illegal_task_fk_rejected", idem_fk, ""))

        return {
            "foreign_keys_pragma": fk_pragma,
            "duplicate_username_rejected": dup_user,
            "duplicate_serial_number_rejected": dup_serial,
            "legal_foreign_key_accepted": legal,
            "illegal_foreign_key_rejected": illegal,
            "idempotency_first_insert_accepted": first_idem,
            "idempotency_duplicate_key_rejected": dup_idem,
            "idempotency_illegal_task_fk_rejected": idem_fk,
        }
    finally:
        conn.rollback()
        conn.close()


def resolve_pragma_applier(workdir: Path):
    """优先复用 app.database.configure_sqlite_connection；失败则回退等价本地实现。

    导入前把 DATABASE_URL 指向隔离目录内的临时文件，确保 app.database 建出的
    异步引擎绝不会指向真实库（且建引擎不连接、不落盘）。
    """
    os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + (workdir / "probe_engine.db").resolve().as_posix()
    os.environ["SECRET_KEY"] = "migration-verification-only-secret-key-32chars"
    if str(BACKEND_DIR) not in sys.path:
        sys.path.insert(0, str(BACKEND_DIR))
    try:
        from app.database import configure_sqlite_connection  # noqa: WPS433

        print("[pragma] apply = app.database.configure_sqlite_connection")
        return configure_sqlite_connection, "app.database.configure_sqlite_connection"
    except Exception as exc:  # pragma: no cover - 防御性回退
        print(f"[pragma] WARN 无法导入 app.database({exc!r})，回退等价本地 PRAGMA")

        def _local(conn):
            conn.execute("PRAGMA foreign_keys=ON")
            conn.execute("PRAGMA busy_timeout=30000")

        return _local, "local-equivalent"


def seed_minimal_rows(path: Path) -> dict:
    """为 revision 级回滚演练写入最小业务数据（任务+记录各 1 行）。"""
    conn = sqlite3.connect(str(path))
    try:
        conn.execute(
            "INSERT INTO users (username, password_hash, role, status) "
            "VALUES ('t02_seed_user', 'x', 'user', 'active')"
        )
        conn.execute(
            "INSERT INTO devices (serial_number, status, pc_identifier, owner_id) "
            "VALUES ('t02-seed-serial', 'offline', 'pc', "
            "(SELECT id FROM users WHERE username='t02_seed_user'))"
        )
        conn.execute("INSERT INTO test_modules (name) VALUES ('t02_seed_module')")
        conn.execute(
            "INSERT INTO test_items (module_id, name, exec_type, exec_command) "
            "VALUES ((SELECT id FROM test_modules WHERE name='t02_seed_module'), "
            "'t02_seed_item', 'adb_shell', 'echo ok')"
        )
        conn.execute(
            "INSERT INTO test_tasks (user_id, device_id, selected_items, status, schedule_type) "
            "VALUES ((SELECT id FROM users WHERE username='t02_seed_user'), "
            "(SELECT id FROM devices WHERE serial_number='t02-seed-serial'), "
            "'[1]', 'pending', 'immediate')"
        )
        conn.execute(
            "INSERT INTO test_records (task_id, item_id, status) "
            "SELECT t.id, i.id, 'pending' FROM test_tasks t, test_items i "
            "WHERE t.selected_items='[1]' AND i.name='t02_seed_item'"
        )
        conn.commit()
    finally:
        conn.close()
    return {"test_tasks": 1, "test_records": 1}


def wipe_business_rows(path: Path) -> None:
    """清空全部业务数据，用于「空库 downgrade base 成功」演练。"""
    conn = sqlite3.connect(str(path))
    try:
        for table in (
            "idempotency_records",
            "test_records",
            "baselines",
            "golden_cases",
            "test_tasks",
            "test_items",
            "test_tools",
            "test_modules",
            "knowledge_entries",
            "failure_patterns",
            "devices",
            "users",
        ):
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (table,)
            ).fetchone():
                conn.execute(f"DELETE FROM {table}")
        conn.commit()
    finally:
        conn.close()


def drill_revision_rollback(path: Path, url: str, label: str, checks) -> dict:
    """head → downgrade 初始 revision（只删 idempotency_records）→ 再 upgrade head。

    断言：downgrade 后 idempotency_records 消失但 test_tasks/test_records 数据保留；
    随后（仍在初始 revision、库非空）验证 downgrade base 被保护代码拒绝且数据完整；
    再次 upgrade head 后表恢复且数据仍保留（revision 级可逆回滚证据）。
    """
    print(f"\n---------------- {label}: revision 级回滚演练 ----------------")
    before = read_state(path, f"{label}/rev-before")
    run_alembic(f"{label}/downgrade-initial", url, ["downgrade", INITIAL_REVISION], checks)
    down = read_state(path, f"{label}/rev-after-downgrade")
    checks.append(
        (
            f"{label}:revision-downgrade-drops-idempotency-table",
            "idempotency_records" not in down["tables"],
            str(down["tables"]),
        )
    )
    checks.append(
        (
            f"{label}:revision-downgrade-preserves-tasks-records",
            down["counts"] == before["counts"],
            f"before={before['counts']} after={down['counts']}",
        )
    )
    checks.append(
        (
            f"{label}:revision-downgrade-keeps-alembic-version-at-initial",
            down["alembic_version"] == INITIAL_REVISION,
            str(down["alembic_version"]),
        )
    )

    # 非空库 downgrade base 保护：在初始 revision 上直接尝试，必须被拒绝且不删任何表
    protected = run_alembic(f"{label}/downgrade-base-protected", url, ["downgrade", "base"], checks, expect_success=False)
    combined = (protected.stdout or "") + (protected.stderr or "")
    checks.append(
        (
            f"{label}:downgrade-base-protection-message",
            "拒绝 downgrade base" in combined,
            combined[-400:],
        )
    )
    after_protect = read_state(path, f"{label}/rev-after-protected-downgrade-base")
    checks.append(
        (
            f"{label}:downgrade-base-protection-keeps-data",
            after_protect["counts"] == before["counts"],
            f"before={before['counts']} after={after_protect['counts']}",
        )
    )
    expected_protected_tables = [t for t in sorted(EXPECTED_TABLES) if t != "idempotency_records"]
    checks.append(
        (
            f"{label}:downgrade-base-protection-keeps-tables",
            after_protect["tables"] == expected_protected_tables
            and after_protect["alembic_version"] == INITIAL_REVISION,
            f"tables={after_protect['tables']} version={after_protect['alembic_version']}",
        )
    )

    run_alembic(f"{label}/reupgrade-head", url, ["upgrade", "head"], checks)
    final = read_state(path, f"{label}/rev-after-reupgrade")
    checks.append(
        (
            f"{label}:revision-reupgrade-restores-idempotency-table",
            "idempotency_records" in final["tables"],
            str(final["tables"]),
        )
    )
    checks.append(
        (
            f"{label}:revision-reupgrade-preserves-tasks-records",
            final["counts"] == before["counts"],
            f"before={before['counts']} after={final['counts']}",
        )
    )
    return {
        "before": before,
        "after_downgrade": down,
        "after_protected_downgrade_base": after_protect,
        "after_reupgrade": final,
    }


def scenario_empty(workdir: Path, checks, apply_pragma) -> dict:
    print("\n================ 场景 A：新装空库 ================")
    db = workdir / "empty.db"
    url = db_url(db)

    run_alembic("empty/upgrade", url, ["upgrade", "head"], checks)
    up = read_state(db, "empty/after-upgrade", checks)
    checks.append(("empty:table-set-equals-expected", up["tables"] == sorted(EXPECTED_TABLES), str(up["tables"])))
    checks.append(("empty:alembic-version-at-head", up["alembic_version"] == HEAD_REVISION, str(up["alembic_version"])))
    checks.append(("empty:integrity-ok", up["integrity_check"] == ["ok"], str(up["integrity_check"])))
    checks.append(("empty:no-fk-violations", up["foreign_key_violations"] == [], str(up["foreign_key_violations"])))
    check_ddl_fingerprint(db, "empty", checks)

    # 再次 upgrade head 必须幂等
    run_alembic("empty/upgrade-again-idempotent", url, ["upgrade", "head"], checks)
    again = read_state(db, "empty/after-reupgrade-idempotent")
    checks.append(("empty:reupgrade-idempotent-version", again["alembic_version"] == HEAD_REVISION, str(again["alembic_version"])))
    checks.append(("empty:reupgrade-idempotent-tables", again["tables"] == sorted(EXPECTED_TABLES), str(again["tables"])))

    offline = run_alembic("empty/offline-sql", url, ["upgrade", "head", "--sql"], checks)
    check_offline_sql(offline.stdout, "empty", checks)

    # revision 级回滚演练（先写入最小数据；内含 downgrade base 保护验证）
    seed_minimal_rows(db)
    revision = drill_revision_rollback(db, url, "empty", checks)

    # 清空数据后 downgrade base 允许成功（真正空库），再 upgrade head 恢复结构
    wipe_business_rows(db)
    run_alembic("empty/downgrade-base-empty", url, ["downgrade", "base"], checks)
    down = read_state(db, "empty/after-downgrade")
    checks.append(("empty:tables-dropped-after-downgrade", down["tables"] == [], str(down["tables"])))
    run_alembic("empty/upgrade-after-downgrade", url, ["upgrade", "head"], checks)
    final = read_state(db, "empty/after-reupgrade")
    checks.append(("empty:reupgrade-table-set", final["tables"] == sorted(EXPECTED_TABLES), str(final["tables"])))
    checks.append(("empty:reupgrade-integrity", final["integrity_check"] == ["ok"], str(final["integrity_check"])))

    run_alembic("empty/current", url, ["current"], checks)
    constraints = probe_constraints(db, "empty", checks, apply_pragma)
    return {
        "after_upgrade": up,
        "revision_rollback": revision,
        "after_downgrade": down,
        "after_reupgrade": final,
        "constraints": constraints,
    }


def sqlite_wal_consistent_backup(source: Path, dest: Path) -> dict:
    """用 sqlite3 backup API 生成一致性快照（覆盖 WAL 中已提交数据）。

    以只读 URI 打开源库，backup 到 dest；随后核对源库只读计数、目标库
    integrity_check / foreign_key_check / 行数 / SHA-256。绝不写源库。
    """
    src_uri = f"file:{source.resolve().as_posix()}?mode=ro"
    src = sqlite3.connect(src_uri, uri=True)
    try:
        src.execute("PRAGMA busy_timeout=30000")
        dst = sqlite3.connect(str(dest))
        try:
            src.backup(dst)
            dst.commit()
            integrity = [r[0] for r in dst.execute("PRAGMA integrity_check")]
            fk_violations = [tuple(r) for r in dst.execute("PRAGMA foreign_key_check")]
            dst_counts = {
                t: dst.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
                for t in COUNT_TABLES
                if dst.execute(
                    "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
                ).fetchone()
            }
        finally:
            dst.close()
        src_counts = {
            t: src.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in COUNT_TABLES
            if src.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
            ).fetchone()
        }
        print(f"[backup] source_counts={src_counts} backup_counts={dst_counts}")
        return {
            "source_counts": src_counts,
            "backup_counts": dst_counts,
            "integrity_check": integrity,
            "foreign_key_violations": fk_violations,
            "backup_sha256": sha256_file(dest),
            "backup_size": dest.stat().st_size,
        }
    finally:
        src.close()


def table_counts(path: Path, tables) -> dict:
    """读取指定表行数（用于数据保留核对）。"""
    conn = sqlite3.connect(str(path))
    try:
        return {
            t: conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
            for t in tables
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
            ).fetchone()
        }
    finally:
        conn.close()


def run_init_db_on(path: Path) -> str:
    """在指定库上端到端运行生产 init_db 同步流程（含结构核验），返回 action。

    通过临时覆盖 DATABASE_URL 指向目标库，验证生产启动迁移路径本身，
    而不是仅用 alembic CLI 模拟。
    """
    from app import database as app_db  # noqa: WPS433

    saved = os.environ.get("DATABASE_URL")
    os.environ["DATABASE_URL"] = "sqlite:///" + path.resolve().as_posix()
    try:
        action = app_db._init_db_sync()
        app_db._verify_schema_matches_models(action)
        return action
    finally:
        if saved is None:
            os.environ.pop("DATABASE_URL", None)
        else:
            os.environ["DATABASE_URL"] = saved


def build_normalized_legacy_copy(source: Path, dest: Path, checks) -> None:
    """用初始 revision 结构建库，再把真实源库数据逐表搬运进来（只读源库）。

    产出「结构=初始 revision、数据=真实存量」的存量副本，用于 stamp → upgrade →
    revision 级回滚 → downgrade base 保护 的数据保留演练。
    """
    run_alembic("legacy-copy/upgrade-initial", db_url(dest), ["upgrade", INITIAL_REVISION], checks)
    src_uri = f"file:{source.resolve().as_posix()}?mode=ro"
    conn = sqlite3.connect(str(dest), uri=True)
    try:
        conn.execute("ATTACH DATABASE ? AS src", (src_uri,))
        tables = [
            r[0]
            for r in conn.execute(
                "SELECT name FROM main.sqlite_master WHERE type='table' "
                "AND name NOT LIKE 'sqlite_%' AND name != 'alembic_version' ORDER BY name"
            )
        ]
        for table in tables:
            dest_cols = [r[1] for r in conn.execute(f'PRAGMA main.table_info("{table}")')]
            src_cols = {r[1] for r in conn.execute(f'PRAGMA src.table_info("{table}")')}
            missing = [c for c in dest_cols if c not in src_cols]
            if missing:
                raise StepError(f"源库表 {table} 缺少初始 revision 需要的列: {missing}")
            col_list = ",".join(f'"{c}"' for c in dest_cols)
            conn.execute(
                f'INSERT INTO main."{table}" ({col_list}) SELECT {col_list} FROM src."{table}"'
            )
        conn.commit()
        copied = table_counts(dest, tables)
        source_counts = table_counts(source, tables)
        checks.append(
            (
                "legacy-copy:all-table-row-counts-equal-source",
                copied == source_counts,
                f"copy={copied} source={source_counts}",
            )
        )
        print(f"[legacy-copy] copied counts={copied}")
        # 模拟历史 create_all 存量库：无 alembic_version（移除建库时 autogenerate 的版本表）
        if conn.execute(
            "SELECT 1 FROM main.sqlite_master WHERE type='table' AND name='alembic_version'"
        ).fetchone():
            conn.execute("DROP TABLE alembic_version")
            conn.commit()
            print("[legacy-copy] dropped alembic_version to mimic pre-alembic legacy DB")
    finally:
        conn.close()


def scenario_legacy(workdir: Path, source: Path, empty_state: dict, checks, notes, apply_pragma) -> dict:
    print("\n================ 场景 B1：真实存量库 WAL 一致性备份 + 漂移检测 ================")
    backup_path = workdir / "legacy_source_backup.db"
    backup = sqlite_wal_consistent_backup(source, backup_path)
    checks.append(("legacy-source:backup-integrity-ok", backup["integrity_check"] == ["ok"], str(backup["integrity_check"])))
    checks.append(
        (
            "legacy-source:backup-row-counts-equal-source",
            backup["source_counts"] == backup["backup_counts"],
            f"source={backup['source_counts']} backup={backup['backup_counts']}",
        )
    )
    print(f"[legacy-source] backup_sha256={backup['backup_sha256']} size={backup['backup_size']}")

    pre = read_state(backup_path, "legacy-source/before", checks)
    checks.append(("legacy-source:avoid-db-already-migrated", pre["alembic_version"] is None, str(pre["alembic_version"])))
    initial_reference = FP.revision_fingerprint(INITIAL_REVISION)
    engine = create_engine(db_url(backup_path), poolclass=NullPool)
    try:
        with engine.connect() as conn:
            actual_fp = FP.schema_fingerprint(conn)
    finally:
        engine.dispose()
    drift = FP.diffs(actual_fp, initial_reference)
    notes.append(
        (
            "legacy-source:ddl-drift-vs-initial-revision (OBSERVATION)",
            not drift,
            "真实存量库由更早版本 create_all 建立，与初始 revision 存在结构漂移（不臆造通过）："
            + ("；".join(drift[:12]) if drift else "无漂移"),
        )
    )
    # 生产 init_db 必须拒绝在漂移结构上 stamp（明确失败，不静默登记）
    try:
        action = run_init_db_on(backup_path)
        checks.append(("legacy-source:init-db-refuses-drifted-schema", False, f"未拒绝且 action={action}"))
    except Exception as exc:  # noqa: BLE001 - 期望 SchemaMismatchError
        from app.database import SchemaMismatchError  # noqa: WPS433

        checks.append(
            (
                "legacy-source:init-db-refuses-drifted-schema",
                isinstance(exc, SchemaMismatchError),
                f"{type(exc).__name__}: {str(exc)[:200]}",
            )
        )

    print("\n================ 场景 B2：结构=初始 revision、数据=真实存量的规范化副本 ================")
    legacy = workdir / "legacy_normalized.db"
    build_normalized_legacy_copy(source, legacy, checks)
    pre_norm = read_state(legacy, "legacy/before", checks)
    checks.append(("legacy:avoid-db-already-migrated", pre_norm["alembic_version"] is None, str(pre_norm["alembic_version"])))
    expected_initial_tables = [t for t in sorted(EXPECTED_TABLES) if t != "idempotency_records"]
    checks.append(
        (
            "legacy:pre-schema-table-set-matches-initial-revision",
            pre_norm["tables"] == expected_initial_tables,
            f"pre={pre_norm['tables']} expected={expected_initial_tables}",
        )
    )
    diffs = check_ddl_fingerprint(legacy, "legacy/pre-initial", checks, reference=initial_reference)
    checks.append(("legacy:pre-ddl-identical-to-initial-before-stamp", not diffs, "" if not diffs else "；".join(diffs[:12])))
    print(f"[legacy] counts(before)={pre_norm['counts']}")

    url = db_url(legacy)
    offline = run_alembic("legacy/offline-sql", url, ["upgrade", "head", "--sql"], checks)
    check_offline_sql(offline.stdout, "legacy", checks)

    # 生产 init_db：结构=初始 revision → stamp 初始 revision → upgrade head
    if diffs:
        checks.append(("legacy:init-db-legacy-path", False, "结构不一致，拒绝 stamp"))
        raise StepError("规范化存量副本结构与初始 revision 不一致，拒绝 stamp")
    action = run_init_db_on(legacy)
    checks.append(
        (
            "legacy:init-db-legacy-path-action",
            action == "legacy-stamp-initial-then-upgrade",
            f"action={action}",
        )
    )
    up = read_state(legacy, "legacy/after-upgrade", checks)
    checks.append(("legacy:integrity-after-upgrade", up["integrity_check"] == ["ok"], str(up["integrity_check"])))
    checks.append(("legacy:data-preserved-after-upgrade", up["counts"] == pre_norm["counts"], f"before={pre_norm['counts']} after={up['counts']}"))
    print(f"[legacy] counts(after_upgrade)={up['counts']}")
    check_ddl_fingerprint(legacy, "legacy/post-upgrade", checks)

    # revision 级回滚 / 再升级：数据保留（内含 downgrade base 保护验证）
    revision = drill_revision_rollback(legacy, url, "legacy", checks)

    run_alembic("legacy/current", url, ["current"], checks)
    constraints = probe_constraints(legacy, "legacy", checks, apply_pragma)
    return {
        "source_backup": backup,
        "source_before": pre,
        "source_ddl_drift": drift,
        "before": pre_norm,
        "after_upgrade": up,
        "revision_rollback": revision,
        "constraints": constraints,
    }


def main(argv=None) -> int:
    global SOURCE_PATH
    parser = argparse.ArgumentParser(description="T-02 alembic/SQLite 外键迁移演练（隔离副本）")
    parser.add_argument("--source", default=None, help="源库路径（默认 backend/test_platform.db，只读）")
    parser.add_argument("--report", default=None, help="输出 JSON 汇总路径")
    parser.add_argument("--keep", action="store_true", help="保留临时工作目录便于排查")
    args = parser.parse_args(argv)

    started = time.strftime("%Y-%m-%dT%H:%M:%S%z")
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    checks: list[tuple[str, bool, str]] = []
    notes: list[tuple[str, bool, str]] = []
    source = (Path(args.source).resolve() if args.source else (BACKEND_DIR / "test_platform.db").resolve())
    SOURCE_PATH = source
    print(f"[env] backend_dir={BACKEND_DIR}")
    print(f"[env] source={source}")
    if not source.is_file():
        print("[env] ERROR 源库不存在，无法演练存量副本")
        return 2

    source_hash_before = sha256_file(source)
    side_before = sidecar_hashes(source)
    print(f"[env] source size={source.stat().st_size} sha256(before)={source_hash_before}")
    print(f"[env] source sidecars(before)={side_before}")

    workdir = Path(tempfile.mkdtemp(prefix="t02_migrations_")).resolve()
    print(f"[env] isolated workdir={workdir}")
    assert workdir != source.parent, "临时目录不能是源库目录"
    assert source not in list(workdir.parents), "源库不能在临时目录内"
    assert workdir not in list(source.parents), "临时目录不能在源库目录内"

    apply_pragma, pragma_name = resolve_pragma_applier(workdir)
    load_fingerprint_helpers()
    empty_state: dict = {}
    legacy_state: dict = {}
    try:
        empty_state = scenario_empty(workdir, checks, apply_pragma)
    except StepError as exc:
        checks.append(("empty:scenario-aborted", False, str(exc)))
        print(f"[empty] ABORTED: {exc}")
    try:
        legacy_state = scenario_legacy(
            workdir, source, empty_state.get("after_upgrade", {}), checks, notes, apply_pragma
        )
    except StepError as exc:
        checks.append(("legacy:scenario-aborted", False, str(exc)))
        print(f"[legacy] ABORTED: {exc}")

    source_hash_after = sha256_file(source)
    side_after = sidecar_hashes(source)
    checks.append(
        ("source:sha256-unchanged", source_hash_before == source_hash_after, f"{source_hash_before} -> {source_hash_after}")
    )
    # 只读 sqlite backup API 打开 WAL 库时，SQLite 可能物化空的 -wal/-shm 派生文件；
    # 已经存在的 sidecar 必须字节不变；新建的 sidecar 只允许是空 WAL/派生共享内存，
    # 并作为观察项记录，不伪造「无任何文件变化」。
    preexisting_ok = all(
        side_after[name] == side_before[name]
        for name in side_before
        if side_before[name] is not None
    )
    checks.append(
        (
            "source:preexisting-sidecars-unchanged",
            preexisting_ok,
            f"{side_before} -> {side_after}",
        )
    )
    materialized = [
        name for name in side_after
        if side_before.get(name) is None and side_after.get(name) is not None
    ]
    if materialized:
        sizes = {
            name: (source.with_name(name).stat().st_size if source.with_name(name).exists() else None)
            for name in materialized
        }
        notes.append(
            (
                "source:readonly-backup-materialized-sidecars (OBSERVATION, NOT DATA CHANGE)",
                True,
                f"new_sidecars={materialized} sizes={sizes}（只读 backup API 打开 WAL 库的派生文件，主库 SHA-256 未变）",
            )
        )

    failed = [c for c in checks if not c[1]]
    print("\n================ 校验汇总 ================")
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    if notes:
        print("\n================ 已知缺陷/观察（不作为门禁，须如实上报） ================")
        for name, ok, detail in notes:
            print(f"  [{'MET' if ok else 'NOT MET'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"\nRESULT: {'PASS' if not failed else 'FAIL'} ({len(checks) - len(failed)}/{len(checks)} checks)")

    if args.report:
        report_path = Path(args.report)
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report = {
            "started": started,
            "finished": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
            "backend_dir": str(BACKEND_DIR),
            "source": str(source),
            "source_size": source.stat().st_size,
            "source_sha256_before": source_hash_before,
            "source_sha256_after": source_hash_after,
            "source_sidecars_before": side_before,
            "source_sidecars_after": side_after,
            "pragma_applier": pragma_name,
            "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
            "known_limitations": [{"name": n, "met": o, "detail": d} for n, o, d in notes],
            "failed": len(failed),
            "empty": empty_state,
            "legacy": legacy_state,
        }
        report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        print(f"[report] {report_path}")

    if args.keep:
        print(f"[env] kept workdir={workdir}")
    else:
        shutil.rmtree(workdir, ignore_errors=True)

    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
