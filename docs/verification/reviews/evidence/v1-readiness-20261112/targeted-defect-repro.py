"""V1.0 readiness 独立定向复现；仅用于审计，不作为交付测试保留。"""
import asyncio

import pytest
from sqlalchemy import select

from app.models import Device, TestItem, TestModule, TestRecord, TestTask
from app.services.judgement_engine import JudgementEngine, RuleBasedJudger
from app.services.task_executor import DeviceLock, TaskExecutor
from app.services.tool_manifest import discover_requirements


@pytest.mark.asyncio
async def test_audit_normal_user_cannot_start_task_on_other_users_device(
    client, normal_token, admin_user, sample_device, sample_item, monkeypatch
):
    """普通用户使用他人且异 PC 设备创建任务必须为 403，且不得写任务。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    response = await client.post(
        "/api/v1/tasks",
        headers={"Authorization": f"Bearer {normal_token}"},
        json={
            "device_serial": sample_device.serial_number,
            "item_ids": [sample_item.id],
            "schedule_type": "immediate",
        },
    )
    assert response.status_code == 403, response.text
    tasks = (await client.get(
        "/api/v1/tasks", headers={"Authorization": f"Bearer {normal_token}"}
    )).json()
    assert tasks["data"]["total"] == 0


@pytest.mark.asyncio
async def test_audit_same_idempotency_key_creates_only_one_task(
    client, admin_token, sample_device, sample_item, test_db, monkeypatch
):
    """相同幂等键和请求体重放不得创建第二个任务。"""
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: True)
    payload = {
        "device_serial": sample_device.serial_number,
        "item_ids": [sample_item.id],
        "schedule_type": "immediate",
    }
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Idempotency-Key": "audit-same-key-0001",
    }
    first = await client.post("/api/v1/tasks", headers=headers, json=payload)
    second = await client.post("/api/v1/tasks", headers=headers, json=payload)
    assert second.json()["data"]["id"] == first.json()["data"]["id"]
    assert first.status_code == 201, first.text
    assert second.status_code == 201, second.text
    count = await test_db.execute(select(TestTask).where(TestTask.name == first.json()["data"]["name"]))
    assert len(count.scalars().all()) == 1


@pytest.mark.asyncio
async def test_audit_falsy_invalid_rules_cannot_be_passed_by_pattern():
    """conditional_rules=[] 是非法根结构，不得经 pass_pattern 变成 pass。"""
    result = await JudgementEngine().judge(
        output="ok",
        returncode=0,
        item_name="audit",
        item_description="",
        judgement_type="assertion",
        rules=[],
        rubric_criteria={},
        device_context={},
        result_parse={"pass_pattern": "ok"},
    )
    assert result.status == "error", result.to_dict()


def test_audit_approx_ratio_zero_target_cannot_pass():
    """零目标不是合法 approx_ratio 配置，任意实际值都不得直接判通过。"""
    ok, _ = RuleBasedJudger()._compare(100, "approx_ratio", 0, "0%")
    assert ok is False


@pytest.mark.asyncio
async def test_audit_stop_on_failure_completes_remaining_items_as_skip(
    test_db, mock_adb, admin_user
):
    """5 项中第 2 项 stop+fail 后，剩余 3 项必须补 skip，不能 completed/100% 只有两条记录。"""
    from unittest.mock import AsyncMock

    device = Device(
        serial_number="audit-stop-device", model="rk3568", status="online",
        pc_identifier=admin_user.pc_identifier, owner_id=admin_user.id,
    )
    module = TestModule(name="audit-stop-module", created_by=admin_user.id)
    test_db.add_all([device, module])
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(module)

    items = []
    for index in range(5):
        item = TestItem(
            module_id=module.id,
            name=f"audit-stop-{index}",
            exec_type="adb_shell",
            exec_command="echo audit",
            parameters={},
            compatibility={},
            judgement_type="assertion",
            result_parse={"pass_pattern": "ok"},
            on_failure="stop",
            timeout=30,
            created_by=admin_user.id,
        )
        test_db.add(item)
        items.append(item)
    await test_db.commit()
    for item in items:
        await test_db.refresh(item)

    task = TestTask(
        user_id=admin_user.id,
        device_id=device.id,
        name="audit-stop-task",
        selected_items=[item.id for item in items],
        status="pending",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    mock_adb.execute_shell = AsyncMock(side_effect=[
        ("ok", "", 0),
        ("bad", "", 0),
    ])
    TaskExecutor._running_tasks.clear()
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()
    assert TaskExecutor.start_task(task.id) is True
    running = TaskExecutor._running_tasks[task.id]
    await asyncio.gather(running, return_exceptions=True)

    records = (await test_db.execute(
        select(TestRecord).where(TestRecord.task_id == task.id).order_by(TestRecord.id)
    )).scalars().all()
    await test_db.refresh(task)
    assert [record.status for record in records] == ["pass", "fail", "skip", "skip", "skip"]
    assert task.status == "completed"
    assert task.progress_percent == 100


def test_audit_missing_device_binary_remains_a_required_manifest_entry(tmp_path):
    """删除已声明必需二进制后，需求条目不能随文件一起消失。"""
    module = tmp_path / "demo"
    binary = module / "binaries" / "arm64-v8a" / "tool"
    binary.parent.mkdir(parents=True)
    binary.write_bytes(b"audit")
    (module / "manifest.yaml").write_text(
        "module:\n  name: demo\nitems: []\n", encoding="utf-8"
    )
    before, _ = discover_requirements(tmp_path)
    assert "demo/binaries/arm64-v8a/tool" in before
    binary.unlink()
    after, _ = discover_requirements(tmp_path)
    assert "demo/binaries/arm64-v8a/tool" in after
