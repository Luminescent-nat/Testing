#!/usr/bin/env python3
"""004_task_deleted_at 迁移演练辅助（隔离临时库，不触碰真实库）。

用法：python alembic_004_drill.py <workdir>
步骤：upgrade head → 插入含软删除数据的任务 → downgrade 003（期望拒绝，非 0 退出）
      → 清空软删除数据 → downgrade 003（成功）→ upgrade head（成功）。
由 PowerShell 驱动逐步执行并记录退出码；本脚本只负责数据播种/清点。
"""
import sqlite3
import sys
from pathlib import Path


def main() -> int:
    mode = sys.argv[1]
    db = Path(sys.argv[2]) / "mig.db"
    conn = sqlite3.connect(str(db))
    try:
        if mode == "seed":
            conn.execute(
                "INSERT INTO test_tasks (user_id, device_id, selected_items, "
                "custom_parameters, status, progress_percent, schedule_type) "
                "VALUES (1,1,'[]','{}','completed',100,'immediate')"
            )
            conn.execute(
                "UPDATE test_tasks SET deleted_at='2026-11-12 09:00:00' WHERE id=1"
            )
            conn.execute(
                "INSERT INTO test_tasks (user_id, device_id, selected_items, "
                "custom_parameters, status, progress_percent, schedule_type) "
                "VALUES (1,1,'[]','{}','completed',100,'immediate')"
            )
            conn.commit()
            rows = conn.execute(
                "SELECT COUNT(*), SUM(deleted_at IS NOT NULL) FROM test_tasks"
            ).fetchall()
            print("seeded rows(total, soft-deleted):", rows)
        elif mode == "count":
            rows = conn.execute("SELECT COUNT(*), SUM(deleted_at IS NOT NULL) FROM test_tasks").fetchall()
            print("rows(total, soft-deleted):", rows)
        elif mode == "clear-soft-deleted":
            conn.execute("DELETE FROM test_tasks WHERE deleted_at IS NOT NULL")
            conn.commit()
            print("cleared soft-deleted rows")
        else:
            raise SystemExit(f"unknown mode: {mode}")
    finally:
        conn.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
