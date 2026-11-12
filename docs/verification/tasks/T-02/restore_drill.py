#!/usr/bin/env python3
"""T-02 增补：合规回滚路径演练——「备份副本 SHA-256 + 从备份恢复」。

重要定位（RR-T02）：本演练验证的是**运维层恢复路径**（备份→哈希→异常后恢复→哈希一致），
**不能替代 alembic 数据保留回滚证据**（初始迁移 downgrade base 会删表，R20 仍不通过）。

全部操作只在 tempfile 隔离目录的副本上进行，源库只读（前后 SHA-256 必须一致）。
"""
from __future__ import annotations

import hashlib
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import time
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[4] / "test-platform" / "backend"
SOURCE = BACKEND_DIR / "test_platform.db"


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def sidecars(source: Path) -> dict:
    out = {}
    for suffix in ("-wal", "-shm", "-journal"):
        p = source.with_name(source.name + suffix)
        out[p.name] = sha256(p) if p.exists() else None
    return out


def row_counts(db: Path) -> dict:
    conn = sqlite3.connect(str(db))
    try:
        counts = {}
        for t in ("test_tasks", "test_records", "users", "devices"):
            if conn.execute(
                "SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)
            ).fetchone():
                counts[t] = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        return counts
    finally:
        conn.close()


def run_alembic(label: str, db: Path, args: list[str]) -> int:
    url = "sqlite:///" + db.as_posix()
    env = dict(**{k: v for k, v in __import__("os").environ.items()})
    env["DATABASE_URL"] = url
    env["SECRET_KEY"] = "restore-drill-only-secret-key-32chars"
    cmd = [sys.executable, "-m", "alembic", *args]
    print(f"[{label}] $ {' '.join(cmd)}  DATABASE_URL={url}")
    proc = subprocess.run(cmd, cwd=str(BACKEND_DIR), env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    print(f"[{label}] exit={proc.returncode}")
    for stream in (proc.stdout, proc.stderr):
        if stream.strip():
            print(f"[{label}] {stream.strip()}")
    return proc.returncode


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    checks: list[tuple[str, bool, str]] = []

    src_hash_0, src_side_0 = sha256(SOURCE), sidecars(SOURCE)
    print(f"[source] {SOURCE} size={SOURCE.stat().st_size} sha256={src_hash_0}")
    print(f"[source] sidecars={src_side_0}")

    work = Path(tempfile.mkdtemp(prefix="t02_restore_"))
    print(f"[work] isolated dir={work}")
    backup = work / "backup_of_source.db"   # 只读备份副本（永不改动）
    live = work / "live_copy.db"            # 模拟「被误操作的生产副本」
    shutil.copyfile(SOURCE, backup)
    shutil.copyfile(SOURCE, live)
    checks.append(("backup-copy-sha256-matches-source", sha256(backup) == src_hash_0, sha256(backup)))
    checks.append(("live-copy-sha256-matches-source", sha256(live) == src_hash_0, sha256(live)))
    print(f"[backup] sha256={sha256(backup)} counts={row_counts(backup)}")

    # 模拟误操作：对 live 副本执行 stamp head + upgrade head（alembic 元数据变更）
    rc1 = run_alembic("live/stamp-head", live, ["stamp", "head"])
    rc2 = run_alembic("live/upgrade-head", live, ["upgrade", "head"])
    changed = (sha256(live) != src_hash_0)
    print(f"[live] after stamp+upgrade sha256={sha256(live)} counts={row_counts(live)} changed={changed}")
    checks.append(("live-changed-after-alembic", changed and rc1 == 0 and rc2 == 0, f"rc1={rc1} rc2={rc2} changed={changed}"))

    # 从备份恢复：用只读备份副本整体覆盖 live（运维恢复路径，非 alembic 回滚）
    shutil.copyfile(backup, live)
    restored_hash = sha256(live)
    checks.append(("live-restored-sha256-equals-backup", restored_hash == sha256(backup), restored_hash))
    checks.append(("restored-data-counts-preserved", row_counts(live) == row_counts(backup),
                   f"{row_counts(live)} vs {row_counts(backup)}"))
    conn = sqlite3.connect(str(live))
    try:
        checks.append(("restored-integrity-ok", conn.execute("PRAGMA integrity_check").fetchone()[0] == "ok", ""))
        checks.append(("restored-no-alembic-version", conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type='table' AND name='alembic_version'").fetchone() is None, ""))
    finally:
        conn.close()
    print(f"[restored] sha256={restored_hash} counts={row_counts(live)}")

    # 源库全程只读
    src_hash_1, src_side_1 = sha256(SOURCE), sidecars(SOURCE)
    checks.append(("source-sha256-unchanged", src_hash_1 == src_hash_0, f"{src_hash_0} -> {src_hash_1}"))
    checks.append(("source-sidecars-unchanged", src_side_1 == src_side_0, ""))

    print("\n================ 汇总 ================")
    failed = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"\nNOTE: 本演练仅为运维恢复路径证据，不能替代 alembic 数据保留回滚证据（R20 另行判定）。")
    print(f"RESULT: {'PASS' if not failed else 'FAIL'} ({len(checks) - len(failed)}/{len(checks)})")
    return 0 if not failed else 1


if __name__ == "__main__":
    print(f"[time] finished_at={time.strftime('%Y-%m-%dT%H:%M:%S%z')}")
    raise SystemExit(main())
