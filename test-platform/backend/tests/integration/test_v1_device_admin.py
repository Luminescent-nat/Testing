"""V1-01 补全：设备发现（/device-discoveries）与管理员改派（PATCH /devices/{serial}）真值表。

契约：docs/contracts/device-authorization-v1.0.md §5（发现）/§6（改派）/§4（详情 403 details）。
覆盖：
- 发现成功 201 + items/total/owner_unchanged=true；发现不改既有 owner/PC/version；
  普通用户新设备 owner=null；ADB 失败 503 且不批量误离线、不动 testing；
- legacy POST /devices/refresh 委托同一服务；
- PATCH：管理员成功（version 递增）、version 冲突 409、完全重放幂等（旧 version 仍返回当前）、
  普通用户 403、disabled 403、404、pc 空白 400、未知字段 400、目标用户未激活 400；
- GET 详情 403 details.field=serial。
"""
from unittest.mock import AsyncMock

import pytest

import app.api.devices as devices_api
from app.models import Device, User
from app.services.auth import create_access_token, get_password_hash


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@pytest.fixture(autouse=True)
def _restore_profile_build():
    """恢复被本模块临时替换的 profile_service.build_profile，避免跨用例泄漏。"""
    service = devices_api.device_service.profile_service
    original = service.build_profile
    try:
        yield
    finally:
        service.build_profile = original


def _device(serial, owner_id=None, pc="", status_="online", version=None):
    kwargs = dict(
        serial_number=serial,
        model="A133P",
        brand="allwinner",
        android_version="10",
        sdk_version="29",
        cpu_abi="armeabi-v7a",
        status=status_,
        owner_id=owner_id,
        pc_identifier=pc,
    )
    if version is not None:
        kwargs["version"] = version
    return Device(**kwargs)


def _patch_discovery(mock_adb, devices_meta, error=None):
    mock_adb.get_device_list = AsyncMock(return_value=(devices_meta, error))
    mock_adb.get_device_info = AsyncMock(
        return_value={
            "serial_number": devices_meta[0]["serial"] if devices_meta else "x",
            "model": "A133P", "brand": "allwinner", "android_version": "10",
            "sdk_version": "29", "cpu_abi": "armeabi-v7a",
            "resolution": None, "battery_level": None,
        }
    )
    devices_api.device_service.profile_service.build_profile = AsyncMock(return_value={})


# ---------------------------------------------------------------- 发现成功
@pytest.mark.asyncio
async def test_discovery_success_201_owner_unchanged(client, admin_token, mock_adb, test_db):
    _patch_discovery(mock_adb, [{"serial": "DISC-NEW", "state": "device"}])
    resp = await client.post("/api/v1/device-discoveries", headers=_auth(admin_token), json={})
    assert resp.status_code == 201, resp.text
    body = resp.json()
    assert body["code"] == 201
    assert body["data"]["owner_unchanged"] is True
    assert body["data"]["total"] == 1
    assert body["data"]["items"][0]["serial_number"] == "DISC-NEW"

    dev = await devices_api.device_service.get_device_by_serial(test_db, "DISC-NEW")
    assert dev is not None
    assert dev.owner_id is None          # 新设备待管理员分配
    assert dev.pc_identifier == ""
    assert dev.version == 1


@pytest.mark.asyncio
async def test_discovery_does_not_change_existing_owner_pc_version(
    client, admin_token, normal_user, mock_adb, test_db
):
    dev = _device("DISC-EXIST", owner_id=normal_user.id, pc="pc-x", version=3)
    test_db.add(dev)
    await test_db.commit()
    _patch_discovery(mock_adb, [{"serial": "DISC-EXIST", "state": "device"}])

    resp = await client.post("/api/v1/device-discoveries", headers=_auth(admin_token), json={})
    assert resp.status_code == 201, resp.text
    await test_db.refresh(dev)
    assert dev.owner_id == normal_user.id
    assert dev.pc_identifier == "pc-x"
    assert dev.version == 3


@pytest.mark.asyncio
async def test_normal_user_discovery_new_device_owner_null(client, normal_token, mock_adb, test_db):
    _patch_discovery(mock_adb, [{"serial": "DISC-BY-USER", "state": "device"}])
    resp = await client.post("/api/v1/device-discoveries", headers=_auth(normal_token), json={})
    assert resp.status_code == 201, resp.text
    dev = await devices_api.device_service.get_device_by_serial(test_db, "DISC-BY-USER")
    assert dev is not None
    assert dev.owner_id is None  # 普通用户不认领
    assert dev.pc_identifier == ""


# ---------------------------------------------------------------- 发现失败 503 不批量误离线
@pytest.mark.asyncio
async def test_discovery_adb_failure_503_does_not_offline_or_touch_testing(
    client, admin_token, mock_adb, test_db
):
    testing = _device("DISC-TESTING", status_="testing")
    online = _device("DISC-ONLINE", status_="online")
    test_db.add_all([testing, online])
    await test_db.commit()
    _patch_discovery(mock_adb, [], error="adb devices 返回码 1（error）")

    resp = await client.post("/api/v1/device-discoveries", headers=_auth(admin_token), json={})
    assert resp.status_code == 503, resp.text
    assert resp.json()["code"] == "SERVICE_UNAVAILABLE"

    await test_db.refresh(testing)
    await test_db.refresh(online)
    assert testing.status == "testing"   # 不动 testing
    assert online.status == "online"     # 不批量误离线


@pytest.mark.asyncio
async def test_discovery_empty_valid_scan_does_not_batch_offline(
    client, admin_token, mock_adb, test_db
):
    online = _device("DISC-EMPTY-SCAN", status_="online")
    test_db.add(online)
    await test_db.commit()
    _patch_discovery(mock_adb, [], error=None)  # 有效空扫描

    resp = await client.post("/api/v1/device-discoveries", headers=_auth(admin_token), json={})
    assert resp.status_code == 201, resp.text
    assert resp.json()["data"] == {"items": [], "total": 0, "owner_unchanged": True}
    await test_db.refresh(online)
    assert online.status == "online"  # 不批量误离线


# ---------------------------------------------------------------- legacy refresh 委托
@pytest.mark.asyncio
async def test_legacy_refresh_delegates_same_service(client, admin_token, mock_adb, test_db):
    _patch_discovery(mock_adb, [{"serial": "REFRESH-1", "state": "device"}])
    resp = await client.post("/api/v1/devices/refresh", headers=_auth(admin_token))
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["found_devices"] == 1
    assert data["owner_unchanged"] is True
    assert data["items"][0]["serial_number"] == "REFRESH-1"

    _patch_discovery(mock_adb, [], error="adb devices 返回码 1（error）")
    resp = await client.post("/api/v1/devices/refresh", headers=_auth(admin_token))
    assert resp.status_code == 503
    assert resp.json()["code"] == "SERVICE_UNAVAILABLE"


# ---------------------------------------------------------------- PATCH 改派
@pytest.mark.asyncio
async def test_patch_admin_assign_success_version_increments(
    client, admin_token, normal_user, test_db
):
    dev = _device("PATCH-OK", owner_id=None, pc="", version=1)
    test_db.add(dev)
    await test_db.commit()
    resp = await client.patch(
        "/api/v1/devices/PATCH-OK",
        headers=_auth(admin_token),
        json={"owner_id": normal_user.id, "pc_identifier": " pc-a ", "version": 1},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()["data"]
    assert data["owner_id"] == normal_user.id
    assert data["pc_identifier"] == "pc-a"   # 首尾空白被去除
    assert data["version"] == 2
    await test_db.refresh(dev)
    assert dev.version == 2 and dev.owner_id == normal_user.id


@pytest.mark.asyncio
async def test_patch_version_conflict_409(client, admin_token, normal_user, admin_user, test_db):
    dev = _device("PATCH-CONFLICT", owner_id=admin_user.id, pc="pc-old", version=2)
    test_db.add(dev)
    await test_db.commit()
    resp = await client.patch(
        "/api/v1/devices/PATCH-CONFLICT",
        headers=_auth(admin_token),
        json={"owner_id": normal_user.id, "pc_identifier": "pc-new", "version": 1},
    )
    assert resp.status_code == 409, resp.text
    body = resp.json()
    assert body["code"] == "CONFLICT"
    assert body["details"]["field"] == "version"
    await test_db.refresh(dev)
    assert dev.version == 2 and dev.owner_id == admin_user.id  # 未变


@pytest.mark.asyncio
async def test_patch_full_replay_idempotent_even_stale_version(
    client, admin_token, normal_user, test_db
):
    dev = _device("PATCH-REPLAY", owner_id=normal_user.id, pc="pc-a", version=5)
    test_db.add(dev)
    await test_db.commit()
    resp = await client.patch(
        "/api/v1/devices/PATCH-REPLAY",
        headers=_auth(admin_token),
        json={"owner_id": normal_user.id, "pc_identifier": "pc-a", "version": 1},
    )
    assert resp.status_code == 200, resp.text
    assert resp.json()["data"]["version"] == 5  # 完全重放：不改、返回当前
    await test_db.refresh(dev)
    assert dev.version == 5


@pytest.mark.asyncio
async def test_patch_normal_user_forbidden(client, normal_token, normal_user, test_db):
    dev = _device("PATCH-BY-USER", owner_id=normal_user.id, pc=normal_user.pc_identifier, version=1)
    test_db.add(dev)
    await test_db.commit()
    resp = await client.patch(
        "/api/v1/devices/PATCH-BY-USER",
        headers=_auth(normal_token),
        json={"owner_id": normal_user.id, "pc_identifier": "pc-a", "version": 1},
    )
    assert resp.status_code == 403, resp.text
    assert resp.json()["code"] == "FORBIDDEN"
    await test_db.refresh(dev)
    assert dev.version == 1  # 零写入


@pytest.mark.asyncio
async def test_patch_disabled_user_forbidden(client, test_db):
    user = User(
        username="patch-disabled",
        password_hash=get_password_hash("x-pass-123"),
        role="admin",
        status="disabled",
        pc_identifier="pc-disabled",
    )
    test_db.add(user)
    dev = _device("PATCH-DISABLED", owner_id=None, pc="", version=1)
    test_db.add(dev)
    await test_db.commit()
    token, _ = create_access_token(data={"sub": user.username})
    resp = await client.patch(
        "/api/v1/devices/PATCH-DISABLED",
        headers=_auth(token),
        json={"owner_id": None, "pc_identifier": "pc-a", "version": 1},
    )
    assert resp.status_code == 403, resp.text


@pytest.mark.asyncio
async def test_patch_validation_and_not_found(client, admin_token, test_db):
    dev = _device("PATCH-VALID", owner_id=None, pc="", version=1)
    test_db.add(dev)
    await test_db.commit()

    # 设备不存在 404
    r = await client.patch(
        "/api/v1/devices/NOPE",
        headers=_auth(admin_token),
        json={"owner_id": None, "pc_identifier": "pc-a", "version": 1},
    )
    assert r.status_code == 404
    # 目标用户不存在 404
    r = await client.patch(
        "/api/v1/devices/PATCH-VALID",
        headers=_auth(admin_token),
        json={"owner_id": 999999, "pc_identifier": "pc-a", "version": 1},
    )
    assert r.status_code == 404
    assert r.json()["details"]["field"] == "owner_id"
    # pc 空白 400
    r = await client.patch(
        "/api/v1/devices/PATCH-VALID",
        headers=_auth(admin_token),
        json={"owner_id": None, "pc_identifier": "   ", "version": 1},
    )
    assert r.status_code == 400
    assert r.json()["details"]["field"] == "pc_identifier"
    # 未知字段 400 VALIDATION_ERROR
    r = await client.patch(
        "/api/v1/devices/PATCH-VALID",
        headers=_auth(admin_token),
        json={"owner_id": None, "pc_identifier": "pc-a", "version": 1, "bogus": 1},
    )
    assert r.status_code == 400
    assert r.json()["code"] == "VALIDATION_ERROR"
    # 缺少 version 400
    r = await client.patch(
        "/api/v1/devices/PATCH-VALID",
        headers=_auth(admin_token),
        json={"owner_id": None, "pc_identifier": "pc-a"},
    )
    assert r.status_code == 400


@pytest.mark.asyncio
async def test_patch_target_user_inactive_400(client, admin_token, test_db):
    inactive = User(
        username="patch-target-disabled",
        password_hash=get_password_hash("x-pass-123"),
        role="user",
        status="disabled",
        pc_identifier="pc-t",
    )
    dev = _device("PATCH-INACTIVE-TARGET", owner_id=None, pc="", version=1)
    test_db.add_all([inactive, dev])
    await test_db.commit()
    await test_db.refresh(inactive)
    r = await client.patch(
        "/api/v1/devices/PATCH-INACTIVE-TARGET",
        headers=_auth(admin_token),
        json={"owner_id": inactive.id, "pc_identifier": "pc-a", "version": 1},
    )
    assert r.status_code == 400, r.text
    assert r.json()["details"]["field"] == "owner_id"


# ---------------------------------------------------------------- GET 详情 403 details.field=serial
@pytest.mark.asyncio
async def test_get_device_forbidden_details_field_serial(
    client, normal_token, admin_user, test_db
):
    dev = _device("DETAIL-FORBIDDEN", owner_id=admin_user.id, pc="other-pc", version=1)
    test_db.add(dev)
    await test_db.commit()
    resp = await client.get("/api/v1/devices/DETAIL-FORBIDDEN", headers=_auth(normal_token))
    assert resp.status_code == 403, resp.text
    body = resp.json()
    assert body["code"] == "FORBIDDEN"
    assert body["details"]["field"] == "serial"
