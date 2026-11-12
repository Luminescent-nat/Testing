#!/usr/bin/env python3
"""T-02 Alembic + SQLite 外键迁移演练（只在隔离临时目录/副本上执行）。

用法（在 backend 目录）：
    python scripts/verify_migrations.py --report docs/verification/tasks/T-02/migration-summary.json

安全红线（见 docs/design/scheduler-and-data.md 第 5 节）：
- 源库（默认 backend/test_platform.db）只读：只用二进制读取复制字节并计算 SHA-256，
  演练前后源库与 WAL/SHM sidecar 的 SHA-256 必须完全一致；
- 所有 alembic 子进程的 DATABASE_URL 都指向 tempfile 隔离目录内的 .db 空库/副本，
  绝不修改真实库，绝不对真实库执行 create_all / stamp / upgrade / downgrade；
- 任一 alembic 步骤失败都保留原始输出并以非 0 退出码结束，不静默吞掉。

演练内容：
1. 空库：alembic upgrade head -> 记录表清单/版本/integrity_check -> --sql 离线核对
   -> downgrade base -> 再次 upgrade head -> 唯一键/非法外键写入必须失败；
2. 存量库备份副本：先只读复制源库 -> 与空库结构核对一致 -> --sql 核对 ->
   仅因「结构与 head 完全一致」在副本上 stamp head（非新装默认命令）->
   upgrade head -> downgrade base -> 再次 upgrade head -> 约束与完整性核对。
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

BACKEND_DIR = Path(__file__).resolve().parents[1]

# 初始迁移 0817df993d8b 建成的全部业务表（来源：源库 sqlite_master 只读核对）
EXPECTED_TABLES = [
    "baselines",
    "devices",
    "failure_patterns",
    "golden_cases",
    "knowledge_entries",
    "test_items",
    "test_modules",
    "test_records",
    "test_tasks",
    "test_tools",
    "users",
]
COUNT_TABLES = ("test_tasks", "test_records")
SOURCE_PATH: Path | None = None


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

        return {
            "foreign_keys_pragma": fk_pragma,
            "duplicate_username_rejected": dup_user,
            "duplicate_serial_number_rejected": dup_serial,
            "legal_foreign_key_accepted": legal,
            "illegal_foreign_key_rejected": illegal,
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


def scenario_empty(workdir: Path, checks, apply_pragma) -> dict:
    print("\n================ 场景 A：新装空库 ================")
    db = workdir / "empty.db"
    url = db_url(db)

    run_alembic("empty/upgrade", url, ["upgrade", "head"], checks)
    up = read_state(db, "empty/after-upgrade", checks)
    checks.append(("empty:table-set-equals-expected", up["tables"] == sorted(EXPECTED_TABLES), str(up["tables"])))
    checks.append(("empty:alembic-version-present", bool(up["alembic_version"]), str(up["alembic_version"])))
    checks.append(("empty:integrity-ok", up["integrity_check"] == ["ok"], str(up["integrity_check"])))
    checks.append(("empty:no-fk-violations", up["foreign_key_violations"] == [], str(up["foreign_key_violations"])))

    offline = run_alembic("empty/offline-sql", url, ["upgrade", "head", "--sql"], checks)
    check_offline_sql(offline.stdout, "empty", checks)

    run_alembic("empty/downgrade-base", url, ["downgrade", "base"], checks)
    down = read_state(db, "empty/after-downgrade", checks)
    checks.append(("empty:tables-dropped-after-downgrade", down["tables"] == [], str(down["tables"])))

    run_alembic("empty/upgrade-again", url, ["upgrade", "head"], checks)
    final = read_state(db, "empty/after-reupgrade", checks)
    checks.append(("empty:reupgrade-table-set", final["tables"] == sorted(EXPECTED_TABLES), str(final["tables"])))
    checks.append(("empty:reupgrade-integrity", final["integrity_check"] == ["ok"], str(final["integrity_check"])))

    run_alembic("empty/current", url, ["current"], checks)
    constraints = probe_constraints(db, "empty", checks, apply_pragma)
    return {
        "after_upgrade": up,
        "after_downgrade": down,
        "after_reupgrade": final,
        "constraints": constraints,
    }


def scenario_legacy(workdir: Path, source: Path, empty_state: dict, checks, notes, apply_pragma) -> dict:
    print("\n================ 场景 B：存量库备份副本（只读复制） ================")
    legacy = workdir / "legacy_backup.db"
    shutil.copyfile(source, legacy)  # 只读复制字节，不打开源库写入
    print(f"[legacy] copy {source} -> {legacy}")
    print(f"[legacy] source_size={source.stat().st_size} copy_size={legacy.stat().st_size}")
    print(f"[legacy] copy_sha256={sha256_file(legacy)}")

    pre = read_state(legacy, "legacy/before", checks)
    checks.append(("legacy:avoid-db-already-migrated", pre["alembic_version"] is None, str(pre["alembic_version"])))
    expected_tables = empty_state.get("tables", sorted(EXPECTED_TABLES))
    checks.append(("legacy:pre-schema-matches-head", pre["tables"] == expected_tables, f"pre={pre['tables']} expected={expected_tables}"))
    print(f"[legacy] counts(before)={pre['counts']}")

    url = db_url(legacy)
    offline = run_alembic("legacy/offline-sql", url, ["upgrade", "head", "--sql"], checks)
    check_offline_sql(offline.stdout, "legacy", checks)

    # 存量库为 create_all 建立、无 alembic_version。结构与 head 完全一致已在上面独立核对，
    # 按设计第 5 节允许在「副本」上 stamp head；这绝不是新装默认命令。
    run_alembic("legacy/stamp-head", url, ["stamp", "head"], checks)
    run_alembic("legacy/upgrade-head", url, ["upgrade", "head"], checks)
    up = read_state(legacy, "legacy/after-upgrade", checks)
    checks.append(("legacy:integrity-after-upgrade", up["integrity_check"] == ["ok"], str(up["integrity_check"])))
    print(f"[legacy] counts(after_upgrade)={up['counts']}")

    run_alembic("legacy/downgrade-base", url, ["downgrade", "base"], checks)
    down = read_state(legacy, "legacy/after-downgrade", checks)
    print(f"[legacy] counts(after_downgrade)={down['counts']}")

    run_alembic("legacy/upgrade-again", url, ["upgrade", "head"], checks)
    final = read_state(legacy, "legacy/after-reupgrade", checks)
    checks.append(("legacy:reupgrade-table-set", final["tables"] == sorted(EXPECTED_TABLES), str(final["tables"])))
    checks.append(("legacy:reupgrade-integrity", final["integrity_check"] == ["ok"], str(final["integrity_check"])))
    print(f"[legacy] counts(after_reupgrade)={final['counts']}")
    # 如实记录（已知缺陷，不作为本任务契约门禁）：初始迁移的 downgrade base 会删表，
    # 存量数据在回滚演练副本中不保留；设计第 5 节“回滚恢复原结构且保留原数据”
    # 对初始迁移尚不满足，作为遗留项在 result.md 中报告，不伪造通过。
    data_preserved = bool(pre["counts"]) and down["counts"] == pre["counts"] and final["counts"] == pre["counts"]
    notes.append(
        (
            "legacy:rollback-preserves-original-data (KNOWN DEFECT, NOT A GATE)",
            data_preserved,
            f"before={pre['counts']} after_downgrade={down['counts']} after_reupgrade={final['counts']}",
        )
    )

    run_alembic("legacy/current", url, ["current"], checks)
    constraints = probe_constraints(legacy, "legacy", checks, apply_pragma)
    return {
        "before": pre,
        "after_upgrade": up,
        "after_downgrade": down,
        "after_reupgrade": final,
        "constraints": constraints,
        "data_preserved_on_rollback": data_preserved,
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
    checks.append(("source:sidecars-unchanged", side_before == side_after, f"{side_before} -> {side_after}"))

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
