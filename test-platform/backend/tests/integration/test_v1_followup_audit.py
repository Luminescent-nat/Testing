"""V1 followup 契约收口永久回归（task-22）。

覆盖契约缺口：
- AI 自然语言创建设备 offline/maintenance → 409 CONFLICT（与手动创建 D2 一致，零任务写入）；
- PATCH /devices/{serial} owner_id 必填（可显式 null 取消分配）；
- POST /device-discoveries 请求体必须为空对象 {}；
- maintenance 设备详情/列表可序列化且 status=maintenance 过滤正常；
- GET /devices 分页 page>=1、1<=page_size<=100，非法 400。
"""
import pytest
from sqlalchemy import func, select

from app.models import Device, TestTask
from app.services.nl_task_planner import NLTaskPlanner
from app.services.task_executor import TaskExecutor


def _auth(token):
    return {"Authorization": f"Bearer {token}"}


@pytest.mark.asyncio
async def test_audit_ai_maintenance_device_cannot_start(
    client, normal_token, normal_user, sample_item, test_db, monkeypatch
):
    device = Device(
        serial_number="audit-ai-maintenance", model="rk3568", status="maintenance",
        owner_id=normal_user.id, pc_identifier=normal_user.pc_identifier,
    )
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)

    async def fake_plan(self, text, user_id, pc_identifier):
        return {"device_id": device.id, "item_ids": [sample_item.id], "intent": "audit"}

    monkeypatch.setattr(NLTaskPlanner, "plan", fake_plan)
    monkeypatch.setattr("app.api.ai_tasks.LLMClient.get_default_client", lambda: None)
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    response = await client.post(
        "/api/v1/ai/tasks/natural", headers=_auth(normal_token), json={"text": "audit"}
    )
    assert response.status_code == 409, response.text
    assert await test_db.scalar(select(func.count()).select_from(TestTask)) == 0


@pytest.mark.asyncio
async def test_audit_patch_owner_id_is_required_even_when_nullable(
    client, admin_token, sample_device
):
    response = await client.patch(
        f"/api/v1/devices/{sample_device.serial_number}",
        headers=_auth(admin_token),
        json={"pc_identifier": "pc-a", "version": sample_device.version},
    )
    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_audit_discovery_rejects_nonempty_body(
    client, normal_token, sample_device, mock_adb
):
    response = await client.post(
        "/api/v1/device-discoveries",
        headers=_auth(normal_token),
        json={"owner_id": sample_device.owner_id},
    )
    assert response.status_code == 400, response.text


@pytest.mark.asyncio
async def test_audit_maintenance_device_serializes_and_is_filterable(
    client, admin_token, sample_device, test_db
):
    sample_device.status = "maintenance"
    await test_db.commit()
    detail = await client.get(
        f"/api/v1/devices/{sample_device.serial_number}", headers=_auth(admin_token)
    )
    listing = await client.get(
        "/api/v1/devices?status=maintenance", headers=_auth(admin_token)
    )
    assert detail.status_code == 200, detail.text
    assert listing.status_code == 200, listing.text


@pytest.mark.asyncio
async def test_audit_device_list_rejects_invalid_pagination(
    client, admin_token, sample_device
):
    response = await client.get(
        "/api/v1/devices?page=0&page_size=1000", headers=_auth(admin_token)
    )
    assert response.status_code == 400, response.text
