"""设备心跳与离线检测的单元测试。"""
import asyncio
from unittest.mock import AsyncMock

import pytest

import app.main as main_module
from app.models import Device
from app.services.device import ADBService


def make_adb_service(online_serials):
    """构造 get_devices 返回指定在线序列号的 ADBService。"""
    adb = ADBService()
    adb.get_devices = AsyncMock(
        return_value=[{"serial": s, "state": "device"} for s in online_serials]
    )
    return adb


async def add_device(test_db, admin_user, serial, status):
    device = Device(
        serial_number=serial,
        status=status,
        pc_identifier="test-pc-admin",
        owner_id=admin_user.id,
    )
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)
    return device


@pytest.mark.asyncio
async def test_heartbeat_marks_missing_devices_offline(test_db, admin_user):
    """TC-HEARTBEAT-001: adb 列表中消失的设备（含 testing 状态）被置 offline。"""
    device_online = await add_device(test_db, admin_user, "hb-online", "online")
    device_gone = await add_device(test_db, admin_user, "hb-gone", "online")
    device_testing = await add_device(test_db, admin_user, "hb-testing", "testing")

    adb = make_adb_service(["hb-online"])
    changed = await adb.heartbeat_check(test_db)

    assert changed["offline"] == 2
    await test_db.refresh(device_online)
    assert device_online.status == "online"
    await test_db.refresh(device_gone)
    assert device_gone.status == "offline"
    # testing 设备掉线同样置 offline（其运行中任务不由心跳处理）
    await test_db.refresh(device_testing)
    assert device_testing.status == "offline"

    # adb 列表中新出现的设备自动登记为未分配设备
    adb2 = make_adb_service(["hb-online", "hb-brand-new"])
    adb2.get_device_info = AsyncMock(return_value={"serial_number": "hb-brand-new"})
    await adb2.heartbeat_check(test_db)
    from sqlalchemy import select
    result = await test_db.execute(
        select(Device).where(Device.serial_number == "hb-brand-new")
    )
    assert result.scalar_one_or_none() is not None


@pytest.mark.asyncio
async def test_heartbeat_marks_returned_device_online(test_db, admin_user):
    """TC-HEARTBEAT-002: offline 设备重新出现在 adb 列表中被置 online。"""
    device_offline = await add_device(test_db, admin_user, "hb-back", "offline")

    adb = make_adb_service(["hb-back"])
    changed = await adb.heartbeat_check(test_db)

    assert changed["online"] == 1
    await test_db.refresh(device_offline)
    assert device_offline.status == "online"
    assert device_offline.last_seen_at is not None


@pytest.mark.asyncio
async def test_heartbeat_ignores_maintenance_devices(test_db, admin_user):
    """TC-HEARTBEAT-003: maintenance 状态设备不受心跳影响。"""
    device_maint = await add_device(test_db, admin_user, "hb-maint", "maintenance")

    adb = make_adb_service([])  # adb 列表为空也不动 maintenance
    changed = await adb.heartbeat_check(test_db)

    assert changed == {"offline": 0, "online": 0, "registered": 0}
    await test_db.refresh(device_maint)
    assert device_maint.status == "maintenance"


@pytest.mark.asyncio
async def test_heartbeat_registers_new_devices(test_db, admin_user):
    """TC-HEARTBEAT-005: adb 列表中新出现的设备自动登记为未分配在线设备。"""
    await add_device(test_db, admin_user, "hb-known", "online")

    adb = make_adb_service(["hb-known", "hb-new-1"])
    adb.get_device_info = AsyncMock(return_value={
        "serial_number": "hb-new-1",
        "model": "rk3568",
        "brand": "rockchip",
        "android_version": "11",
        "sdk_version": "30",
        "cpu_abi": "arm64-v8a",
        "resolution": "1920x1080",
        "battery_level": 100,
    })
    changed = await adb.heartbeat_check(test_db)

    assert changed["registered"] == 1
    from sqlalchemy import select
    result = await test_db.execute(
        select(Device).where(Device.serial_number == "hb-new-1")
    )
    device = result.scalar_one_or_none()
    assert device is not None
    assert device.status == "online"
    # 未分配设备：pc_identifier 为空，普通用户不可见，等待 admin 分配
    assert device.pc_identifier == ""
    assert device.owner_id is None
    assert device.model == "rk3568"
    assert device.brand == "rockchip"
    assert device.last_seen_at is not None


@pytest.mark.asyncio
async def test_heartbeat_loop_survives_exceptions(test_db, monkeypatch):
    """TC-HEARTBEAT-004: 心跳方法抛异常时后台循环不退出，下个周期继续执行。"""
    calls = []

    async def failing_heartbeat(self, db):
        calls.append(1)
        raise RuntimeError("adb not found")

    monkeypatch.setattr(ADBService, "heartbeat_check", failing_heartbeat)
    monkeypatch.setattr(main_module.settings, "HEARTBEAT_INTERVAL", 0.01)

    task = asyncio.create_task(main_module.device_heartbeat_loop())
    await asyncio.sleep(0.15)
    assert not task.done()
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert len(calls) >= 2
