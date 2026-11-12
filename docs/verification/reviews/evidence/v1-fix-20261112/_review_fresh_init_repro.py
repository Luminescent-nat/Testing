"""评审方 V1-05 独立复现：新装空库仅走 alembic upgrade，再次 init 幂等（无 table exists）。
临时库隔离（tempfile），不触碰真实 backend/test_platform.db。"""
import asyncio
import os
import sqlite3
import tempfile
from pathlib import Path

tmpdir = Path(tempfile.mkdtemp(prefix="review_fresh_init_"))
db = tmpdir / "fresh.db"
os.environ["DATABASE_URL"] = "sqlite+aiosqlite:///" + db.as_posix()
os.environ.setdefault("SECRET_KEY", "review-only-secret-key-0123456789abcdef")
# 确保 tool 清单校验等与启动无关（仅调 init_db，不启动 app）
import sys
sys.path.insert(0, str(Path(__file__).resolve().parents[5] / "test-platform" / "backend"))

import app.database as database


async def main():
    await database.init_db()
    action1 = "init#1 done"
    tables1 = sorted(
        r[0] for r in sqlite3.connect(str(db)).execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
        ).fetchall()
    )
    ver1 = sqlite3.connect(str(db)).execute("select version_num from alembic_version").fetchall()
    # 第二次 init_db：已在 head，应为幂等 no-op（不再 create_all / 不报 table exists）
    await database.init_db()
    tables2 = sorted(
        r[0] for r in sqlite3.connect(str(db)).execute(
            "select name from sqlite_master where type='table' and name not like 'sqlite_%'"
        ).fetchall()
    )
    ver2 = sqlite3.connect(str(db)).execute("select version_num from alembic_version").fetchall()
    print("action1:", action1)
    print("tables#1:", tables1)
    print("version#1:", ver1)
    print("tables#2:", tables2)
    print("version#2:", ver2)
    print("IDEMPOTENT:", tables1 == tables2 and ver1 == ver2)
    print("HAS_ALEMBIC_VERSION:", "alembic_version" in tables1)
    print("HAS_IDEMPOTENCY_TABLE:", "idempotency_records" in tables1)


asyncio.run(main())
