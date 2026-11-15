"""用户管理接口集成测试。"""
import pytest
from httpx import AsyncClient
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.auth import get_password_hash


@pytest.mark.asyncio
async def test_list_users_admin(client: AsyncClient, admin_token: str, normal_user: User):
    """TC-USER-001: 管理员可查看用户列表。"""
    response = await client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    usernames = [u["username"] for u in data["items"]]
    assert "admin" in usernames
    assert "normal" in usernames


@pytest.mark.asyncio
async def test_list_users_forbidden_for_normal(client: AsyncClient, normal_token: str):
    """TC-USER-002: 普通用户无法查看用户列表。"""
    response = await client.get(
        "/api/v1/users",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_update_user_role(client: AsyncClient, admin_token: str, normal_user: User):
    """TC-USER-003: 管理员可修改用户角色。"""
    response = await client.put(
        f"/api/v1/users/{normal_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"role": "admin"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["role"] == "admin"


@pytest.mark.asyncio
async def test_disable_user(client: AsyncClient, admin_token: str, test_db: AsyncSession):
    """TC-USER-004: 管理员可禁用用户（不能禁用自己）。"""
    user = User(
        username="tobedisabled",
        password_hash=get_password_hash("pass123"),
        role="user",
        status="active",
        pc_identifier="test-pc",
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)

    response = await client.delete(
        f"/api/v1/users/{user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200

    # 验证已禁用（跨会话修改后需要刷新才能看到最新状态）
    result = await test_db.get(User, user.id)
    await test_db.refresh(result)
    assert result.status == "disabled"


@pytest.mark.asyncio
async def test_disable_self_forbidden(client: AsyncClient, admin_token: str, admin_user: User):
    """TC-USER-005: 管理员不能禁用自己。"""
    response = await client.delete(
        f"/api/v1/users/{admin_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400


@pytest.mark.asyncio
async def test_reset_password(client: AsyncClient, admin_token: str, normal_user: User):
    """TC-USER-006: 管理员可重置用户密码（T-16 安全修复：密码走请求体不走 URL query）。"""
    response = await client.post(
        f"/api/v1/users/{normal_user.id}/reset-password",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"new_password": "newpass123"},
    )
    assert response.status_code == 200

    # 使用新密码登录
    login_res = await client.post(
        "/api/v1/auth/login",
        json={"username": "normal", "password": "newpass123"},
    )
    assert login_res.status_code == 200


@pytest.mark.asyncio
async def test_get_user_detail_admin(client: AsyncClient, admin_token: str, normal_user: User):
    """TC-USER-007: 管理员可查看指定用户详情。"""
    response = await client.get(
        f"/api/v1/users/{normal_user.id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["username"] == "normal"
