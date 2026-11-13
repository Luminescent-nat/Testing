"""V1 followup 契约收口永久回归（task-22）+ v1.1 授权顺序（task-24 B1~B3）。

覆盖契约缺口：
- AI 自然语言创建设备 offline/maintenance → 409 CONFLICT（与手动创建 D2 一致，零任务写入）；
- PATCH /devices/{serial} owner_id 必填（可显式 null 取消分配）；
- POST /device-discoveries 请求体必须为空对象 {}；
- maintenance 设备详情/列表可序列化且 status=maintenance 过滤正常；
- GET /devices 分页 page>=1、1<=page_size<=100，非法 400。

契约 v1.1 task-execution §10 授权顺序（B1~B3，GWT）：
- B1：普通用户对他人设备提交 AI 文本 → 403，且知识库读取与 LLMClient 调用计数为 0；
- B2：maintenance 设备走 AI 入口 → 409，且两计数为 0；
- B3：AI 与手动创建同设备同 item 集合，落库行/设备状态推进/幂等语义逐字段一致（plan 仅 AI 有）。
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
    client, normal_token, normal_user, sample_item, test_db
):
    device = Device(
        serial_number="audit-ai-maintenance", model="rk3568", status="maintenance",
        owner_id=normal_user.id, pc_identifier=normal_user.pc_identifier,
    )
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)

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


# ---------------------------------------------------------------- 契约 v1.1 授权顺序（B1~B3）
def _install_knowledge_llm_counters(monkeypatch):
    """monkeypatch 知识库读取与 LLMClient 调用计数器，返回 counters dict。"""
    counters = {"knowledge": 0, "llm": 0}

    import app.services.nl_task_planner as planner_mod

    real_knowledge = planner_mod.get_device_knowledge

    async def counting_knowledge(*args, **kwargs):
        counters["knowledge"] += 1
        return await real_knowledge(*args, **kwargs)

    monkeypatch.setattr(planner_mod, "get_device_knowledge", counting_knowledge)

    class _CountingLLMClient:
        @staticmethod
        def get_default_client():
            counters["llm"] += 1
            return None

    import app.api.ai_tasks as ai_mod

    monkeypatch.setattr(ai_mod, "LLMClient", _CountingLLMClient)
    return counters


@pytest.mark.asyncio
async def test_b1_ai_other_users_device_403_zero_knowledge_llm(
    client, normal_token, normal_user, admin_user, test_db, monkeypatch
):
    """B1：普通用户对他人设备提交 AI 文本 → 403，且知识/LLM 调用计数为 0（v1.1 §10）。"""
    device = Device(
        serial_number="b1-other-device",
        model="rk3568",
        status="online",
        owner_id=admin_user.id,
        pc_identifier="b1-admin-pc",
    )
    test_db.add(device)
    await test_db.commit()

    counters = _install_knowledge_llm_counters(monkeypatch)
    response = await client.post(
        "/api/v1/ai/tasks/natural",
        headers=_auth(normal_token),
        json={"text": "对 rk3568 设备做 DDR 功能测试"},
    )
    assert response.status_code == 403, response.text
    assert response.json()["code"] == "FORBIDDEN"
    assert counters["knowledge"] == 0, counters
    assert counters["llm"] == 0, counters
    assert await test_db.scalar(select(func.count()).select_from(TestTask)) == 0


@pytest.mark.asyncio
async def test_b2_ai_maintenance_device_409_zero_knowledge_llm(
    client, normal_token, normal_user, sample_item, test_db, monkeypatch
):
    """B2：maintenance 设备走 AI 入口 → 409，且知识/LLM 调用计数为 0（v1.1 §10）。"""
    device = Device(
        serial_number="b2-maintenance-device",
        model="rk3568",
        status="maintenance",
        owner_id=normal_user.id,
        pc_identifier=normal_user.pc_identifier,
    )
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)

    counters = _install_knowledge_llm_counters(monkeypatch)
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    response = await client.post(
        "/api/v1/ai/tasks/natural",
        headers=_auth(normal_token),
        json={"text": "对 rk3568 设备做 DDR 功能测试"},
    )
    assert response.status_code == 409, response.text
    assert response.json()["code"] == "CONFLICT"
    assert counters["knowledge"] == 0, counters
    assert counters["llm"] == 0, counters
    assert await test_db.scalar(select(func.count()).select_from(TestTask)) == 0


@pytest.mark.asyncio
async def test_b3_ai_and_manual_creation_parity(
    client, admin_token, admin_user, sample_device, sample_item, test_db, monkeypatch
):
    """B3：同设备同 item 集合手动 vs AI 创建，落库行/设备状态/幂等语义逐字段一致。

    注：ai_tasks.py 删除自写任务逻辑后，AI 与手动都走统一创建服务（app/services/
    task_creation.py）；plan 快照仅存于 AI 任务行（手动为 None）。
    """
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)

    fixed_plan = {
        "device_serial": sample_device.serial_number,
        "device_id": sample_device.id,
        "intent": "B3差分测试",
        "selected_modules": ["cpu"],
        "test_type": "functional",
        "item_ids": [sample_item.id],
        "knowledge_matches": [],
        "notes": "",
        "llm_used": False,
    }

    async def fake_plan_for_device(self, text, device):
        plan = dict(fixed_plan)
        # intent 随文本变化，使 B3 幂等冲突用例的请求体可区分
        plan["intent"] = text.strip()[:50] or "B3差分测试"
        return plan

    monkeypatch.setattr(NLTaskPlanner, "plan_for_device", fake_plan_for_device)
    monkeypatch.setattr("app.api.ai_tasks.LLMClient.get_default_client", lambda: None)

    ai_key = {"Idempotency-Key": "b3-ai-key-0001", **_auth(admin_token)}
    ai_resp = await client.post(
        "/api/v1/ai/tasks/natural",
        headers=ai_key,
        json={"text": "对 rk3568 设备做 CPU 功能测试"},
    )
    assert ai_resp.status_code == 201, ai_resp.text
    ai_task_id = ai_resp.json()["data"]["id"]

    manual_resp = await client.post(
        "/api/v1/tasks",
        headers=_auth(admin_token),
        json={"device_serial": sample_device.serial_number, "item_ids": [sample_item.id]},
    )
    assert manual_resp.status_code == 201, manual_resp.text
    manual_task_id = manual_resp.json()["data"]["id"]

    ai_task = await test_db.get(TestTask, ai_task_id)
    manual_task = await test_db.get(TestTask, manual_task_id)
    assert ai_task and manual_task
    assert ai_task.id != manual_task.id

    # 逐字段一致性（同一创建服务）：B3 差分
    comparable_fields = (
        "user_id", "device_id", "selected_items", "custom_parameters",
        "status", "schedule_type", "next_run_at",
    )
    for field in comparable_fields:
        assert getattr(ai_task, field) == getattr(manual_task, field), field
    assert ai_task.user_id == admin_user.id
    # plan 快照仅 AI 任务持有
    assert ai_task.plan is not None
    assert ai_task.plan["intent"] == "对 rk3568 设备做 CPU 功能测试"
    assert manual_task.plan is None

    # 设备状态推进一致（immediate 创建后 testing）
    await test_db.refresh(sample_device)
    assert sample_device.status == "testing"

    # 幂等语义一致：同键同文本重放返回同一任务（即使设备已进入 testing，重放不被
    # 状态 409 掩盖——重放预检先于设备可用性检查）；同键不同文本 409
    ai_second = await client.post(
        "/api/v1/ai/tasks/natural", headers=ai_key,
        json={"text": "对 rk3568 设备做 CPU 功能测试"},
    )
    assert ai_second.status_code == 201, ai_second.text
    assert ai_second.json()["data"]["id"] == ai_task_id
    ai_conflict = await client.post(
        "/api/v1/ai/tasks/natural", headers=ai_key,
        json={"text": "对 rk3568 设备做 DDR 稳定性测试"},
    )
    assert ai_conflict.status_code == 409, ai_conflict.text
    assert ai_conflict.json()["code"] == "CONFLICT"
