"""确保 E2E 测试管理员账号存在且密码正确。"""
import asyncio
import sys

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
