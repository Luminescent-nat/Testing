"""为现有数据库创建/补齐 knowledge_entries 测试知识库表。"""
import sqlite3
import os

DB_PATH = os.path.join(os.path.dirname(__file__), "test_platform.db")

CREATE_SQL = """
CREATE TABLE IF NOT EXISTS knowledge_entries (
    id INTEGER NOT NULL PRIMARY KEY AUTOINCREMENT,
    title VARCHAR(200) NOT NULL,
    entry_type VARCHAR(50) NOT NULL DEFAULT 'document',
    category VARCHAR(100),
    tags JSON,
    content TEXT,
    chunks JSON,
    embedding JSON,
    source_type VARCHAR(50) NOT NULL DEFAULT 'manual',
    source_file VARCHAR(500),
    status VARCHAR(50) NOT NULL DEFAULT 'draft',
    metadata JSON,
    pass_count INTEGER DEFAULT 0,
    fail_count INTEGER DEFAULT 0,
    hit_count INTEGER DEFAULT 0,
    created_by INTEGER,
    created_at DATETIME,
    updated_at DATETIME,
    FOREIGN KEY (created_by) REFERENCES users (id)
);
"""

INDEX_SQL = """
CREATE INDEX IF NOT EXISTS ix_knowledge_entries_id ON knowledge_entries (id);
CREATE INDEX IF NOT EXISTS ix_knowledge_entries_entry_type ON knowledge_entries (entry_type);
CREATE INDEX IF NOT EXISTS ix_knowledge_entries_category ON knowledge_entries (category);
CREATE INDEX IF NOT EXISTS ix_knowledge_entries_status ON knowledge_entries (status);
"""

COLUMNS = [
    ("embedding", "JSON"),
]


def migrate():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='knowledge_entries'")
    if cursor.fetchone():
        print("knowledge_entries 表已存在，检查并补齐字段")
    else:
        cursor.executescript(CREATE_SQL + INDEX_SQL)
        print("已创建 knowledge_entries 表及索引")
        conn.commit()
        conn.close()
        return

    cursor.execute("PRAGMA table_info(knowledge_entries)")
    existing_columns = [row[1] for row in cursor.fetchall()]

    for name, dtype in COLUMNS:
        if name in existing_columns:
            print(f"{name} 列已存在，跳过")
        else:
            cursor.execute(f"ALTER TABLE knowledge_entries ADD COLUMN {name} {dtype}")
            print(f"已添加 {name} 列")

    cursor.executescript(INDEX_SQL)
    conn.commit()
    conn.close()


if __name__ == "__main__":
    migrate()
