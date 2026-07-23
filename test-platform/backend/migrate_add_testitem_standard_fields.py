"""为现有 test_items 表添加标准测试卡字段。"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "test_platform.db")

COLUMNS = [
    ("objective", "TEXT"),
    ("precondition", "TEXT"),
    ("steps", "TEXT"),
    ("expected_result", "TEXT"),
]


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("PRAGMA table_info(test_items)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    for name, dtype in COLUMNS:
        if name in existing_columns:
            print(f"{name} 列已存在，跳过")
        else:
            cursor.execute(f"ALTER TABLE test_items ADD COLUMN {name} {dtype}")
            print(f"已添加 {name} 列")

    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
