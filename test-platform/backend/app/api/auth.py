from fastapi import APIRouter, Depends, HTTPException, status, Request
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel, Field
from typing import Optional

from app.config import get_settings
from app.database import get_db
from app.services.auth import (
    authenticate_user, create_access_token, decode_token,
    get_password_hash, get_user_by_username, update_last_login, verify_password
)
from app.models import User
from app.schemas import (
    UserCreate, UserLogin, Token, UserResponse, ResponseModel,
    UserUpdate, PaginationParams, FirstAdminRegistration
)


class PasswordChangeRequest(BaseModel):
    old_password: str = Field(..., min_length=6, max_length=32)
    new_password: str = Field(..., min_length=6, max_length=32)

router = APIRouter(prefix="/auth", tags=["认证"])
security = HTTPBearer()


def get_pc_identifier(request: Request) -> str:
    """获取客户端 PC 唯一标识。

    前端首次访问时生成 UUID 存入 localStorage，之后所有请求通过
    X-PC-Identifier 请求头上报；设备按该标识归属到具体操作人员的电脑。
    缺失时退化为客户端 IP（兜底，不能保证严格隔离）。
    """
    identifier = request.headers.get("X-PC-Identifier")
    if identifier:
        return identifier.strip()[:255]
    if request.client:
        return f"ip-{request.client.host}"
    return "unknown"


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: AsyncSession = Depends(get_db)
) -> User:
    """获取当前登录用户"""
    token = credentials.credentials
    payload = decode_token(token)
    
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    username = payload.get("sub")
    if not username:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="无效的认证凭据",
        )
    
    user = await get_user_by_username(db, username)
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户不存在",
        )
    
    if user.status != "active":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="用户已被禁用",
        )
    
    return user


async def get_current_admin(current_user: User = Depends(get_current_user)) -> User:
    """检查是否为管理员"""
    if current_user.role != "admin":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="需要管理员权限",
        )
    return current_user


@router.post("/registrations", response_model=ResponseModel, status_code=201)
async def register_first_admin(
    data: FirstAdminRegistration,
    db: AsyncSession = Depends(get_db)
):
    """首管理员初始化（契约 user-administration §2）。

    仅数据库无任何用户时允许公开创建，服务端强制 role=admin；
    已有用户后返回 403 系统已完成初始化，后续账号走 POST /users 由管理员创建。
    """
    from app.services.user_admin import register_first_admin as register_service

    user = await register_service(
        db,
        username=data.username,
        password=data.password,
        pc_identifier=data.pc_identifier,
    )
    return ResponseModel(
        code=201,
        message="首管理员创建成功",
        data=UserResponse.model_validate(user)
    )


@router.post("/register", response_model=ResponseModel)
async def register(
    user_data: UserCreate,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """用户注册。第一个注册用户自动设为 admin，后续用户为普通用户。"""
    from sqlalchemy import select as sa_select

    # 检查用户名是否已存在
    existing_user = await get_user_by_username(db, user_data.username)
    if existing_user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="用户名已存在"
        )

    # 判断是否为第一个用户
    user_count_result = await db.execute(sa_select(User))
    is_first_user = user_count_result.scalars().first() is None

    # 注册开关：首个用户（自动成为 admin）始终允许注册；
    # 之后仅当 REGISTRATION_ENABLED=true 才开放自助注册，否则由 admin 创建账号。
    if not is_first_user and not get_settings().REGISTRATION_ENABLED:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="注册已关闭，请联系管理员创建账号"
        )

    # 创建新用户
    pc_identifier = get_pc_identifier(request)
    new_user = User(
        username=user_data.username,
        password_hash=get_password_hash(user_data.password),
        role="admin" if is_first_user else "user",
        status="active",
        pc_identifier=pc_identifier
    )

    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)

    return ResponseModel(
        code=200,
        message="注册成功",
        data={
            "user_id": new_user.id,
            "username": new_user.username,
            "role": new_user.role
        }
    )


@router.post("/login", response_model=ResponseModel)
async def login(
    login_data: UserLogin,
    request: Request,
    db: AsyncSession = Depends(get_db)
):
    """用户登录"""
    user = await authenticate_user(db, login_data.username, login_data.password)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="用户名或密码错误"
        )
    
    # 更新登录信息
    pc_identifier = get_pc_identifier(request)
    await update_last_login(db, user, pc_identifier)
    
    # 创建Token
    access_token, expire = create_access_token(data={"sub": user.username})
    
    return ResponseModel(
        code=200,
        message="登录成功",
        data=Token(
            access_token=access_token,
            expires_in=3600 * 24,  # 24小时
            user=UserResponse.model_validate(user)
        )
    )


@router.get("/me", response_model=ResponseModel)
async def get_me(current_user: User = Depends(get_current_user)):
    """获取当前用户信息"""
    return ResponseModel(
        code=200,
        data=UserResponse.model_validate(current_user)
    )


@router.post("/change-password", response_model=ResponseModel)
async def change_password(
    data: PasswordChangeRequest,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """修改当前用户密码"""
    if not verify_password(data.old_password, current_user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="原密码错误"
        )

    current_user.password_hash = get_password_hash(data.new_password)
    await db.commit()
    await db.refresh(current_user)

    return ResponseModel(code=200, message="密码修改成功")
