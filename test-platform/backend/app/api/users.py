from fastapi import APIRouter, Depends, HTTPException, status, Request
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_
from typing import Optional

from app.database import get_db
from app.api.auth import get_current_user, get_current_admin, get_pc_identifier
from app.models import User
from app.schemas import (
    UserResponse, UserUpdate, ResponseModel, PaginationParams,
    UserRole, UserStatus
)
from app.services.auth import get_password_hash

router = APIRouter(prefix="/users", tags=["用户管理"])


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


@router.put("/{user_id}", response_model=ResponseModel)
async def update_user(
    user_id: int,
    user_data: UserUpdate,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """更新用户信息（管理员）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 更新字段
    if user_data.role is not None:
        user.role = user_data.role
    if user_data.status is not None:
        user.status = user_data.status
    
    await db.commit()
    await db.refresh(user)
    
    return ResponseModel(
        code=200,
        message="更新成功",
        data=UserResponse.model_validate(user)
    )


@router.post("/{user_id}/reset-password", response_model=ResponseModel)
async def reset_password(
    user_id: int,
    new_password: str,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """重置用户密码（管理员）"""
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    user.password_hash = get_password_hash(new_password)
    await db.commit()
    
    return ResponseModel(code=200, message="密码重置成功")


@router.delete("/{user_id}", response_model=ResponseModel)
async def delete_user(
    user_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(get_current_admin)
):
    """删除用户（管理员）"""
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="不能删除自己")
    
    result = await db.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    
    if not user:
        raise HTTPException(status_code=404, detail="用户不存在")
    
    # 软删除：将状态设为disabled
    user.status = "disabled"
    await db.commit()
    
    return ResponseModel(code=200, message="用户已禁用")
