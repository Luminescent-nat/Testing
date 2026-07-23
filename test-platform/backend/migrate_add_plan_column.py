"""为现有 test_tasks 表添加 plan 列（JSON 可空）。"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "test_platform.db")

def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # 检查列是否已存在
    cursor.execute("PRAGMA table_info(test_tasks)")
    columns = [row[1] for row in cursor.fetchall()]

    if "plan" in columns:
        print("plan 列已存在，跳过迁移")
    else:
        cursor.execute("ALTER TABLE test_tasks ADD COLUMN plan TEXT")
        conn.commit()
        print("已添加 plan 列到 test_tasks 表")

    conn.close()

if __name__ == "__main__":
    migrate()
