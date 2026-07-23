"""测试任务接口集成测试。"""
import pytest
from httpx import AsyncClient
from unittest.mock import AsyncMock

from sqlalchemy import select

from app.models import Device, TestItem, TestRecord, TestTask
from app.services.task_executor import TaskExecutor


@pytest.mark.asyncio
async def test_create_task_success(
    client: AsyncClient,
    admin_token: str,
    sample_device: Device,
    sample_item: TestItem,
    mock_adb,
):
    """TC-TASK-001: 创建测试任务。"""
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "name": "TestTask",
            "item_ids": [sample_item.id],
            "custom_parameters": {},
        },
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["status"] == "pending"
    assert data["device_serial"] == sample_device.serial_number


@pytest.mark.asyncio
async def test_create_task_device_offline(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem
):
    """TC-TASK-002: 离线设备不能创建任务。"""
    # 通过 API 将设备置为 offline 状态
    status_res = await client.put(
        f"/api/v1/devices/{sample_device.serial_number}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "offline"},
    )
    assert status_res.status_code == 200

    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "name": "TestTask",
            "item_ids": [sample_item.id],
        },
    )
    assert response.status_code == 400
    assert "离线" in response.json()["detail"]


@pytest.mark.asyncio
async def test_create_task_device_busy(
    client: AsyncClient,
    admin_token: str,
    sample_device: Device,
    sample_item: TestItem,
    mock_adb,
):
    """TC-TASK-003: 设备被占用（testing）时任务排队创建，不再直接拒绝。"""
    # 通过 API 将设备置为 testing 状态
    status_res = await client.put(
        f"/api/v1/devices/{sample_device.serial_number}/status",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={"status": "testing"},
    )
    assert status_res.status_code == 200

    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "name": "QueuedTask",
            "item_ids": [sample_item.id],
        },
    )
    # 排队创建成功，任务初始为 pending，由执行器设备锁串行化执行
    assert response.status_code == 200
    assert response.json()["data"]["status"] == "pending"


@pytest.mark.asyncio
async def test_create_task_invalid_item(
    client: AsyncClient, admin_token: str, sample_device: Device
):
    """TC-TASK-004: 不存在的测试项应 404。"""
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "name": "TestTask",
            "item_ids": [99999],
        },
    )
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_list_tasks(
    client: AsyncClient,
    admin_token: str,
    sample_device: Device,
    sample_item: TestItem,
):
    """TC-TASK-005: 任务列表包含已创建任务。"""
    await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "name": "ListTask",
            "item_ids": [sample_item.id],
        },
    )

    response = await client.get(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["total"] >= 1


@pytest.mark.asyncio
async def test_get_task_detail(
    client: AsyncClient,
    admin_token: str,
    sample_device: Device,
    sample_item: TestItem,
):
    """TC-TASK-006: 获取任务详情。"""
    create_res = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "name": "DetailTask",
            "item_ids": [sample_item.id],
        },
    )
    task_id = create_res.json()["data"]["id"]

    response = await client.get(
        f"/api/v1/tasks/{task_id}",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    assert response.json()["data"]["id"] == task_id


@pytest.mark.asyncio
async def test_cancel_task(
    client: AsyncClient,
    admin_token: str,
    sample_device: Device,
    sample_item: TestItem,
    monkeypatch,
):
    """TC-TASK-007: 取消 pending 任务。"""
    # 阻止后台任务实际执行，确保取消时任务仍处于 pending 状态
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)

    create_res = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "name": "CancelTask",
            "item_ids": [sample_item.id],
        },
    )
    task_id = create_res.json()["data"]["id"]

    response = await client.post(
        f"/api/v1/tasks/{task_id}/cancel",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200


@pytest.mark.asyncio
async def test_task_records_after_sync_execution(
    client: AsyncClient,
    admin_token: str,
    sample_device: Device,
    sample_item: TestItem,
    mock_adb,
):
    """TC-TASK-008: 同步执行任务并验证记录。"""
    # mock adb shell 返回匹配 pass_pattern 的输出
    mock_adb.execute_shell = AsyncMock(return_value=("ok", "", 0))

    create_res = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {admin_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "name": "RunTask",
            "item_ids": [sample_item.id],
        },
    )
    task_id = create_res.json()["data"]["id"]

    # 等待 API 启动的后台任务完成
    running = TaskExecutor._running_tasks.get(task_id)
    if running:
        await running

    response = await client.get(
        f"/api/v1/tasks/{task_id}/records",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    records = response.json()["data"]["items"]
    assert len(records) == 1
    assert records[0]["status"] == "pass"


@pytest.mark.asyncio
async def test_rerun_failed_creates_task_with_failed_items_only(
    client: AsyncClient,
    admin_token: str,
    admin_user,
    sample_device: Device,
    sample_module,
    sample_item: TestItem,
    test_db,
    mock_adb,
):
    """TC-TASK-009: 重跑失败项创建的新任务只包含失败/错误/超时的测试项。"""
    # 第二个测试项（通过的）
    item2 = TestItem(
        module_id=sample_module.id,
        name="Passed Item",
        exec_type="adb_shell",
        exec_command="echo ok",
        parameters={},
        compatibility={},
        judgement_type="assertion",
        result_parse={"pass_pattern": "ok"},
        timeout=30,
        created_by=admin_user.id,
    )
    test_db.add(item2)
    await test_db.commit()
    await test_db.refresh(item2)

    # 已完成的任务：item1 失败、item2 通过
    task = TestTask(
        user_id=admin_user.id,
        device_id=sample_device.id,
        name="RerunSrc",
        selected_items=[sample_item.id, item2.id],
        status="completed",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    test_db.add_all([
        TestRecord(task_id=task.id, item_id=sample_item.id, status="fail", fail_reason="断言失败"),
        TestRecord(task_id=task.id, item_id=item2.id, status="pass"),
    ])
    await test_db.commit()

    response = await client.post(
        f"/api/v1/tasks/{task.id}/rerun-failed",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["name"] == "RerunSrc（重跑）"
    assert data["device_serial"] == sample_device.serial_number

    # 新任务只包含失败项
    result = await test_db.execute(
        select(TestTask).where(TestTask.id == data["id"])
    )
    new_task = result.scalar_one()
    assert new_task.selected_items == [sample_item.id]

    # 等待 API 启动的后台重跑任务结束，避免污染其他用例
    running = TaskExecutor._running_tasks.get(new_task.id)
    if running:
        await running


@pytest.mark.asyncio
async def test_rerun_failed_without_failures_returns_400(
    client: AsyncClient,
    admin_token: str,
    admin_user,
    sample_device: Device,
    sample_item: TestItem,
    test_db,
):
    """TC-TASK-010: 任务没有失败项时重跑返回 400。"""
    task = TestTask(
        user_id=admin_user.id,
        device_id=sample_device.id,
        name="AllPass",
        selected_items=[sample_item.id],
        status="completed",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    test_db.add(TestRecord(task_id=task.id, item_id=sample_item.id, status="pass"))
    await test_db.commit()

    response = await client.post(
        f"/api/v1/tasks/{task.id}/rerun-failed",
        headers={"Authorization": f"Bearer {admin_token}"},
    )
    assert response.status_code == 400
