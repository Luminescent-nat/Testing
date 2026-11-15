from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional

from app.database import get_db
from app.api.auth import get_current_user, get_current_admin, get_pc_identifier
from app.models import User
from app.schemas import (
    UserCreateByAdmin, UserPatch, ResetPasswordRequest,
    UserResponse, ResponseModel, PaginationParams,
    UserRole, UserStatus
)
from app.services import user_admin


router = APIRouter(prefix="/users", tags=["用户管理"])


@router.post("", response_model=ResponseModel, status_code=201)
async def create_user(
    user_data: UserCreateByAdmin,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """创建后续账号（契约 user-administration §4，唯一正常开通入口，仅 active 管理员）。"""
    user = await user_admin.create_user_by_admin(db, data=user_data)
    return ResponseModel(
        code=201,
        message="用户创建成功",
        data=UserResponse.model_validate(user)
    )


@router.get("", response_model=ResponseModel)
async def list_users(
    params: PaginationParams = Depends(),
    username: Optional[str] = None,
    role: Optional[UserRole] = None,
    status: Optional[UserStatus] = None,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取用户列表（管理员）"""
    query = select(User)
    
    # 筛选条件
    if username:
        query = query.where(User.username.ilike(f"%{username}%"))
    if role:
        query = query.where(User.role == role)
    if status:
        query = query.where(User.status == status)
    
    # 获取总数
    count_result = await db.execute(query)
    total = len(count_result.scalars().all())
    
    # 分页
    query = query.offset((params.page - 1) * params.page_size).limit(params.page_size)
    result = await db.execute(query)
    users = result.scalars().all()
    
    return ResponseModel(
        code=200,
        data={
            "items": [UserResponse.model_validate(u) for u in users],
            "total": total,
            "page": params.page,
            "page_size": params.page_size
        }
    )


@router.get("/{user_id}", response_model=ResponseModel)
async def get_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """获取用户详情（管理员）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    return ResponseModel(code=200, data=UserResponse.model_validate(user))


@router.patch("/{user_id}", response_model=ResponseModel)
@router.put("/{user_id}", response_model=ResponseModel)
async def update_user(
    user_id: int,
    user_data: UserPatch,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """局部更新用户角色/状态（契约 user-administration §6）。

    PUT 为 legacy 兼容别名（前端存量调用），PATCH 为契约路径；两者同一服务，
    含最后 active 管理员保护（409）与幂等语义。
    """
    user = await user_admin.patch_user(db, target_id=user_id, patch=user_data)
    return ResponseModel(
        code=200,
        message="用户已更新",
        data=UserResponse.model_validate(user)
    )


@router.post("/{user_id}/reset-password", response_model=ResponseModel)
async def reset_password(
    user_id: int,
    body: ResetPasswordRequest,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """重置用户密码（管理员）。密码必须走请求体（T-16：URL query 会进访问日志）。"""
    await user_admin.reset_user_password(db, target_id=user_id, new_password=body.new_password)
    return ResponseModel(code=200, message="密码重置成功")


@router.delete("/{user_id}", response_model=ResponseModel)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除用户（管理员）：软删除=禁用，受最后 active 管理员保护约束。"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    # 复用 §6 更新服务：禁用同样不允许落在最后一个 active 管理员上
    await user_admin.patch_user(
        db, target_id=user_id, patch=UserPatch(status=UserStatus.DISABLED)
    )
    return ResponseModel(code=200, message="用户已禁用")
