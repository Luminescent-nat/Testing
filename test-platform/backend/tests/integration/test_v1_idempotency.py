"""V1-04 任务创建/重跑幂等与 201 永久回归测试（T-10）。

覆盖契约 docs/contracts/README.md 第 3 节：
- 同用户/同操作/同键/同请求体：重放返回首次响应与同一任务 ID，数据库仅 1 行任务；
- 同键不同请求体：409 CONFLICT；
- 并发 10 次：至多一次真实创建（DB 唯一约束兜底），全部返回同一任务 ID；
- Idempotency-Key 缺失：400 VALIDATION_ERROR（U-D1 已确认收紧为强制必填，零写入）；
- 非法键（过短/不可打印 ASCII）：400 VALIDATION_ERROR；
- 重跑端点 POST /tasks/{id}/reruns 与 legacy /rerun-failed：201 且复用幂等。
"""
import asyncio

import pytest
from httpx import AsyncClient
from sqlalchemy import func, select

from app.models import Device, IdempotencyRecord, TestItem, TestRecord, TestTask
from app.services.task_executor import TaskExecutor


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


async def _count(db, model) -> int:
    return int(await db.scalar(select(func.count()).select_from(model)) or 0)


def _payload(device: Device, item: TestItem, name: str = "IdemTask") -> dict:
    return {
        "device_serial": device.serial_number,
        "name": name,
        "item_ids": [item.id],
        "schedule_type": "immediate",
    }


@pytest.mark.asyncio
async def test_same_key_same_body_replays_single_task(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    test_db, monkeypatch,
):
    """两次同键同体请求：均 201、同一任务 ID、数据库仅 1 行任务与 1 行幂等记录。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    headers = {**_auth(admin_token), "Idempotency-Key": "idem-same-key-0001"}
    payload = _payload(sample_device, sample_item)

    first = await client.post("/api/v1/tasks", headers=headers, json=payload)
    second = await client.post("/api/v1/tasks", headers=headers, json=payload)

    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    assert first.json()["code"] == 201 and second.json()["code"] == 201
    assert second.json()["data"]["id"] == first.json()["data"]["id"]
    assert await _count(test_db, TestTask) == 1
    assert await _count(test_db, IdempotencyRecord) == 1


@pytest.mark.asyncio
async def test_same_key_different_body_returns_409(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    test_db, monkeypatch,
):
    """同键不同请求体 → 409 CONFLICT，且不创建第二个任务。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    headers = {**_auth(admin_token), "Idempotency-Key": "idem-conflict-key-0001"}

    first = await client.post("/api/v1/tasks", headers=headers,
                              json=_payload(sample_device, sample_item, name="first"))
    assert first.status_code == 201, first.text

    second = await client.post("/api/v1/tasks", headers=headers,
                               json=_payload(sample_device, sample_item, name="second"))
    assert second.status_code == 409, second.text
    assert second.json()["code"] == "CONFLICT"
    assert await _count(test_db, TestTask) == 1


@pytest.mark.asyncio
async def test_concurrent_same_key_creates_at_most_one_task(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    test_db, monkeypatch,
):
    """并发 10 次同键同体：全部 201、同一任务 ID、数据库仅 1 行任务、1 行幂等记录。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    headers = {**_auth(admin_token), "Idempotency-Key": "idem-concurrent-key-0001"}
    payload = _payload(sample_device, sample_item, name="ConcurrentTask")

    responses = await asyncio.gather(
        *[client.post("/api/v1/tasks", headers=headers, json=payload) for _ in range(10)]
    )

    assert all(r.status_code == 201 for r in responses), [r.status_code for r in responses]
    ids = {r.json()["data"]["id"] for r in responses}
    assert len(ids) == 1, ids
    assert await _count(test_db, TestTask) == 1
    assert await _count(test_db, IdempotencyRecord) == 1


@pytest.mark.asyncio
async def test_missing_key_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    test_db, monkeypatch,
):
    """缺失 Idempotency-Key：400 VALIDATION_ERROR（强制必填），零任务零幂等记录写入。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    payload = _payload(sample_device, sample_item, name="NoKeyTask")
    headers = {**_auth(admin_token), "X-Test-No-Idempotency-Key": "1"}

    first = await client.post("/api/v1/tasks", headers=headers, json=payload)

    assert first.status_code == 400
    assert first.json()["code"] == "VALIDATION_ERROR"
    assert await _count(test_db, TestTask) == 0
    assert await _count(test_db, IdempotencyRecord) == 0


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_key", ["short", "x" * 129, "bad\tkey-with-tab"])
async def test_invalid_idempotency_key_rejected(
    client: AsyncClient, admin_token: str, sample_device: Device, sample_item: TestItem,
    test_db, monkeypatch, bad_key,
):
    """非法 Idempotency-Key（过短/过长/不可打印 ASCII）→ 400 VALIDATION_ERROR，零写入。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    response = await client.post(
        "/api/v1/tasks",
        headers={**_auth(admin_token), "Idempotency-Key": bad_key},
        json=_payload(sample_device, sample_item),
    )
    assert response.status_code == 400, response.text
    assert response.json()["code"] == "VALIDATION_ERROR"
    assert await _count(test_db, TestTask) == 0


async def _make_completed_task_with_fail(test_db, admin_user, sample_device, sample_item):
    task = TestTask(
        user_id=admin_user.id,
        device_id=sample_device.id,
        name="IdemRerunSrc",
        selected_items=[sample_item.id],
        status="completed",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)
    test_db.add(TestRecord(task_id=task.id, item_id=sample_item.id, status="fail", fail_reason="断言失败"))
    await test_db.commit()
    return task


@pytest.mark.asyncio
async def test_rerun_endpoints_return_201_and_reuse_idempotency(
    client: AsyncClient, admin_token: str, admin_user, sample_device: Device, sample_item: TestItem,
    test_db, monkeypatch,
):
    """重跑目标/legacy 端点：201，同键重放返回同一新任务；不同源任务同键 409。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    src = await _make_completed_task_with_fail(test_db, admin_user, sample_device, sample_item)
    headers = {**_auth(admin_token), "Idempotency-Key": "idem-rerun-key-0001"}

    first = await client.post(f"/api/v1/tasks/{src.id}/reruns", headers=headers)
    assert first.status_code == 201, first.text
    assert first.json()["code"] == 201
    rerun_id = first.json()["data"]["id"]

    again = await client.post(f"/api/v1/tasks/{src.id}/reruns", headers=headers)
    assert again.status_code == 201, again.text
    assert again.json()["data"]["id"] == rerun_id

    legacy = await client.post(f"/api/v1/tasks/{src.id}/rerun-failed", headers=headers)
    assert legacy.status_code == 201, legacy.text
    assert legacy.json()["data"]["id"] == rerun_id

    # 同一幂等键用于不同源任务（请求体 task_id 不同）→ 409
    src2 = await _make_completed_task_with_fail(test_db, admin_user, sample_device, sample_item)
    conflict = await client.post(f"/api/v1/tasks/{src2.id}/reruns", headers=headers)
    assert conflict.status_code == 409, conflict.text
    assert conflict.json()["code"] == "CONFLICT"

    # 源任务 1 + 源任务 2（为验证 409 构造）+ 唯一重跑任务 1 = 3；重跑只创建一次
    assert await _count(test_db, TestTask) == 3
    assert await _count(test_db, IdempotencyRecord) == 1


@pytest.mark.asyncio
async def test_rerun_without_key_returns_400(
    client: AsyncClient, admin_token: str, admin_user, sample_device: Device, sample_item: TestItem,
    test_db, monkeypatch,
):
    """重跑缺失 Idempotency-Key：400 VALIDATION_ERROR（强制必填），零写入。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    src = await _make_completed_task_with_fail(test_db, admin_user, sample_device, sample_item)

    headers = {**_auth(admin_token), "X-Test-No-Idempotency-Key": "1"}
    first = await client.post(f"/api/v1/tasks/{src.id}/rerun-failed", headers=headers)
    assert first.status_code == 400
    assert first.json()["code"] == "VALIDATION_ERROR"
    assert await _count(test_db, TestTask) == 1  # 仅源任务，无重跑任务写入
