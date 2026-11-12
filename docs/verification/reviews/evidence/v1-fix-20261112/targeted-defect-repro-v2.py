"""V1 定向反例永久回归基线 v2（R6 基线语义更新版）。

来源与沿革：
- v1 基线 = docs/verification/reviews/evidence/v1-readiness-20261112/targeted-defect-repro.py
  （审计原文件，**保持原样不修改**；其 R6 断言"文件存在即成为必需项"基于被 V1-08 废除的
  glob 语义，与新显式声明契约前提冲突）。
- 本 v2 基线经 Lead 裁决（2026-11-12，待用户最终确认）更新 R6：
  R6a = 显式 tools 声明 + 删除已声明文件 → 条目仍在且启动校验失败
        （等价于 tests/unit/test_v1_tool_manifest.py::test_deleting_declared_device_binary_keeps_requirement_and_fails_startup）；
  R6b = 无 tools 声明的模块（含 host/二进制）→ declaration_gaps 致命（启动失败）。
  R1～R5 与 v1 逐字一致（原样保留）。
- 运行方式（不触碰业务 tests/ 目录）：workdir=test-platform/backend，
  PYTHONPATH=docs/verification/reviews/evidence/v1-fix-20261112
  PYTEST_PLUGINS=_repro_plugin（该 shim 把 backend/tests/conftest.py 的 fixtures 注册为插件），
  python -m pytest <本文件> -q -W error::pytest.PytestUnraisableExceptionWarning -rA
"""
import asyncio

import pytest
from sqlalchemy import select

from app.models import Device, TestItem, TestModule, TestRecord, TestTask
from app.services.judgement_engine import JudgementEngine, RuleBasedJudger
from app.services.task_executor import DeviceLock, TaskExecutor
from app.services.tool_manifest import (
    ToolManifestError,
    assert_required_tools,
    discover_requirements,
    validate_tools,
)


@pytest.mark.asyncio
async def test_audit_normal_user_cannot_start_task_on_other_users_device(
    client, normal_token, admin_user, sample_device, sample_item, monkeypatch
):
    """R1（V1-01）：普通用户使用他人且异 PC 设备创建任务必须为 403，且不得写任务。"""
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
    """R2（V1-04）：相同幂等键和请求体重放不得创建第二个任务；两次 201。"""
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
    """R3（V1-02）：conditional_rules=[] 是非法根结构，不得经 pass_pattern 变成 pass。"""
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
    """R4（V1-02）：零目标不是合法 approx_ratio 配置，任意实际值都不得直接判通过。"""
    ok, _ = RuleBasedJudger()._compare(100, "approx_ratio", 0, "0%")
    assert ok is False


@pytest.mark.asyncio
async def test_audit_stop_on_failure_completes_remaining_items_as_skip(
    test_db, mock_adb, admin_user
):
    """R5（V1-03）：5 项中第 2 项 stop+fail 后，剩余 3 项必须补 skip。"""
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


# ---- R6（V1-08，基线语义更新版：显式声明契约）----


def _make_declared_module(root, sha256_hex):
    module = root / "demo"
    binary = module / "binaries" / "arm64-v8a" / "tool"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"audit")
    (module / "manifest.yaml").write_text(
        "module:\n  name: demo\nitems: []\n"
        "tools:\n  device:\n"
        "    - path: demo/binaries/arm64-v8a/tool\n"
        "      abi: arm64-v8a\n"
        "      version: '1.0'\n"
        f"      sha256: \"{sha256_hex}\"\n",
        encoding="utf-8",
    )
    return binary


def test_audit_missing_declared_device_binary_remains_required_and_blocks_startup(
    tmp_path,
):
    """R6a（V1-08 显式声明契约）：删除【已声明】必需二进制后，需求条目仍存在且启动校验失败。"""
    import hashlib

    binary = _make_declared_module(tmp_path, hashlib.sha256(b"audit").hexdigest())
    before, _ = discover_requirements(tmp_path)
    assert "demo/binaries/arm64-v8a/tool" in before
    binary.unlink()
    after, _ = discover_requirements(tmp_path)
    assert "demo/binaries/arm64-v8a/tool" in after
    with pytest.raises(ToolManifestError) as excinfo:
        assert_required_tools(tmp_path)
    assert "demo/binaries/arm64-v8a/tool" in str(excinfo.value)


def test_audit_undeclared_module_with_binaries_is_declaration_gap(tmp_path):
    """R6b（V1-08 显式声明契约）：无 tools 声明但目录含 host/二进制的模块 → declaration_gaps 致命。"""
    module = tmp_path / "demo"
    binary = module / "binaries" / "arm64-v8a" / "tool"
    binary.parent.mkdir(parents=True, exist_ok=True)
    binary.write_bytes(b"audit")
    (module / "manifest.yaml").write_text(
        "module:\n  name: demo\nitems: []\n", encoding="utf-8"
    )
    # 未声明文件不再自动成为必需项（废除 glob 语义）
    requirements, _ = discover_requirements(tmp_path)
    assert "demo/binaries/arm64-v8a/tool" not in requirements
    # 但该模块会被 declaration_gaps 判为致命（启动失败），不会被静默放过
    result = validate_tools(tmp_path)
    assert result["declaration_gaps"], result
    with pytest.raises(ToolManifestError) as excinfo:
        assert_required_tools(tmp_path)
    assert "未显式声明" in str(excinfo.value)
