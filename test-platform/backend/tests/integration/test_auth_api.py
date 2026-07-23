"""认证接口集成测试。"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.auth import get_password_hash


@pytest.mark.asyncio
async def test_register_success(client: AsyncClient):
    """TC-AUTH-001: 正常注册用户。"""
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "newuser", "password": "newpass123", "role": "user"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert data["data"]["username"] == "newuser"


@pytest.mark.asyncio
async def test_register_duplicate_username(client: AsyncClient):
    """TC-AUTH-002: 重复用户名注册失败。"""
    await client.post(
        "/api/v1/auth/register",
        json={"username": "dupuser", "password": "newpass123", "role": "user"},
    )
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "dupuser", "password": "newpass123", "role": "user"},
    )
    assert response.status_code == 400
    assert "已存在" in response.json()["detail"]


@pytest.mark.asyncio
async def test_register_weak_password(client: AsyncClient):
    """TC-AUTH-003: 密码过短应被 Pydantic 校验拒绝。"""
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "weakuser", "password": "123", "role": "user"},
    )
    assert response.status_code == 422


@pytest.mark.asyncio
async def test_login_success(client: AsyncClient, admin_user: User):
    """TC-AUTH-004: 正常登录返回 token。"""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["code"] == 200
    assert "access_token" in data["data"]
    assert data["data"]["user"]["username"] == "admin"


@pytest.mark.asyncio
async def test_login_wrong_password(client: AsyncClient, admin_user: User):
    """TC-AUTH-005: 错误密码登录失败。"""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "wrongpass"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_login_disabled_user(client: AsyncClient, test_db: AsyncSession):
    """TC-AUTH-006: 禁用用户无法登录。"""
    user = User(
        username="disabled",
        password_hash=get_password_hash("pass123"),
        role="user",
        status="disabled",
        pc_identifier="test-pc",
    )
    test_db.add(user)
    await test_db.commit()

    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "disabled", "password": "pass123"},
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_get_me(client: AsyncClient, admin_token: str):
    """TC-AUTH-007: 获取当前登录用户信息。"""
    response = await client.get(
        "/api/v1/auth/me",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()
    assert data["data"]["username"] == "admin"
    assert data["data"]["role"] == "admin"


@pytest.mark.asyncio
async def test_get_me_without_token(client: AsyncClient):
    """TC-AUTH-008: 未认证访问受保护接口应 401。"""
    response = await client.get("/api/v1/auth/me")
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_change_password(client: AsyncClient, admin_token: str):
    """TC-AUTH-009: 当前用户修改密码。"""
    response = await client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"old_password": "admin123", "new_password": "newadmin123"},
    )
    assert response.status_code == 200
    assert response.json()["code"] == 200

    # 使用新密码登录
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "newadmin123"},
    )
    assert login_res.status_code == 200


@pytest.mark.asyncio
async def test_change_password_wrong_old(client: AsyncClient, admin_token: str):
    """TC-AUTH-010: 原密码错误应拒绝。"""
    response = await client.post(
        "/api/v1/auth/change-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"old_password": "wrongpass", "new_password": "newpass123"},
    )
    assert response.status_code == 400
