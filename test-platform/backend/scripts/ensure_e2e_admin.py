"""确保隔离 E2E 环境中的测试管理员账号存在且密码正确。"""
import asyncio
import os
import sys


def validate_e2e_environment():
    """未显式选择隔离数据库时拒绝创建或重置管理员。"""
    if os.environ.get("E2E_TEST_MODE") != "1":
        raise SystemExit("拒绝执行：E2E 管理员初始化要求 E2E_TEST_MODE=1")
    database_url = os.environ.get("DATABASE_URL", "")
    expected_url = os.environ.get("E2E_DATABASE_URL", "")
    if not expected_url or database_url != expected_url:
        raise SystemExit("拒绝执行：DATABASE_URL 必须与显式设置的 E2E_DATABASE_URL 一致")
    if database_url == "sqlite+aiosqlite:///./test_platform.db":
        raise SystemExit("拒绝执行：E2E 不得使用平台默认数据库")


validate_e2e_environment()

sys.path.insert(0, ".")

from app.database import AsyncSessionLocal
from app.models import User
from app.services.auth import get_password_hash
from sqlalchemy import select

E2E_ADMIN_USER = "e2e-admin"
E2E_ADMIN_PASS = "e2e-admin-pass"


async def main():
    async with AsyncSessionLocal() as db:
        result = await db.execute(select(User).where(User.username == E2E_ADMIN_USER))
        user = result.scalar_one_or_none()
        if user:
            user.role = "admin"
            user.status = "active"
            user.password_hash = get_password_hash(E2E_ADMIN_PASS)
            print(f"更新管理员账号: {user.username}")
        else:
            user = User(
                username=E2E_ADMIN_USER,
                password_hash=get_password_hash(E2E_ADMIN_PASS),
                role="admin",
                status="active",
                pc_identifier="e2e-pc",
            )
            db.add(user)
            print(f"创建管理员账号: {user.username}")
        await db.commit()


if __name__ == "__main__":
    asyncio.run(main())
