"""设备管理接口集成测试。"""
import pytest
from httpx import AsyncClient
from sqlalchemy import select

from app.models import Device


@pytest.mark.asyncio
async def test_refresh_devices(
    client: AsyncClient, admin_token: str, mock_adb, admin_user
):
    """TC-DEV-001: 刷新 ADB 设备，mock 返回一台 rk3568。"""
    response = await client.post(
        "/api/v1/devices/refresh",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["found_devices"] == 1
    assert len(data["items"]) == 1
    assert data["items"][0]["serial_number"] == "rk3568-test"


@pytest.mark.asyncio
async def test_list_devices_visibility(
    client: AsyncClient,
    admin_token: str,
    normal_token: str,
    sample_device: Device,
):
    """TC-DEV-002: 普通用户只能看到本机设备。"""
    # admin 能看到全部
    response = await client.get(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    admin_devices = response.json()["data"]["items"]
    assert len(admin_devices) == 1

    # normal 用户 pc_identifier 不同，应看不到
    response = await client.get(
        "/api/v1/devices",
        headers={"Authorization": f"Bearer {normal_token}"},
    )
    assert response.status_code == 200
    normal_devices = response.json()["data"]["items"]
    assert len(normal_devices) == 0


@pytest.mark.asyncio
async def test_get_device_detail(
    client: AsyncClient, admin_token: str, sample_device: Device
):
    """TC-DEV-003: 查看设备详情。"""
    response = await client.get(
        f"/api/v1/devices/{sample_device.serial_number}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["model"] == "rk3568"


@pytest.mark.asyncio
async def test_update_device_status_admin(
    client: AsyncClient, admin_token: str, sample_device: Device
):
    """TC-DEV-004: 管理员更新设备状态。"""
    response = await client.put(
        f"/api/v1/devices/{sample_device.serial_number}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "offline"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_update_device_status_forbidden_for_normal(
    client: AsyncClient, normal_token: str, sample_device: Device
):
    """TC-DEV-005: 普通用户不能更新设备状态。"""
    response = await client.put(
        f"/api/v1/devices/{sample_device.serial_number}/status",
        headers={"Authorization": f"Bearer {normal_token}"},
        json={"status": "offline"},
    )
    assert response.status_code == 403


@pytest.mark.asyncio
async def test_delete_device_admin(
    client: AsyncClient, admin_token: str, sample_device: Device, test_db
):
    """TC-DEV-006: 管理员可删除设备。"""
    response = await client.delete(
        f"/api/v1/devices/{sample_device.serial_number}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200

    result = await test_db.execute(select(Device).where(Device.serial_number == sample_device.serial_number))
    assert result.scalar_one_or_none() is None
