"""T-16 账号闭环（R28）集成测试：user-administration-v1.0.md §2/§4/§6。

覆盖：
- POST /auth/registrations 首管理员初始化（201/403/400，拒绝 role/status 自助提权）；
- POST /users 管理员建号（201/403/400/409，唯一约束，10 次同名至多一行）；
- PATCH /users/{id} 角色/状态局部更新（200/400/404/409，最后 active 管理员保护，幂等）；
- POST /users/{id}/reset-password 走请求体（不再走 URL query，防进访问日志）。
"""
import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import User
from app.services.auth import create_access_token


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


# ========== §2 首管理员注册 ==========

@pytest.mark.asyncio
async def test_first_admin_registration_created(client: AsyncClient):
    """空库注册首个用户：201、强制 role=admin、message=首管理员创建成功。"""
    response = await client.post(
        "/api/v1/auth/registrations",
        json={"username": "first-admin", "password": "change-me-now", "pc_identifier": "pc-admin"},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == 201
    assert body["message"] == "首管理员创建成功"
    data = body["data"]
    assert data["role"] == "admin"
    assert data["status"] == "active"
    assert data["username"] == "first-admin"
    assert "password" not in data


@pytest.mark.asyncio
async def test_registration_forbidden_after_initialized(client: AsyncClient, admin_user: User):
    """已有用户后注册返回 403 系统已完成初始化（不接受任何后续自助注册）。"""
    response = await client.post(
        "/api/v1/auth/registrations",
        json={"username": "second", "password": "second123", "pc_identifier": "pc-b"},
    )
    assert response.status_code == 403
    assert response.json()["message"] == "系统已完成初始化"


@pytest.mark.asyncio
async def test_registration_rejects_role_field(client: AsyncClient):
    """请求携带 role/status 字段一律 400（防止自助提权）。"""
    response = await client.post(
        "/api/v1/auth/registrations",
        json={
            "username": "evil", "password": "evil123", "pc_identifier": "pc-c",
            "role": "user",
        },
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_first_admin_concurrent_registration_once(
    client: AsyncClient, test_db: AsyncSession
):
    """并发初始化只成功一次：后续请求 403，库中恰好一行 admin。"""
    async def register():
        return await client.post(
            "/api/v1/auth/registrations",
            json={"username": "race-admin", "password": "race123", "pc_identifier": "pc-race"},
        )

    results = await asyncio.gather(*[register() for _ in range(5)])
    codes = sorted(r.status_code for r in results)
    # 单 worker 顺序执行下表现为首个 201 + 其余 403；唯一约束兜底不产生 500
    assert codes[0] == 201
    assert all(c in (201, 403, 409) for c in codes)
    count = await test_db.scalar(
        select(func.count()).select_from(User).where(User.username == "race-admin")
    )
    assert count == 1


# ========== §4 管理员建号 ==========

@pytest.mark.asyncio
async def test_admin_creates_user(client: AsyncClient, admin_token: str, test_db: AsyncSession):
    """管理员创建后续账号：201，落库字段与请求一致，密码不回显。"""
    response = await client.post(
        "/api/v1/users",
        headers=_auth(admin_token),
        json={
            "username": "operator", "password": "user-pass",
            "role": "user", "status": "active", "pc_identifier": "pc-a",
        },
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["code"] == 201
    assert body["message"] == "用户创建成功"
    data = body["data"]
    assert data["role"] == "user"
    assert data["status"] == "active"
    assert data["pc_identifier"] == "pc-a"
    assert "password" not in data

    # 按 ID 读出相同字段（契约 GWT）
    user_id = data["id"]
    user = await test_db.get(User, user_id)
    assert user is not None
    assert user.role == "user"
    assert user.status == "active"
    assert user.pc_identifier == "pc-a"


@pytest.mark.asyncio
async def test_non_admin_cannot_create_user(client: AsyncClient, normal_token: str):
    response = await client.post(
        "/api/v1/users",
        headers=_auth(normal_token),
        json={"username": "hacker", "password": "hacker1", "pc_identifier": "pc-x"},
    )
    assert response.status_code == 403
    assert response.json()["message"] == "需要管理员权限"


@pytest.mark.asyncio
async def test_disabled_admin_cannot_create_user(
    client: AsyncClient, test_db: AsyncSession, admin_user: User
):
    """disabled 管理员创建账号返回 403（禁用状态先于权限检查）。"""
    admin_user.status = "disabled"
    await test_db.commit()
    token = create_access_token(data={"sub": admin_user.username})[0]
    response = await client.post(
        "/api/v1/users",
        headers=_auth(token),
        json={"username": "late", "password": "late123", "pc_identifier": "pc-y"},
    )
    assert response.status_code == 403
    assert response.json()["message"] == "用户已被禁用"


@pytest.mark.asyncio
async def test_create_user_duplicate_username(
    client: AsyncClient, admin_token: str, test_db: AsyncSession
):
    """重名创建返回 409；连续 10 次同名至多创建一行。"""
    payload = {
        "username": "dup-user", "password": "user-pass",
        "role": "user", "status": "active", "pc_identifier": "pc-d",
    }
    first = await client.post("/api/v1/users", headers=_auth(admin_token), json=payload)
    assert first.status_code == 201

    results = []
    for _ in range(9):
        r = await client.post("/api/v1/users", headers=_auth(admin_token), json=payload)
        results.append(r.status_code)
    assert all(c == 409 for c in results), results

    count = await test_db.scalar(
        select(func.count()).select_from(User).where(User.username == "dup-user")
    )
    assert count == 1


@pytest.mark.asyncio
async def test_create_user_invalid_fields(client: AsyncClient, admin_token: str):
    """字段非法（用户名过短/密码过短/pc_identifier 缺失）返回 400。"""
    for bad in (
        {"username": "ab", "password": "user-pass", "pc_identifier": "pc-a"},
        {"username": "operator", "password": "123", "pc_identifier": "pc-a"},
        {"username": "operator", "password": "user-pass"},
    ):
        response = await client.post("/api/v1/users", headers=_auth(admin_token), json=bad)
        assert response.status_code == 400, bad
        assert response.json()["code"] == "VALIDATION_ERROR"


# ========== §6 PATCH 用户 ==========

@pytest.mark.asyncio
async def test_patch_user_role_status(
    client: AsyncClient, admin_token: str, test_db: AsyncSession
):
    """PATCH 局部更新 role/status：200 并返回更新后的用户。"""
    created = await client.post(
        "/api/v1/users",
        headers=_auth(admin_token),
        json={"username": "patchable", "password": "user-pass", "pc_identifier": "pc-p"},
    )
    user_id = created.json()["data"]["id"]

    response = await client.patch(
        f"/api/v1/users/{user_id}",
        headers=_auth(admin_token),
        json={"role": "admin"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert data["role"] == "admin"
    assert data["status"] == "active"

    user = await test_db.get(User, user_id)
    assert user.role == "admin"


@pytest.mark.asyncio
async def test_patch_empty_or_unknown_fields(client: AsyncClient, admin_token: str, normal_user: User):
    """空对象或含未知字段的 PATCH 返回 400。"""
    for bad in ({}, {"role": "admin", "email": "a@b.com"}):
        response = await client.patch(
            f"/api/v1/users/{normal_user.id}",
            headers=_auth(admin_token),
            json=bad,
        )
        assert response.status_code == 400, bad
        assert response.json()["code"] == "VALIDATION_ERROR"


@pytest.mark.asyncio
async def test_patch_last_active_admin_forbidden(
    client: AsyncClient, admin_token: str, admin_user: User
):
    """禁用或降级最后一个 active 管理员返回 409，库中状态不变。"""
    for patch in ({"status": "disabled"}, {"role": "user"}):
        response = await client.patch(
            f"/api/v1/users/{admin_user.id}",
            headers=_auth(admin_token),
            json=patch,
        )
        assert response.status_code == 409, patch
        assert "最后一个" in response.json()["message"]


@pytest.mark.asyncio
async def test_patch_non_last_admin_allowed(
    client: AsyncClient, admin_token: str, test_db: AsyncSession, admin_user: User
):
    """存在第二个 active 管理员时，禁用其中一个返回 200。"""
    created = await client.post(
        "/api/v1/users",
        headers=_auth(admin_token),
        json={
            "username": "admin2", "password": "admin222",
            "role": "admin", "status": "active", "pc_identifier": "pc-2",
        },
    )
    second_id = created.json()["data"]["id"]

    response = await client.patch(
        f"/api/v1/users/{second_id}",
        headers=_auth(admin_token),
        json={"status": "disabled"},
    )
    assert response.status_code == 200, response.text

    # 原管理员仍可操作（未被误伤）
    me = await client.get("/api/v1/auth/me", headers=_auth(admin_token))
    assert me.status_code == 200


@pytest.mark.asyncio
async def test_patch_idempotent_same_value(
    client: AsyncClient, admin_token: str, normal_user: User
):
    """重复 PATCH 到相同 role/status 幂等返回 200 与相同值。"""
    for _ in range(2):
        response = await client.patch(
            f"/api/v1/users/{normal_user.id}",
            headers=_auth(admin_token),
            json={"status": "disabled"},
        )
        assert response.status_code == 200, response.text
        assert response.json()["data"]["status"] == "disabled"


@pytest.mark.asyncio
async def test_patch_user_not_found(client: AsyncClient, admin_token: str):
    response = await client.patch(
        "/api/v1/users/99999", headers=_auth(admin_token), json={"role": "user"}
    )
    assert response.status_code == 404


# ========== 重置密码（安全修复：走 Body 不走 URL query） ==========

@pytest.mark.asyncio
async def test_reset_password_via_request_body(
    client: AsyncClient, admin_token: str, normal_user: User
):
    """管理员通过请求体重置密码：200，新密码可登录。"""
    response = await client.post(
        f"/api/v1/users/{normal_user.id}/reset-password",
        headers=_auth(admin_token),
        json={"new_password": "brand-new-pass"},
    )
    assert response.status_code == 200, response.text

    login = await client.post(
        "/api/v1/auth/login",
        json={"username": normal_user.username, "password": "brand-new-pass"},
    )
    assert login.status_code == 200, login.text


@pytest.mark.asyncio
async def test_reset_password_query_param_rejected(
    client: AsyncClient, admin_token: str, normal_user: User
):
    """密码走 URL query 不再被接受（400），防止落入访问日志。"""
    response = await client.post(
        f"/api/v1/users/{normal_user.id}/reset-password?new_password=leak-pass",
        headers=_auth(admin_token),
    )
    assert response.status_code == 400
    assert response.json()["code"] == "VALIDATION_ERROR"
