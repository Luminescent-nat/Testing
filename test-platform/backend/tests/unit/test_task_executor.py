"""任务执行器与设备锁单元测试。"""
import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models import Device, TestItem, TestModule, TestRecord, TestTask
from app.services.task_executor import DeviceLock, TaskExecutor


@pytest.mark.asyncio
async def test_device_lock_acquire_and_release():
    """TC-EXEC-001: 设备锁可正常获取与释放，占用时第二个获取排队等待。"""
    await DeviceLock.acquire("serial-1", 1)
    assert DeviceLock.get_holder("serial-1") == 1

    # 同一设备的第二个获取将排队阻塞，直到持有者释放
    waiter = asyncio.create_task(DeviceLock.acquire("serial-1", 2))
    await asyncio.sleep(0.05)
    assert not waiter.done()
    assert DeviceLock.get_holder("serial-1") == 1

    DeviceLock.release("serial-1")
    await waiter
    assert DeviceLock.get_holder("serial-1") == 2

    DeviceLock.release("serial-1")
    assert DeviceLock.get_holder("serial-1") is None
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()


@pytest.mark.asyncio
async def test_device_lock_release_unknown():
    """TC-EXEC-002: 释放未加锁设备不报错。"""
    DeviceLock.release("unknown-serial")
    assert DeviceLock.get_holder("unknown-serial") is None


@pytest.mark.asyncio
async def test_start_task_duplicate():
    """TC-EXEC-003: 同一任务重复启动应被拒绝。"""
    # 使用一个不存在的数据库任务 ID，让后台任务快速失败并清理
    TaskExecutor._running_tasks.clear()
    assert TaskExecutor.start_task(999999) is True
    # 同一任务 ID 再次启动应失败
    assert TaskExecutor.start_task(999999) is False
    # 等待任务结束或取消，避免污染其他测试
    running = TaskExecutor._running_tasks.get(999999)
    if running:
        running.cancel()
        try:
            await running
        except (Exception, BaseException):
            pass
    TaskExecutor._running_tasks.clear()
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()


async def _wait_for_record_running(test_db, task_id, timeout=5.0):
    """轮询等待执行器创建 running 状态的测试记录。"""
    import time
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        result = await test_db.execute(
            select(TestRecord).where(TestRecord.task_id == task_id)
        )
        records = result.scalars().all()
        if any(r.status == "running" for r in records):
            return records[0]
        await asyncio.sleep(0.05)
    return None


@pytest.mark.asyncio
async def test_cancel_running_task_keeps_cancelled(test_db, mock_adb, admin_user):
    """TC-EXEC-004: 取消运行中任务后状态保持 cancelled，不被覆盖为 completed。"""
    # 让 shell 执行一直挂起，模拟长时间运行的测试项
    async def _hang(*args, **kwargs):
        await asyncio.sleep(60)
        return "", "", 0
    mock_adb.execute_shell = _hang

    device = Device(
        serial_number="cancel-test-serial",
        status="testing",
        pc_identifier="test-pc-admin",
        owner_id=admin_user.id,
    )
    module = TestModule(name="CancelModule", created_by=admin_user.id)
    test_db.add_all([device, module])
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(module)

    item = TestItem(
        module_id=module.id,
        name="Long Item",
        exec_type="adb_shell",
        exec_command="sleep 60",
        parameters={},
        compatibility={},
        judgement_type="assertion",
        result_parse={"pass_pattern": "ok"},
        timeout=300,
        created_by=admin_user.id,
    )
    test_db.add(item)
    await test_db.commit()
    await test_db.refresh(item)

    task = TestTask(
        user_id=admin_user.id,
        device_id=device.id,
        name="cancel-test",
        selected_items=[item.id],
        status="pending",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    TaskExecutor._running_tasks.clear()
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()
    try:
        assert TaskExecutor.start_task(task.id) is True
        running = TaskExecutor._running_tasks[task.id]

        # 等待执行器进入测试项执行阶段
        record = await _wait_for_record_running(test_db, task.id)
        assert record is not None, "执行器未进入测试项执行阶段"

        # 取消并等待协程收尾完成
        assert TaskExecutor.cancel_task(task.id) is True
        await asyncio.gather(running, return_exceptions=True)

        # 任务状态保持 cancelled，不被后台协程覆盖回 completed
        await test_db.refresh(task)
        assert task.status == "cancelled"

        # 正在执行的记录被收尾为中断状态
        await test_db.refresh(record)
        assert record.status == "error"
        assert record.fail_reason == "任务被取消"

        # 设备被释放回 online（mock 探活返回在线）
        await test_db.refresh(device)
        assert device.status == "online"
    finally:
        leftover = TaskExecutor._running_tasks.get(task.id)
        if leftover and not leftover.done():
            leftover.cancel()
            await asyncio.gather(leftover, return_exceptions=True)
        TaskExecutor._running_tasks.clear()
        DeviceLock._locks.clear()
        DeviceLock._holders.clear()


@pytest.mark.asyncio
async def test_handle_cancel_missing_task_no_error(test_db):
    """TC-EXEC-005: 取消/失败收尾不存在的任务时不抛 AttributeError。"""
    # task_id 不存在，应安静返回而不是 AttributeError
    await TaskExecutor._handle_cancel(999998, test_db)
    await TaskExecutor._handle_failure(999998, test_db, "boom")


async def _run_single_item_task(test_db, admin_user, *, serial, item_kwargs):
    """创建设备/模块/测试项/任务并同步跑完，返回 (task, records)。"""
    device = Device(
        serial_number=serial,
        status="testing",
        pc_identifier="test-pc-admin",
        owner_id=admin_user.id,
    )
    module = TestModule(name=f"Module-{serial}", created_by=admin_user.id)
    test_db.add_all([device, module])
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(module)

    item = TestItem(
        module_id=module.id,
        name=f"Item-{serial}",
        exec_type="adb_shell",
        exec_command="echo ok",
        parameters={},
        compatibility={},
        judgement_type="assertion",
        created_by=admin_user.id,
        **item_kwargs,
    )
    test_db.add(item)
    await test_db.commit()
    await test_db.refresh(item)

    task = TestTask(
        user_id=admin_user.id,
        device_id=device.id,
        name=f"task-{serial}",
        selected_items=[item.id],
        status="pending",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    TaskExecutor._running_tasks.clear()
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()
    try:
        assert TaskExecutor.start_task(task.id) is True
        running = TaskExecutor._running_tasks[task.id]
        await asyncio.gather(running, return_exceptions=True)

        result = await test_db.execute(
            select(TestRecord).where(TestRecord.task_id == task.id)
        )
        return task, result.scalars().all()
    finally:
        leftover = TaskExecutor._running_tasks.get(task.id)
        if leftover and not leftover.done():
            leftover.cancel()
            await asyncio.gather(leftover, return_exceptions=True)
        TaskExecutor._running_tasks.clear()
        DeviceLock._locks.clear()
        DeviceLock._holders.clear()


@pytest.mark.asyncio
async def test_retry_count_retries_failed_item_and_keeps_output(test_db, mock_adb, admin_user):
    """TC-EXEC-006: retry_count 生效，失败自动重试且每次尝试输出都保留。"""
    # 前两次失败、第三次通过
    mock_adb.execute_shell = AsyncMock(side_effect=[
        ("bad", "", 1),
        ("bad", "", 1),
        ("ok", "", 0),
    ])

    task, records = await _run_single_item_task(
        test_db, admin_user,
        serial="retry-test-serial",
        item_kwargs={
            "result_parse": {"fail_pattern": "bad", "pass_pattern": "ok"},
            "timeout": 30,
            "retry_count": 2,
        },
    )

    # 重试不产生新的 TestRecord
    assert len(records) == 1
    record = records[0]
    # 最终状态以最后一次执行为准
    assert record.status == "pass"
    # 每次尝试的输出都保留，带重试分隔标记
    assert "=== 重试 1/2 ===" in record.output
    assert "=== 重试 2/2 ===" in record.output
    assert mock_adb.execute_shell.call_count == 3

    await test_db.refresh(task)
    assert task.status == "completed"


@pytest.mark.asyncio
async def test_retry_count_exhausted_keeps_failed(test_db, mock_adb, admin_user):
    """TC-EXEC-007: 重试次数用完后仍失败，最终状态为失败。"""
    mock_adb.execute_shell = AsyncMock(return_value=("bad", "", 1))

    task, records = await _run_single_item_task(
        test_db, admin_user,
        serial="retry-exhaust-serial",
        item_kwargs={
            "result_parse": {"fail_pattern": "bad", "pass_pattern": "ok"},
            "timeout": 30,
            "retry_count": 1,
        },
    )

    assert len(records) == 1
    assert records[0].status == "fail"
    assert "=== 重试 1/1 ===" in records[0].output
    assert mock_adb.execute_shell.call_count == 2


@pytest.mark.asyncio
async def test_timeout_record_marked_as_timeout(test_db, mock_adb, admin_user):
    """TC-EXEC-008: 执行超时的记录状态为 timeout。"""
    # 模拟 adb 子进程等待超时
    mock_adb.execute_shell = AsyncMock(
        return_value=("", "Timeout after 30 seconds", -1)
    )

    task, records = await _run_single_item_task(
        test_db, admin_user,
        serial="timeout-test-serial",
        item_kwargs={
            "result_parse": {"pass_pattern": "ok"},
            "timeout": 30,
        },
    )

    assert len(records) == 1
    assert records[0].status == "timeout"
    # 超时算未通过：任务跑完但结果应为 failed
    await test_db.refresh(task)
    assert task.status == "completed"


async def _make_task(test_db, admin_user, device, item, name):
    """创建 pending 状态任务。"""
    task = TestTask(
        user_id=admin_user.id,
        device_id=device.id,
        name=name,
        selected_items=[item.id],
        status="pending",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)
    return task


async def _make_device_module_item(test_db, admin_user, serial, *, item_kwargs=None):
    """创建 testing 状态设备 + 模块 + 单项测试项。"""
    device = Device(
        serial_number=serial,
        status="testing",
        pc_identifier="test-pc-admin",
        owner_id=admin_user.id,
    )
    module = TestModule(name=f"QueueModule-{serial}", created_by=admin_user.id)
    test_db.add_all([device, module])
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(module)

    item = TestItem(
        module_id=module.id,
        name=f"QueueItem-{serial}",
        exec_type="adb_shell",
        exec_command="echo ok",
        parameters={},
        compatibility={},
        judgement_type="assertion",
        created_by=admin_user.id,
        **(item_kwargs or {"result_parse": {"pass_pattern": "ok"}, "timeout": 30}),
    )
    test_db.add(item)
    await test_db.commit()
    await test_db.refresh(item)
    return device, item


async def _cleanup_executor(*task_ids):
    """取消残留后台协程并清理执行器/锁状态。"""
    for tid in task_ids:
        leftover = TaskExecutor._running_tasks.get(tid)
        if leftover and not leftover.done():
            leftover.cancel()
            await asyncio.gather(leftover, return_exceptions=True)
    TaskExecutor._running_tasks.clear()
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()


@pytest.mark.asyncio
async def test_queued_task_runs_after_first_completes(test_db, mock_adb, admin_user):
    """TC-EXEC-009: 设备被占用时第二个任务排队等待，第一个完成后自动按 FIFO 执行。"""
    gate = asyncio.Event()

    async def _shell(*args, **kwargs):
        await gate.wait()
        return ("ok", "", 0)
    mock_adb.execute_shell = _shell

    device, item = await _make_device_module_item(test_db, admin_user, "queue-serial")
    task1 = await _make_task(test_db, admin_user, device, item, "queue-task-1")
    task2 = await _make_task(test_db, admin_user, device, item, "queue-task-2")

    await _cleanup_executor()
    try:
        assert TaskExecutor.start_task(task1.id) is True
        running1 = TaskExecutor._running_tasks[task1.id]

        # 等 task1 持锁进入测试项执行阶段（shell 阻塞在 gate 上）
        record1 = await _wait_for_record_running(test_db, task1.id)
        assert record1 is not None, "task1 未进入测试项执行阶段"

        # 启动 task2：设备被占用，应排队保持 pending，不直接 failed
        assert TaskExecutor.start_task(task2.id) is True
        running2 = TaskExecutor._running_tasks[task2.id]
        await asyncio.sleep(0.2)
        await test_db.refresh(task2)
        assert task2.status == "pending"
        assert DeviceLock.get_holder(device.serial_number) == task1.id

        # 放行 task1，两个任务应依次完成
        gate.set()
        await asyncio.gather(running1, running2, return_exceptions=True)

        await test_db.refresh(task1)
        await test_db.refresh(task2)
        assert task1.status == "completed"
        assert task2.status == "completed"
        # FIFO：task2 在 task1 完成后才开始执行
        assert task2.started_at >= task1.completed_at

        result = await test_db.execute(
            select(TestRecord).where(TestRecord.task_id == task2.id)
        )
        records2 = result.scalars().all()
        assert len(records2) == 1
        assert records2[0].status == "pass"
    finally:
        await _cleanup_executor(task1.id, task2.id)


@pytest.mark.asyncio
async def test_queued_task_cancellable(test_db, mock_adb, admin_user):
    """TC-EXEC-010: 排队中的任务可取消，状态 cancelled、不执行、不释放他人锁。"""
    gate = asyncio.Event()

    async def _shell(*args, **kwargs):
        await gate.wait()
        return ("ok", "", 0)
    mock_adb.execute_shell = _shell

    device, item = await _make_device_module_item(test_db, admin_user, "queue-cancel-serial")
    task1 = await _make_task(test_db, admin_user, device, item, "cancel-queue-1")
    task2 = await _make_task(test_db, admin_user, device, item, "cancel-queue-2")

    await _cleanup_executor()
    try:
        assert TaskExecutor.start_task(task1.id) is True
        running1 = TaskExecutor._running_tasks[task1.id]
        record1 = await _wait_for_record_running(test_db, task1.id)
        assert record1 is not None, "task1 未进入测试项执行阶段"

        assert TaskExecutor.start_task(task2.id) is True
        running2 = TaskExecutor._running_tasks[task2.id]
        await asyncio.sleep(0.2)
        await test_db.refresh(task2)
        assert task2.status == "pending"

        # 取消排队中的 task2
        assert TaskExecutor.cancel_task(task2.id) is True
        await asyncio.gather(running2, return_exceptions=True)

        await test_db.refresh(task2)
        assert task2.status == "cancelled"
        # 未执行：不产生任何测试记录
        result = await test_db.execute(
            select(TestRecord).where(TestRecord.task_id == task2.id)
        )
        assert result.scalars().all() == []
        # 不误放 task1 持有的锁
        assert DeviceLock.get_holder(device.serial_number) == task1.id

        # task1 放行后正常完成，设备由 task1 的收尾释放回 online
        gate.set()
        await asyncio.gather(running1, return_exceptions=True)
        await test_db.refresh(task1)
        assert task1.status == "completed"
        await test_db.refresh(device)
        assert device.status == "online"
    finally:
        await _cleanup_executor(task1.id, task2.id)


@pytest.mark.asyncio
async def test_device_offline_mid_run_fails_fast(test_db, mock_adb, admin_user):
    """TC-EXEC-011: 执行中设备掉线，剩余项标记 error"设备离线"，任务 failed，设备保持 offline。"""
    state = {"online": True}

    async def _is_online(serial, timeout=None):
        return state["online"]
    mock_adb.is_device_online = _is_online

    async def _shell(*args, **kwargs):
        # 第一项执行后设备掉线
        state["online"] = False
        return ("ok", "", 0)
    mock_adb.execute_shell = AsyncMock(side_effect=_shell)

    device = Device(
        serial_number="offline-mid-serial",
        status="testing",
        pc_identifier="test-pc-admin",
        owner_id=admin_user.id,
    )
    module = TestModule(name="OfflineMidModule", created_by=admin_user.id)
    test_db.add_all([device, module])
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(module)

    items = []
    for i in range(3):
        item = TestItem(
            module_id=module.id,
            name=f"OfflineItem-{i}",
            exec_type="adb_shell",
            exec_command="echo ok",
            parameters={},
            compatibility={},
            judgement_type="assertion",
            result_parse={"pass_pattern": "ok"},
            timeout=30,
            retry_count=2,  # 设备离线不进入重试，retry_count 不应生效
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
        name="offline-mid-task",
        selected_items=[item.id for item in items],
        status="pending",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    await _cleanup_executor()
    try:
        assert TaskExecutor.start_task(task.id) is True
        running = TaskExecutor._running_tasks[task.id]
        await asyncio.gather(running, return_exceptions=True)

        result = await test_db.execute(
            select(TestRecord).where(TestRecord.task_id == task.id)
        )
        records = result.scalars().all()
        # 第一项 pass；第二项探活失败，当前项及剩余项均 error"设备离线"
        assert len(records) == 3
        assert records[0].status == "pass"
        for record in records[1:]:
            assert record.status == "error"
            assert "设备离线" in record.fail_reason or "离线" in record.fail_reason
        # shell 只执行了一次（不重试、不继续执行剩余项）
        assert mock_adb.execute_shell.call_count == 1

        # 任务按失败收尾
        await test_db.refresh(task)
        assert task.status == "failed"
        assert "离线" in task.error_message

        # 设备保持 offline，不被误置 online
        await test_db.refresh(device)
        assert device.status == "offline"
    finally:
        await _cleanup_executor(task.id)
