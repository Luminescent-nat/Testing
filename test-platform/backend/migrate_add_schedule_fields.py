"""为现有 test_tasks 表添加调度字段：schedule_type / scheduled_time / next_run_at。

用法：python migrate_add_schedule_fields.py
（db 路径按脚本所在目录定位，与 migrate_add_plan_column.py 一致）
"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "test_platform.db")

# (列名, DDL 类型)
SCHEDULE_COLUMNS = [
    ("schedule_type", "VARCHAR(20) NOT NULL DEFAULT 'immediate'"),
    ("scheduled_time", "VARCHAR(50)"),
    ("next_run_at", "DATETIME"),
]

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查列是否已存在
    cursor.execute("PRAGMA table_info(test_tasks)")
    columns = [row[1] for row in cursor.fetchall()]

    for name, ddl in SCHEDULE_COLUMNS:
        if name in columns:
            print(f"{name} 列已存在，跳过")
        else:
            cursor.execute(f"ALTER TABLE test_tasks ADD COLUMN {name} {ddl}")
            conn.commit()
            print(f"已添加 {name} 列到 test_tasks 表")

    conn.close()

if __name__ == "__main__":
    migrate()
