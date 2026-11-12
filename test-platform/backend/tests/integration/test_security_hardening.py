"""第二批安全加固集成测试：注册开关、命令注入防护、客户端设备标识、仪表盘统计。"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Device, TestItem, User


@pytest.mark.asyncio
async def test_first_user_registration_always_allowed(client: AsyncClient):
    """首个用户始终可注册并自动成为 admin（保证全新部署可初始化）。"""
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "first", "password": "first123", "email": "first@test.com"},
    )
    assert response.status_code == 200, response.text
    assert response.json()["data"]["role"] == "admin"


@pytest.mark.asyncio
async def test_registration_forbidden_when_disabled(client: AsyncClient, admin_user: User):
    """已有用户且 REGISTRATION_ENABLED=false（默认）时，自助注册被拒绝。"""
    response = await client.post(
        "/api/v1/auth/register",
        json={"username": "second", "password": "second123", "email": "second@test.com"},
    )
    assert response.status_code == 403
    err = response.json()
    assert err["code"] == "FORBIDDEN"
    assert "注册已关闭" in err["message"]


@pytest.mark.asyncio
async def test_login_binds_pc_identifier_from_header(
    client: AsyncClient, admin_user: User, test_db: AsyncSession
):
    """登录时通过 X-PC-Identifier 请求头绑定客户端标识，不再使用服务器标识。"""
    response = await client.post(
        "/api/v1/auth/login",
        json={"username": "admin", "password": "admin123"},
        headers={"X-PC-Identifier": "uuid-client-abc"},
    )
    assert response.status_code == 200, response.text
    result = await test_db.execute(select(User).where(User.username == "admin"))
    user = result.scalar_one()
    await test_db.refresh(user)  # 绕过 identity map 缓存，读取登录请求提交的最新值
    assert user.pc_identifier == "uuid-client-abc"


@pytest.mark.asyncio
async def test_custom_parameter_injection_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem
):
    """任务自定义参数含 shell 元字符时被 400 拒绝（防命令注入）。"""
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "item_ids": [sample_item.id],
            "custom_parameters": {"target": "8.8.8.8; rm -rf /"},
        },
    )
    assert response.status_code == 400
    err = response.json()
    assert err["code"] == "VALIDATION_ERROR"
    assert "非法字符" in err["message"]


@pytest.mark.asyncio
async def test_custom_parameter_legit_accepted(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem
):
    """合法参数值（字母数字、路径、URL 字符）正常通过校验。"""
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "item_ids": [sample_item.id],
            "custom_parameters": {"target": "https://example.com/a-b_c.zip"},
        },
    )
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_dashboard_stats_response_shape(
    client: AsyncClient, admin_token: str, sample_device: Device
):
    """仪表盘统计接口返回真实聚合口径的字段结构。"""
    response = await client.get(
        "/api/v1/dashboard/stats",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200, response.text
    data = response.json()["data"]
    assert set(data["today"].keys()) == {"tasks", "passed", "failed", "pass_rate"}
    assert data["today"]["tasks"] == 0
    assert data["today"]["pass_rate"] is None  # 无完成任务时为 None 而非假数字
    assert data["devices"]["total"] == 1
    assert data["devices"]["online"] == 1
    assert "running_tasks" in data
