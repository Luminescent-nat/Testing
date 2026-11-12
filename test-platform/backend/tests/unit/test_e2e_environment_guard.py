"""E2E 固定管理员脚本的环境保护测试。"""
import os
from pathlib import Path
import subprocess
import sys
import sqlite3

from sqlalchemy import create_engine

from app.database import Base


BACKEND_DIR = Path(__file__).resolve().parents[2]
SCRIPT = BACKEND_DIR / "scripts" / "ensure_e2e_admin.py"


def run_with_env(env_overrides):
    env = os.environ.copy()
    for key in ("E2E_TEST_MODE", "DATABASE_URL", "E2E_DATABASE_URL"):
        env.pop(key, None)
    env["PYTHONDONTWRITEBYTECODE"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"
    env.update(env_overrides)
    return subprocess.run(
        [sys.executable, str(SCRIPT)],
        cwd=BACKEND_DIR,
        env=env,
        capture_output=True,
        text=True,
        encoding="utf-8",
        errors="replace",
        timeout=10,
        check=False,
    )


def test_e2e_admin_script_rejects_unmarked_environment():
    """未显式进入 E2E 模式时，脚本必须在导入应用和写库前拒绝。"""
    result = run_with_env({})
    assert result.returncode != 0
    assert "E2E_TEST_MODE=1" in result.stdout + result.stderr


def test_e2e_admin_script_rejects_default_database():
    """即使进入 E2E 模式，也不得重置平台默认数据库中的账号。"""
    default_url = "sqlite+aiosqlite:///./test_platform.db"
    result = run_with_env({
        "E2E_TEST_MODE": "1",
        "DATABASE_URL": default_url,
        "E2E_DATABASE_URL": default_url,
    })
    assert result.returncode != 0
    assert "默认数据库" in result.stdout + result.stderr


def test_e2e_admin_script_creates_admin_in_isolated_database(tmp_path):
    """合法隔离环境下正常建号，并验证实际落库角色与状态。"""
    db_path = tmp_path / "e2e.db"
    sync_engine = create_engine(f"sqlite:///{db_path.as_posix()}")
    Base.metadata.create_all(sync_engine)
    sync_engine.dispose()

    database_url = f"sqlite+aiosqlite:///{db_path.as_posix()}"
    result = run_with_env({
        "E2E_TEST_MODE": "1",
        "DATABASE_URL": database_url,
        "E2E_DATABASE_URL": database_url,
    })
    assert result.returncode == 0, result.stdout + result.stderr

    with sqlite3.connect(db_path) as connection:
        row = connection.execute(
            'SELECT role, status FROM users WHERE username = "e2e-admin"'
        ).fetchone()
    assert row == ("admin", "active")
