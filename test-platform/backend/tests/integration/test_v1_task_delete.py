"""V1-09b（T-14）：任务删除边界、item_ids 写前校验与设备不可用 409 回归。

覆盖契约 task-execution：
- §8 DELETE /tasks/{id}：仅 active 管理员；pending/running → 409；终态软删除
  deleted_at 幂等（重复删除 200 不 500）；默认列表/详情排除已删除；记录引用保留；
- §2/R14：item_ids 空/非正/重复 → 400 details.field=item_ids；不存在/禁用 → 400
  details.field=item_ids.<下标>（原 404 改 400）；
- §2/V1-04 D2：创建任务设备 offline/maintenance → 409 CONFLICT（原 400 改 409）；
  重跑（§7）设备不可用同样 409。
"""
import pytest
import pytest_asyncio
from sqlalchemy import func, select

from app.models import TestItem, TestRecord, TestTask


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _task_count(test_db) -> int:
    return await test_db.scalar(select(func.count()).select_from(TestTask))


async def _make_task(test_db, user, device, status="completed", name="del-task", items=None):
    task = TestTask(
        user_id=user.id,
        device_id=device.id,
        name=name,
        selected_items=items or [],
        status=status,
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)
    return task


# ---------------------------------------------------------------- DELETE 软删除边界
@pytest.mark.asyncio
async def test_admin_soft_delete_completed_task(
    client, admin_token, admin_user, sample_device, sample_item, test_db
):
    """终态任务软删除：200、deleted_at 写入、记录保留、默认列表/详情排除。"""
    task = await _make_task(test_db, admin_user, sample_device, status="completed",
                            name="soft-del-task", items=[sample_item.id])
    test_db.add(TestRecord(task_id=task.id, item_id=sample_item.id, status="pass"))
    await test_db.commit()

    response = await client.delete(f"/api/v1/tasks/{task.id}", headers=_auth(admin_token))
    assert response.status_code == 200, response.text
    body = response.json()
    assert body["code"] == 200
    assert body["data"] == {"id": task.id, "deleted": True, "artifacts": "retained"}

    await test_db.refresh(task)
    assert task.deleted_at is not None
    # 记录引用保留（可追溯），任务行仍在
    assert task.id is not None
    records = (await test_db.execute(
        select(func.count()).select_from(TestRecord).where(TestRecord.task_id == task.id)
    )).scalar()
    assert records == 1

    # 默认列表排除已删除任务
    listed = await client.get("/api/v1/tasks", headers=_auth(admin_token))
    assert listed.status_code == 200
    ids = [item["id"] for item in listed.json()["data"]["items"]]
    assert task.id not in ids

    # 详情默认 404（契约：默认不返回已删除任务）
    detail = await client.get(f"/api/v1/tasks/{task.id}", headers=_auth(admin_token))
    assert detail.status_code == 404


@pytest.mark.asyncio
async def test_repeat_delete_is_idempotent(
    client, admin_token, admin_user, sample_device, test_db
):
    """重复删除返回相同 200，不 500、不重复改写 deleted_at。"""
    task = await _make_task(test_db, admin_user, sample_device, status="completed",
                            name="repeat-del")
    first = await client.delete(f"/api/v1/tasks/{task.id}", headers=_auth(admin_token))
    assert first.status_code == 200, first.text
    await test_db.refresh(task)
    deleted_at_first = task.deleted_at
    assert deleted_at_first is not None

    second = await client.delete(f"/api/v1/tasks/{task.id}", headers=_auth(admin_token))
    assert second.status_code == 200, second.text
    assert second.json()["data"]["deleted"] is True
    await test_db.refresh(task)
    assert task.deleted_at == deleted_at_first


@pytest.mark.asyncio
@pytest.mark.parametrize("status_", ["pending", "running"])
async def test_delete_pending_or_running_returns_409(
    client, admin_token, admin_user, sample_device, test_db, status_
):
    """pending/running 状态不可删除 → 409 CONFLICT，且不写 deleted_at。"""
    task = await _make_task(test_db, admin_user, sample_device, status=status_,
                            name=f"del-{status_}")
    response = await client.delete(f"/api/v1/tasks/{task.id}", headers=_auth(admin_token))
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "CONFLICT"
    assert "不可删除" in body["message"]
    await test_db.refresh(task)
    assert task.deleted_at is None


@pytest.mark.asyncio
async def test_delete_forbidden_for_normal_user(
    client, normal_token, admin_user, sample_device, test_db
):
    """非管理员删除任务 → 403（越权零写入）。"""
    task = await _make_task(test_db, admin_user, sample_device, status="completed",
                            name="forbidden-del")
    response = await client.delete(f"/api/v1/tasks/{task.id}", headers=_auth(normal_token))
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"
    await test_db.refresh(task)
    assert task.deleted_at is None


@pytest.mark.asyncio
async def test_delete_nonexistent_returns_404(client, admin_token):
    """任务不存在 → 404。"""
    response = await client.delete("/api/v1/tasks/999999", headers=_auth(admin_token))
    assert response.status_code == 404


# ---------------------------------------------------------------- item_ids 写前校验（R14）
@pytest.mark.asyncio
@pytest.mark.parametrize(
    "item_ids, expected_field",
    [
        ([], "item_ids"),
        ([0], "item_ids"),
        ([-1], "item_ids"),
        ([1, 1], "item_ids"),
        (["abc"], "item_ids.0"),
    ],
)
async def test_item_ids_schema_constraints_return_400(
    client, admin_token, sample_device, sample_item, test_db, item_ids, expected_field
):
    """item_ids 空/非正/重复/错类型 → 400 VALIDATION_ERROR，details.field=item_ids（.*），零写入。"""
    before = await _task_count(test_db)
    response = await client.post(
        "/api/v1/tasks",
        headers=_auth(admin_token),
        json={"device_serial": sample_device.serial_number, "item_ids": item_ids},
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["field"] == expected_field, body
    assert await _task_count(test_db) == before


@pytest.mark.asyncio
async def test_nonexistent_item_returns_400_with_index_field(
    client, admin_token, sample_device, sample_item, test_db
):
    """不存在的 item_id → 400（R14），details.field=item_ids.<下标>，零任务写入。"""
    before = await _task_count(test_db)
    response = await client.post(
        "/api/v1/tasks",
        headers=_auth(admin_token),
        json={"device_serial": sample_device.serial_number,
              "item_ids": [sample_item.id, 99999]},
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["field"] == "item_ids.1"
    assert await _task_count(test_db) == before


@pytest.mark.asyncio
async def test_disabled_item_returns_400_with_index_field(
    client, admin_token, admin_user, sample_module, test_db, sample_device
):
    """禁用的测试项 → 400，details.field=item_ids.<下标>。"""
    disabled = TestItem(
        module_id=sample_module.id,
        name="Disabled Item",
        exec_type="adb_shell",
        exec_command="echo ok",
        parameters={},
        compatibility={},
        judgement_type="assertion",
        result_parse={"pass_pattern": "ok"},
        timeout=30,
        enabled=False,
        created_by=admin_user.id,
    )
    test_db.add(disabled)
    await test_db.commit()
    await test_db.refresh(disabled)

    response = await client.post(
        "/api/v1/tasks",
        headers=_auth(admin_token),
        json={"device_serial": sample_device.serial_number, "item_ids": [disabled.id]},
    )
    assert response.status_code == 400, response.text
    body = response.json()
    assert body["code"] == "VALIDATION_ERROR"
    assert body["details"]["field"] == "item_ids.0"
    assert "禁用" in body["details"]["reason"]


# ---------------------------------------------------------------- D2：设备不可用 409
@pytest.mark.asyncio
@pytest.mark.parametrize("device_status", ["offline", "maintenance"])
async def test_create_task_device_unavailable_returns_409(
    client, admin_token, sample_device, sample_item, test_db, device_status
):
    """创建任务：offline/maintenance → 409 CONFLICT（V1-04 D2，原 400 改 409）。"""
    sample_device.status = device_status
    await test_db.commit()

    before = await _task_count(test_db)
    response = await client.post(
        "/api/v1/tasks",
        headers=_auth(admin_token),
        json={"device_serial": sample_device.serial_number, "item_ids": [sample_item.id]},
    )
    assert response.status_code == 409, response.text
    body = response.json()
    assert body["code"] == "CONFLICT"
    assert await _task_count(test_db) == before


@pytest.mark.asyncio
async def test_rerun_device_unavailable_returns_409(
    client, admin_token, admin_user, sample_device, sample_item, test_db
):
    """重跑：设备 offline → 409 CONFLICT（契约 §7）。"""
    task = await _make_task(test_db, admin_user, sample_device, status="completed",
                            name="rerun-offline", items=[sample_item.id])
    test_db.add(TestRecord(task_id=task.id, item_id=sample_item.id, status="fail",
                           fail_reason="x"))
    await test_db.commit()

    sample_device.status = "offline"
    await test_db.commit()
    before = await _task_count(test_db)

    response = await client.post(
        f"/api/v1/tasks/{task.id}/rerun-failed", headers=_auth(admin_token)
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "CONFLICT"
    assert await _task_count(test_db) == before
