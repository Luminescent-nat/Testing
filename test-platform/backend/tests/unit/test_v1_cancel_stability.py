"""task-C1：cancel 状态机条件更新与竞态治理（契约 v1.1）。

背景：RR-V1-REFINAL §3.4 —— `test_cancel_running_task_keeps_cancelled` 偶发
running。根因两条：
1. API 端点与执行器收尾均为无条件 ORM 状态写（last-writer-wins，cancelled 可被
   completed/running 覆盖；ORM 陈旧属性 flush 是隐藏写回后门）；
2. 取消信号可能打断执行器会话上的数据库操作，`_release_device` 在 finally 中抛出的
   非 Cancelled 异常会替换在飞 CancelledError，导致 `_handle_cancel` 不执行，
   最后落库值停留 running。

本文件：
- 两条确定性红用例（先在旧实现上跑红留证，绿后永久回归）；
- 20 连跑 × API 双路径（legacy /cancel 与 /cancellations）；
- 并发 10 取消（legacy 与双路径混发）全部返回、无 500、终态 cancelled。
"""
import asyncio
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select, update

from app.models import Device, TestItem, TestModule, TestRecord, TestTask
from app.services.task_executor import DeviceLock, TaskExecutor
from tests.unit.test_task_executor import _cleanup_executor, _wait_for_record_running


# --------------------------------------------------------------------------- #
# 辅助
# --------------------------------------------------------------------------- #

async def _make_running_task(test_db, admin_user, mock_adb, *, serial, monkeypatch=None):
    """创建 device/module/item/task 并启动执行器，等第一项进入 running（事件钉住）。

    mock execute_shell 在 gate 事件上阻塞（任务钉在 running，直到测试显式 set），
    保证「发取消请求时任务必然仍是 running」的确定性前提；返回
    (task, item, record, running 协程, gate)。调用方负责 cleanup。
    """
    if monkeypatch is not None:
        # 避免后台报告任务跨用例泄漏（本文件用例不校验报告内容）
        monkeypatch.setattr(
            "app.services.task_executor.generate_task_report_files", AsyncMock()
        )

    device = Device(serial_number=serial, status="testing",
                    pc_identifier="test-pc-admin", owner_id=admin_user.id)
    module = TestModule(name=f"CancelStability-{serial}", created_by=admin_user.id)
    test_db.add_all([device, module])
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(module)

    item = TestItem(
        module_id=module.id, name=f"item-{serial}", exec_type="adb_shell",
        exec_command="echo ok", parameters={}, compatibility={},
        judgement_type="assertion", result_parse={"pass_pattern": "ok"},
        timeout=30, created_by=admin_user.id,
    )
    test_db.add(item)
    await test_db.commit()
    await test_db.refresh(item)

    task = TestTask(user_id=admin_user.id, device_id=device.id, name=f"task-{serial}",
                    selected_items=[item.id], status="pending")
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    gate = asyncio.Event()

    async def _shell(*args, **kwargs):
        await gate.wait()
        return ("ok", "", 0)

    mock_adb.execute_shell = _shell

    TaskExecutor._running_tasks.clear()
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()
    assert TaskExecutor.start_task(task.id) is True
    running = TaskExecutor._running_tasks[task.id]
    record = await _wait_for_record_running(test_db, task.id)
    assert record is not None, "执行器未进入测试项执行阶段"
    return task, item, record, running, gate


# --------------------------------------------------------------------------- #
# 红 1：执行器 completed 收尾不得覆盖 cancelled（确定性）
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_red_executor_completed_finalize_must_not_overwrite_cancelled(
    test_db, mock_adb, admin_user, monkeypatch
):
    """API 已条件更新 cancelled 后，执行器正常跑完的 completed 收尾不得改写状态。"""
    task, item, record, running, gate = await _make_running_task(
        test_db, admin_user, mock_adb, serial="cancel-red1", monkeypatch=monkeypatch,
    )
    try:
        # 模拟 cancel 端点条件更新先赢：pending/running → cancelled
        await test_db.execute(
            update(TestTask)
            .where(TestTask.id == task.id, TestTask.status.in_(["pending", "running"]))
            .values(status="cancelled", completed_at=datetime.now(timezone.utc))
        )
        await test_db.commit()

        # 放行执行器：其 completed 收尾在旧实现中无条件写库（红）
        gate.set()
        await asyncio.gather(running, return_exceptions=True)

        await test_db.refresh(task)
        assert task.status == "cancelled", (
            f"执行器收尾覆盖了 cancelled：实际 {task.status}"
        )
    finally:
        gate.set()
        await _cleanup_executor(task.id)


# --------------------------------------------------------------------------- #
# 红 2：收尾释放设备抛异常不得吞掉取消收尾（偶发 running 的确定性根因）
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_red_cancel_persisted_when_release_raises(
    test_db, mock_adb, admin_user, monkeypatch
):
    """`_release_device` 抛非 Cancelled 异常时，取消收尾必须仍然落库 cancelled。"""
    task, item, record, running, gate = await _make_running_task(
        test_db, admin_user, mock_adb, serial="cancel-red2", monkeypatch=monkeypatch,
    )
    try:
        real_release = TaskExecutor._release_device.__func__
        calls = {"n": 0}

        async def flaky_release(db, device, task_id=None):
            calls["n"] += 1
            if calls["n"] == 1:
                # 模拟取消信号打断数据库操作后，收尾释放路径上的异常
                raise RuntimeError("simulated broken session")
            return await real_release(TaskExecutor, db, device, task_id)

        monkeypatch.setattr(TaskExecutor, "_release_device", flaky_release)

        assert TaskExecutor.cancel_task(task.id) is True
        await asyncio.gather(running, return_exceptions=True)

        await test_db.refresh(task)
        assert task.status == "cancelled", (
            f"取消收尾被收尾异常吞掉：实际 {task.status}"
        )
        # 运行中的记录被收尾为中断态
        await test_db.refresh(record)
        assert record.status == "error"
        assert record.fail_reason == "任务被取消"
    finally:
        gate.set()
        await _cleanup_executor(task.id)


# --------------------------------------------------------------------------- #
# 验收：20 连跑 × API 双路径
# --------------------------------------------------------------------------- #

async def _cancel_cycle_via_api(test_db, admin_user, mock_adb, client, token, path, index):
    serial = f"c20-{'legacy' if path == '/cancel' else 'cxl'}-{index}"
    task, item, record, running, gate = await _make_running_task(
        test_db, admin_user, mock_adb, serial=serial,
    )
    try:
        resp = await client.post(
            f"/api/v1/tasks/{task.id}{path}",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp.status_code == 200, (index, resp.status_code, resp.text)
        body = resp.json()
        assert set(body) == {"code", "message", "data"}
        assert body["code"] == 200 and "已取消" in body["message"]

        await asyncio.gather(running, return_exceptions=True)
        await test_db.refresh(task)
        assert task.status == "cancelled", (index, task.status)
        await test_db.refresh(record)
        assert record.status == "error"
        assert record.fail_reason == "任务被取消"
    finally:
        gate.set()
        await _cleanup_executor(task.id)


@pytest.mark.asyncio
async def test_cancel_twenty_consecutive_cycles_legacy_api(
    test_db, mock_adb, admin_user, admin_token, client, monkeypatch
):
    """20 连跑（legacy POST /tasks/{id}/cancel）：每轮取消后终态必须为 cancelled。"""
    monkeypatch.setattr(
        "app.services.task_executor.generate_task_report_files", AsyncMock()
    )
    for index in range(20):
        await _cancel_cycle_via_api(
            test_db, admin_user, mock_adb, client, admin_token, "/cancel", index
        )


@pytest.mark.asyncio
async def test_cancel_twenty_consecutive_cycles_cancellations_api(
    test_db, mock_adb, admin_user, admin_token, client, monkeypatch
):
    """20 连跑（目标路径 POST /tasks/{id}/cancellations）：与 legacy 同一语义。"""
    monkeypatch.setattr(
        "app.services.task_executor.generate_task_report_files", AsyncMock()
    )
    for index in range(20):
        await _cancel_cycle_via_api(
            test_db, admin_user, mock_adb, client, admin_token, "/cancellations", index
        )


# --------------------------------------------------------------------------- #
# 验收：并发 10 取消（全部返回、无 500、终态 cancelled）
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_concurrent_ten_cancels_legacy_no_500(
    test_db, mock_adb, admin_user, admin_token, client, monkeypatch
):
    monkeypatch.setattr(
        "app.services.task_executor.generate_task_report_files", AsyncMock()
    )
    task, item, record, running, gate = await _make_running_task(
        test_db, admin_user, mock_adb, serial="conc-legacy",
    )
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        responses = await asyncio.gather(*[
            client.post(f"/api/v1/tasks/{task.id}/cancel", headers=headers)
            for _ in range(10)
        ])
        for resp in responses:
            assert resp.status_code < 500, (resp.status_code, resp.text)
            assert resp.status_code in (200, 400)
        assert any(r.status_code == 200 for r in responses)

        await asyncio.gather(running, return_exceptions=True)
        await test_db.refresh(task)
        assert task.status == "cancelled"
        await test_db.refresh(record)
        assert record.status == "error"
    finally:
        gate.set()
        await _cleanup_executor(task.id)


@pytest.mark.asyncio
async def test_concurrent_ten_cancels_mixed_paths_no_500(
    test_db, mock_adb, admin_user, admin_token, client, monkeypatch
):
    """并发 10 混发（5×legacy + 5×cancellations）：共用同一业务函数，全部返回无 500。"""
    monkeypatch.setattr(
        "app.services.task_executor.generate_task_report_files", AsyncMock()
    )
    task, item, record, running, gate = await _make_running_task(
        test_db, admin_user, mock_adb, serial="conc-mixed",
    )
    try:
        headers = {"Authorization": f"Bearer {admin_token}"}
        paths = ["/cancel"] * 5 + ["/cancellations"] * 5
        responses = await asyncio.gather(*[
            client.post(f"/api/v1/tasks/{task.id}{path}", headers=headers)
            for path in paths
        ])
        for resp in responses:
            assert resp.status_code < 500, (resp.status_code, resp.text)
            assert resp.status_code in (200, 400)
        assert any(r.status_code == 200 for r in responses)

        await asyncio.gather(running, return_exceptions=True)
        await test_db.refresh(task)
        assert task.status == "cancelled"
        await test_db.refresh(record)
        assert record.status == "error"
    finally:
        gate.set()
        await _cleanup_executor(task.id)


# --------------------------------------------------------------------------- #
# 幂等语义护栏：终态任务取消 → 400 VALIDATION_ERROR（确定性正交用例）
# --------------------------------------------------------------------------- #

async def _make_terminal_task(test_db, admin_user, *, serial, status):
    device = Device(serial_number=serial, status="testing",
                    pc_identifier="test-pc-admin", owner_id=admin_user.id)
    module = TestModule(name=f"Terminal-{serial}", created_by=admin_user.id)
    test_db.add_all([device, module])
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(module)

    item = TestItem(
        module_id=module.id, name=f"item-{serial}", exec_type="adb_shell",
        exec_command="echo ok", parameters={}, compatibility={},
        judgement_type="assertion", result_parse={"pass_pattern": "ok"},
        timeout=30, created_by=admin_user.id,
    )
    test_db.add(item)
    await test_db.commit()
    await test_db.refresh(item)

    task = TestTask(user_id=admin_user.id, device_id=device.id, name=f"task-{serial}",
                    selected_items=[item.id], status=status,
                    completed_at=datetime.now(timezone.utc))
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)
    return task


@pytest.mark.asyncio
async def test_cancel_terminal_task_returns_400_validation_error(
    test_db, admin_user, admin_token, client
):
    """已 completed / cancelled 的任务再取消：400 VALIDATION_ERROR，不覆盖终态。"""
    headers = {"Authorization": f"Bearer {admin_token}"}
    for status_value, path in (
        ("completed", "/cancel"),
        ("cancelled", "/cancellations"),
    ):
        task = await _make_terminal_task(
            test_db, admin_user, serial=f"terminal-{status_value}-{path.strip('/')}",
            status=status_value,
        )
        resp = await client.post(
            f"/api/v1/tasks/{task.id}{path}", headers=headers
        )
        assert resp.status_code == 400, (status_value, resp.status_code, resp.text)
        body = resp.json()
        assert body["code"] == "VALIDATION_ERROR", body
        await test_db.refresh(task)
        assert task.status == status_value
