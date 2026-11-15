"""T-16 用户开通与账号闭环（R28，契约 user-administration-v1.0.md §2/§4/§6）。

- 首管理员初始化：仅空库允许，并发靠 username 唯一约束兜底（409）；
- 管理员建号：用户名唯一约束，重名/并发 409；
- 局部更新：事务内重查最后 active 管理员，防并发破坏管理闭环。
"""
import logging

from fastapi import HTTPException
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.schemas import UserCreateByAdmin, UserPatch
from app.services.auth import get_password_hash

logger = logging.getLogger(__name__)


async def register_first_admin(
    db: AsyncSession, *, username: str, password: str, pc_identifier: str
) -> User:
    """首管理员初始化（§2）：仅数据库无任何用户时允许，服务端强制 role=admin。

    并发双注册窗口由 username 唯一约束兜底：同时通过空库检查的两个请求，
    后提交者触发 IntegrityError → 409 系统正在并发初始化。
    """
    user_count = await db.scalar(select(func.count()).select_from(User))
    if user_count:
        raise HTTPException(status_code=403, detail="系统已完成初始化")

    admin = User(
        username=username,
        password_hash=get_password_hash(password),
        role="admin",
        status="active",
        pc_identifier=pc_identifier,
    )
    db.add(admin)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        logger.warning("并发首管理员初始化被唯一约束拦截: %s", username)
        raise HTTPException(status_code=409, detail="系统正在并发初始化")
    await db.refresh(admin)
    return admin


async def create_user_by_admin(db: AsyncSession, *, data: UserCreateByAdmin) -> User:
    """管理员创建后续账号（§4）：唯一约束防并发重名（至多一行，重放 409）。"""
    user = User(
        username=data.username,
        password_hash=get_password_hash(data.password),
        role=data.role.value,
        status=data.status.value,
        pc_identifier=data.pc_identifier,
    )
    db.add(user)
    try:
        await db.commit()
    except IntegrityError:
        await db.rollback()
        raise HTTPException(status_code=409, detail="用户名已存在")
    await db.refresh(user)
    return user


async def patch_user(db: AsyncSession, *, target_id: int, patch: UserPatch) -> User:
    """局部更新 role/status（§6），含最后 active 管理员保护。

    保护在事务内重新检查（SELECT count 与 UPDATE 同事务，SQLite 写事务串行），
    防止并发禁用/降级破坏系统管理闭环；重复 PATCH 相同值幂等返回当前用户。
    """
    target = await db.get(User, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")

    new_role = patch.role.value if patch.role is not None else target.role
    new_status = patch.status.value if patch.status is not None else target.status

    # 本次变更会使一个 active 管理员失去管理员身份时，必须存在其他 active 管理员
    if target.role == "admin" and target.status == "active":
        losing_admin = (new_role != "admin") or (new_status != "active")
        if losing_admin:
            other_admins = await db.scalar(
                select(func.count()).select_from(User).where(
                    User.role == "admin",
                    User.status == "active",
                    User.id != target.id,
                )
            )
            if not other_admins:
                raise HTTPException(
                    status_code=409, detail="不能禁用或降级最后一个active管理员"
                )

    if patch.role is not None:
        target.role = new_role
    if patch.status is not None:
        target.status = new_status
    await db.commit()
    await db.refresh(target)
    return target


async def reset_user_password(
    db: AsyncSession, *, target_id: int, new_password: str
) -> None:
    """重置用户密码（管理员）：密码经请求体传入，不得走 URL query。"""
    target = await db.get(User, target_id)
    if target is None:
        raise HTTPException(status_code=404, detail="用户不存在")
    target.password_hash = get_password_hash(new_password)
    await db.commit()
