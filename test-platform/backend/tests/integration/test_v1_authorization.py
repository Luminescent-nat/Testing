"""V1 授权回归：设备统一授权（V1-01）与 WS disabled 校验（V1-07）。

对应任务 T-03（设备授权）、T-04（手动/AI/重跑复用授权）、T-05（报告与 WS 授权）。
核心用例 test_audit_normal_user_cannot_start_task_on_other_users_device 来源于
docs/verification/reviews/evidence/v1-readiness-20261112/targeted-defect-repro.py，
永久保留为回归；实现前该用例失败（200），实现后必须 403 且零任务写入。
"""
import pytest
import pytest_asyncio
from fastapi import status
from fastapi.testclient import TestClient
from sqlalchemy import func, select

from app.main import app
from app.models import Device, TestRecord, TestTask, User
from app.services.auth import create_access_token, get_password_hash
from app.services.task_executor import TaskExecutor


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _make_device(serial, owner_id, pc_identifier, status_="online", model="rk3568"):
    return Device(
        serial_number=serial,
        model=model,
        brand="rockchip",
        android_version="11",
        sdk_version="30",
        cpu_abi="arm64-v8a",
        status=status_,
        owner_id=owner_id,
        pc_identifier=pc_identifier,
        board="rk3568",
        hardware="rk3568-evb",
        features=["wifi"],
    )


async def _task_total(test_db) -> int:
    return await test_db.scalar(select(func.count()).select_from(TestTask))


# ---------------------------------------------------------------- V1-01 核心复现（永久回归）
@pytest.mark.asyncio
async def test_audit_normal_user_cannot_start_task_on_other_users_device(
    client, normal_token, admin_user, sample_device, sample_item, test_db, monkeypatch
):
    """普通用户使用他人且异 PC 设备创建任务必须为 403，且不得写任务。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    response = await client.post(
        "/api/v1/tasks",
        headers=_auth(normal_token),
        json={
            "device_serial": sample_device.serial_number,
            "item_ids": [sample_item.id],
            "schedule_type": "immediate",
        },
    )
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"
    tasks = (await client.get("/api/v1/tasks", headers=_auth(normal_token))).json()
    assert tasks["data"]["total"] == 0
    # 服务端零任务写入（不仅普通用户列表不可见）
    assert await _task_total(test_db) == 0


# ---------------------------------------------------------------- T-04 手动创建授权真值表
@pytest.mark.asyncio
async def test_admin_can_create_task_on_any_device(
    client, admin_token, normal_user, sample_item, test_db, monkeypatch
):
    """管理员可在任意归属设备（含他人设备）创建任务。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    device = _make_device("admin-any-dev", normal_user.id, "someone-else-pc")
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)

    response = await client.post(
        "/api/v1/tasks",
        headers=_auth(admin_token),
        json={"device_serial": device.serial_number, "item_ids": [sample_item.id]},
    )
    assert response.status_code == 201, response.text


@pytest.mark.asyncio
async def test_normal_user_can_create_task_on_own_device_matching_pc(
    client, normal_token, normal_user, sample_item, test_db, monkeypatch
):
    """普通用户可在 owner=本人且 PC 一致的设备创建任务。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    device = _make_device("normal-own-dev", normal_user.id, normal_user.pc_identifier)
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)

    response = await client.post(
        "/api/v1/tasks",
        headers=_auth(normal_token),
        json={"device_serial": device.serial_number, "item_ids": [sample_item.id]},
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_normal_user_cannot_create_task_on_other_owner_same_pc(
    client, normal_token, admin_user, normal_user, sample_item, test_db
):
    """他人设备即使 PC 一致也 403（PC 不是授权凭证）。"""
    device = _make_device("other-owner-same-pc", admin_user.id, normal_user.pc_identifier)
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)

    response = await client.post(
        "/api/v1/tasks",
        headers=_auth(normal_token),
        json={"device_serial": device.serial_number, "item_ids": [sample_item.id]},
    )
    assert response.status_code == 403, response.text
    assert response.json()["message"] == "无权限使用此设备创建任务"
    assert await _task_total(test_db) == 0


@pytest.mark.asyncio
async def test_normal_user_cannot_create_task_on_own_device_mismatched_pc(
    client, normal_token, normal_user, sample_item, test_db
):
    """本人设备但 PC 分组不一致 403。"""
    device = _make_device("own-dev-other-pc", normal_user.id, "another-pc")
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)

    response = await client.post(
        "/api/v1/tasks",
        headers=_auth(normal_token),
        json={"device_serial": device.serial_number, "item_ids": [sample_item.id]},
    )
    assert response.status_code == 403, response.text
    assert await _task_total(test_db) == 0


@pytest.mark.asyncio
async def test_normal_user_cannot_create_task_on_null_owner_device(
    client, normal_token, normal_user, sample_item, test_db
):
    """owner=null（待分配）设备普通用户 403；管理员可创建。"""
    device = _make_device("null-owner-dev", None, normal_user.pc_identifier)
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)

    response = await client.post(
        "/api/v1/tasks",
        headers=_auth(normal_token),
        json={"device_serial": device.serial_number, "item_ids": [sample_item.id]},
    )
    assert response.status_code == 403, response.text
    assert await _task_total(test_db) == 0


# ---------------------------------------------------------------- T-04 AI 自然语言创建复用授权
@pytest.mark.asyncio
async def test_ai_create_rejects_other_users_device(
    client, normal_token, admin_user, normal_user, test_db, mock_adb
):
    """AI 自然语言创建同样复用设备授权：他人设备 403 且零任务写入。"""
    device = _make_device("ai-other-owner", admin_user.id, normal_user.pc_identifier)
    test_db.add(device)
    await test_db.commit()

    response = await client.post(
        "/api/v1/ai/tasks/natural",
        headers=_auth(normal_token),
        json={"text": "对 rk3568 设备做 DDR 功能测试"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"
    assert await _task_total(test_db) == 0


# ---------------------------------------------------------------- T-04 失败重跑复用授权
@pytest.mark.asyncio
async def test_rerun_rejects_device_no_longer_authorized(
    client, normal_token, admin_user, normal_user, sample_item, test_db
):
    """重跑：源任务属本人但设备已归属他人 → 403 且不新建任务。"""
    device = _make_device("rerun-owner-changed", admin_user.id, admin_user.pc_identifier)
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)
    task = TestTask(
        user_id=normal_user.id,
        device_id=device.id,
        name="rerun-src",
        selected_items=[sample_item.id],
        status="completed",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(task)
    test_db.add(TestRecord(task_id=task.id, item_id=sample_item.id, status="fail", fail_reason="x"))
    await test_db.commit()
    before = await _task_total(test_db)

    response = await client.post(
        f"/api/v1/tasks/{task.id}/rerun-failed", headers=_auth(normal_token)
    )
    assert response.status_code == 403, response.text
    assert await _task_total(test_db) == before


@pytest.mark.asyncio
async def test_rerun_allowed_on_own_authorized_device(
    client, normal_token, normal_user, sample_item, test_db, monkeypatch
):
    """重跑：本人任务且设备 owner=本人/PC 一致 → 200 创建重跑任务。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    device = _make_device("rerun-own-dev", normal_user.id, normal_user.pc_identifier)
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)
    task = TestTask(
        user_id=normal_user.id,
        device_id=device.id,
        name="rerun-src-ok",
        selected_items=[sample_item.id],
        status="completed",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(task)
    test_db.add(TestRecord(task_id=task.id, item_id=sample_item.id, status="fail", fail_reason="x"))
    await test_db.commit()

    response = await client.post(
        f"/api/v1/tasks/{task.id}/rerun-failed", headers=_auth(normal_token)
    )
    assert response.status_code == 201, response.text
    assert response.json()["data"]["name"] == "rerun-src-ok（重跑）"


# ---------------------------------------------------------------- T-03 设备列表/详情授权
@pytest.mark.asyncio
async def test_device_list_filters_by_owner_and_pc(
    client, admin_token, normal_token, admin_user, normal_user, test_db
):
    """普通用户列表仅返回 owner=本人且 PC 一致的设备；管理员可见全部。"""
    own = _make_device("list-own", normal_user.id, normal_user.pc_identifier)
    other = _make_device("list-other", admin_user.id, admin_user.pc_identifier)
    test_db.add_all([own, other])
    await test_db.commit()

    normal_res = await client.get("/api/v1/devices", headers=_auth(normal_token))
    assert normal_res.status_code == 200
    normal_serials = {d["serial_number"] for d in normal_res.json()["data"]["items"]}
    assert normal_serials == {"list-own"}

    admin_res = await client.get("/api/v1/devices", headers=_auth(admin_token))
    admin_serials = {d["serial_number"] for d in admin_res.json()["data"]["items"]}
    assert {"list-own", "list-other"}.issubset(admin_serials)


@pytest.mark.asyncio
async def test_device_detail_authorization(
    client, admin_token, normal_token, admin_user, normal_user, test_db
):
    """详情：本人设备 200；他人设备 403；owner=null 普通用户 403、管理员 200。"""
    own = _make_device("detail-own", normal_user.id, normal_user.pc_identifier)
    other = _make_device("detail-other", admin_user.id, admin_user.pc_identifier)
    null_owner = _make_device("detail-null", None, normal_user.pc_identifier)
    test_db.add_all([own, other, null_owner])
    await test_db.commit()

    assert (await client.get("/api/v1/devices/detail-own", headers=_auth(normal_token))).status_code == 200
    resp_other = await client.get("/api/v1/devices/detail-other", headers=_auth(normal_token))
    assert resp_other.status_code == 403
    assert resp_other.json()["message"] == "无权限访问此设备"
    assert (await client.get("/api/v1/devices/detail-null", headers=_auth(normal_token))).status_code == 403
    assert (await client.get("/api/v1/devices/detail-null", headers=_auth(admin_token))).status_code == 200


# ---------------------------------------------------------------- T-05 报告读取/导出/批量授权
@pytest.fixture
def completed_task_admin(test_db, admin_user, sample_device):
    task = TestTask(
        user_id=admin_user.id,
        device_id=sample_device.id,
        name="admin-report-task",
        selected_items=[],
        status="completed",
    )
    test_db.add(task)
    return task


@pytest.mark.asyncio
async def test_report_read_forbidden_for_other_user(
    client, normal_token, test_db, completed_task_admin
):
    """普通用户读取他人报告 403（不可绕过）。"""
    await test_db.commit()
    await test_db.refresh(completed_task_admin)
    response = await client.get(
        f"/api/v1/reports/{completed_task_admin.id}", headers=_auth(normal_token)
    )
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"


@pytest.mark.asyncio
async def test_report_read_allowed_for_owner(
    client, normal_token, normal_user, sample_device, test_db
):
    """普通用户读取本人报告 200。"""
    task = TestTask(
        user_id=normal_user.id,
        device_id=sample_device.id,
        name="normal-report-task",
        selected_items=[],
        status="completed",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    response = await client.get(f"/api/v1/reports/{task.id}", headers=_auth(normal_token))
    assert response.status_code == 200, response.text


@pytest.mark.asyncio
async def test_batch_export_rejects_unauthorized_task(
    client, normal_token, normal_user, admin_user, sample_device, test_db
):
    """批量导出含越权任务时整体 403，不静默跳过。"""
    own = TestTask(user_id=normal_user.id, device_id=sample_device.id,
                   name="batch-own", selected_items=[], status="completed")
    other = TestTask(user_id=admin_user.id, device_id=sample_device.id,
                     name="batch-other", selected_items=[], status="completed")
    test_db.add_all([own, other])
    await test_db.commit()
    await test_db.refresh(own)
    await test_db.refresh(other)

    response = await client.get(
        "/api/v1/reports/batch/export",
        headers=_auth(normal_token),
        params={"task_ids": f"{own.id},{other.id}", "format": "json"},
    )
    assert response.status_code == 403, response.text


# ---------------------------------------------------------------- V1-07 WS disabled 用户 1008
async def _prepare_ws_user_task(test_db, username, user_status):
    user = User(
        username=username,
        password_hash=get_password_hash("ws-pass-123"),
        role="user",
        status=user_status,
        pc_identifier="ws-pc",
    )
    test_db.add(user)
    await test_db.commit()
    await test_db.refresh(user)
    device = _make_device(f"ws-dev-{username}", user.id, user.pc_identifier)
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)
    token, _ = create_access_token(data={"sub": user.username})
    task = TestTask(
        user_id=user.id,
        device_id=device.id,
        name=f"ws-task-{username}",
        selected_items=[],
        status="pending",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)
    return token, task.id


@pytest_asyncio.fixture(name="ws_disabled_ctx")
async def _ws_disabled_ctx(test_db, mock_adb):
    """disabled 用户的 WS 上下文（token + 任务）。"""
    token, task_id = await _prepare_ws_user_task(test_db, "ws-disabled", "disabled")
    return token, task_id


@pytest_asyncio.fixture(name="ws_active_ctx")
async def _ws_active_ctx(test_db, mock_adb):
    """active 用户的 WS 上下文（token + 任务）。"""
    token, task_id = await _prepare_ws_user_task(test_db, "ws-active", "active")
    return token, task_id


def test_ws_disabled_user_closed_1008(ws_disabled_ctx):
    """V1-07：disabled 用户 WS 首消息订阅必须以 1008 关闭。

    不使用 `with TestClient(app)` 触发 lifespan：WS 端点鉴权不依赖启动期初始化，
    避免与其它并行任务的启动校验/迁移逻辑耦合（test_db 已建好表结构）。
    """
    from starlette.websockets import WebSocketDisconnect

    token, task_id = ws_disabled_ctx
    client = TestClient(app)
    with client.websocket_connect(f"/ws/tasks/{task_id}") as ws:
        ws.send_json({"token": token})
        with pytest.raises(WebSocketDisconnect) as exc_info:
            ws.receive_json()
        assert exc_info.value.code == status.WS_1008_POLICY_VIOLATION


def test_ws_active_user_still_allowed(ws_active_ctx):
    """对照：active 用户本人任务 WS 认证通过（不影响正常订阅）。"""
    token, task_id = ws_active_ctx
    client = TestClient(app)
    with client.websocket_connect(f"/ws/tasks/{task_id}") as ws:
        ws.send_json({"token": token})
        first = ws.receive_json()
        assert first["type"] == "test_progress"
        assert first["task_id"] == task_id


# ---------------------------------------------------------------- disabled REST 403（防御）
@pytest.mark.asyncio
async def test_disabled_user_rest_403(client, test_db):
    """disabled 用户任何 REST 受保护接口 403（get_current_user 拦截）。"""
    user = User(
        username="rest-disabled",
        password_hash=get_password_hash("rest-pass-123"),
        role="user",
        status="disabled",
        pc_identifier="rest-pc",
    )
    test_db.add(user)
    await test_db.commit()
    token, _ = create_access_token(data={"sub": user.username})

    response = await client.get("/api/v1/tasks", headers=_auth(token))
    assert response.status_code == 403, response.text
