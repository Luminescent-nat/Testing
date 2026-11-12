#!/usr/bin/env python3
"""task-19 / V1-01：003_device_version 迁移演练（空库 + 存量副本，数据保留）。

只读复制 backend/test_platform.db 到 tempfile 副本，绝不改真实库：
- 空库：0817 -> 002 -> 003 upgrade head；devices.version 存在且默认 1；插入设备行验证默认值；
  downgrade 002（回退 003）后 version 列移除、设备行仍保留；再 upgrade head 恢复且行仍在。
- 存量副本（test_tasks=10 / test_records=98 / devices=26）：stamp 0817 后 upgrade head，
  version 列补齐且既有设备 version=1、行数全部保留；downgrade 002 后 version 列移除、行数仍保留；
  再 upgrade head 恢复。源库 SHA-256 前后一致。
"""
from __future__ import annotations

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

BACKEND = Path(__file__).resolve().parents[4] / "test-platform" / "backend"
SOURCE = BACKEND / "test_platform.db"
TABLES = ("test_tasks", "test_records", "devices", "users")


def sha(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def url(db: Path) -> str:
    return "sqlite:///" + db.resolve().as_posix()


def counts(db: Path) -> dict:
    conn = sqlite3.connect(str(db))
    try:
        out = {}
        for t in TABLES:
            if conn.execute("SELECT 1 FROM sqlite_master WHERE type='table' AND name=?", (t,)).fetchone():
                out[t] = conn.execute(f"SELECT count(*) FROM {t}").fetchone()[0]
        return out
    finally:
        conn.close()


def device_columns(db: Path) -> list:
    conn = sqlite3.connect(str(db))
    try:
        return [r[1] for r in conn.execute("PRAGMA table_info(devices)")]
    finally:
        conn.close()


def run_alembic(label: str, db: Path, args: list) -> int:
    env = os.environ.copy()
    env["DATABASE_URL"] = url(db)
    env["SECRET_KEY"] = "migration-drill-only-secret-key-32chars"
    cmd = [sys.executable, "-m", "alembic", *args]
    print(f"\n[{label}] $ {' '.join(cmd)}  DATABASE_URL={url(db)}")
    proc = subprocess.run(cmd, cwd=str(BACKEND), env=env, capture_output=True,
                          text=True, encoding="utf-8", errors="replace")
    print(f"[{label}] exit={proc.returncode}")
    for stream in (proc.stdout, proc.stderr):
        if stream.strip():
            print(f"[{label}] {stream.strip()}")
    return proc.returncode


def main() -> int:
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    checks: list = []
    src_before = sha(SOURCE)
    print(f"[source] {SOURCE} size={SOURCE.stat().st_size} sha256={src_before}")

    work = Path(tempfile.mkdtemp(prefix="t19_devver_")).resolve()
    print(f"[work] {work}")

    # ---------------- 空库 ----------------
    empty = work / "empty.db"
    run_alembic("empty/upgrade-head", empty, ["upgrade", "head"])
    cols = device_columns(empty)
    checks.append(("empty:devices-version-column", "version" in cols, str(cols)))
    conn = sqlite3.connect(str(empty))
    try:
        conn.execute("INSERT INTO devices (serial_number, status, pc_identifier) VALUES ('T19-EMPTY','online','')")
        conn.commit()
        v = conn.execute("SELECT version FROM devices WHERE serial_number='T19-EMPTY'").fetchone()[0]
    finally:
        conn.close()
    checks.append(("empty:default-version-1", v == 1, f"version={v}"))
    run_alembic("empty/downgrade-002", empty, ["downgrade", "002_idempotency"])
    cols_down = device_columns(empty)
    checks.append(("empty:downgrade-drops-version", "version" not in cols_down, str(cols_down)))
    checks.append(("empty:downgrade-keeps-device-row", counts(empty).get("devices") == 1, str(counts(empty))))
    run_alembic("empty/re-upgrade-head", empty, ["upgrade", "head"])
    checks.append(("empty:re-upgrade-restores-version", "version" in device_columns(empty), ""))
    checks.append(("empty:re-upgrade-keeps-device-row", counts(empty).get("devices") == 1, str(counts(empty))))

    # ---------------- 存量副本 ----------------
    legacy = work / "legacy_backup.db"
    shutil.copyfile(SOURCE, legacy)
    print(f"[legacy] copy={legacy} sha256={sha(legacy)}")
    pre = counts(legacy)
    print(f"[legacy] counts(before)={pre}")
    checks.append(("legacy:copy-sha-matches-source", sha(legacy) == src_before, ""))
    checks.append(("legacy:pre-has-no-version-column", "version" not in device_columns(legacy), ""))
    run_alembic("legacy/stamp-0817", legacy, ["stamp", "0817df993d8b"])
    run_alembic("legacy/upgrade-head", legacy, ["upgrade", "head"])
    post_up = counts(legacy)
    print(f"[legacy] counts(after upgrade head)={post_up}")
    checks.append(("legacy:upgrade-adds-version-column", "version" in device_columns(legacy), ""))
    conn = sqlite3.connect(str(legacy))
    try:
        versions = [r[0] for r in conn.execute("SELECT version FROM devices")]
    finally:
        conn.close()
    checks.append(("legacy:existing-devices-version-1", all(v == 1 for v in versions) and len(versions) == pre.get("devices"), f"n={len(versions)} sample={versions[:3]}"))
    checks.append(("legacy:upgrade-preserves-row-counts", post_up == pre, f"{pre} -> {post_up}"))
    run_alembic("legacy/downgrade-002", legacy, ["downgrade", "002_idempotency"])
    post_down = counts(legacy)
    print(f"[legacy] counts(after downgrade 002)={post_down}")
    checks.append(("legacy:downgrade-drops-version-column", "version" not in device_columns(legacy), ""))
    checks.append(("legacy:downgrade-preserves-row-counts", post_down == pre, f"{pre} -> {post_down}"))
    run_alembic("legacy/re-upgrade-head", legacy, ["upgrade", "head"])
    post_re = counts(legacy)
    checks.append(("legacy:re-upgrade-adds-version-column", "version" in device_columns(legacy), ""))
    checks.append(("legacy:re-upgrade-preserves-row-counts", post_re == pre, f"{pre} -> {post_re}"))

    src_after = sha(SOURCE)
    checks.append(("source:sha256-unchanged", src_before == src_after, f"{src_before} -> {src_after}"))

    print("\n================ 汇总 ================")
    failed = [c for c in checks if not c[1]]
    for name, ok, detail in checks:
        print(f"  [{'PASS' if ok else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"\nRESULT: {'PASS' if not failed else 'FAIL'} ({len(checks) - len(failed)}/{len(checks)})")
    report = {
        "started": time.strftime("%Y-%m-%dT%H:%M:%S%z"),
        "source": str(SOURCE), "source_sha256_before": src_before, "source_sha256_after": src_after,
        "empty_counts": counts(empty), "legacy_pre": pre, "legacy_after_upgrade": post_up,
        "legacy_after_downgrade": post_down, "legacy_after_reupgrade": post_re,
        "checks": [{"name": n, "ok": o, "detail": d} for n, o, d in checks],
        "result": "PASS" if not failed else "FAIL",
    }
    (Path(__file__).resolve().parent / "migration-003-summary.json").write_text(
        json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    shutil.rmtree(work, ignore_errors=True)
    return 0 if not failed else 1


if __name__ == "__main__":
    raise SystemExit(main())
