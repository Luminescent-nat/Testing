"""服务启动时中断状态恢复的单元测试。"""
import pytest

from app.main import INTERRUPTED_MESSAGE, recover_interrupted_state
from app.models import Device, TestItem, TestModule, TestRecord, TestTask


@pytest.mark.asyncio
async def test_recover_interrupted_state(test_db, admin_user):
    """TC-RECOVERY-001: 启动恢复将中断任务标 failed、中断记录标 error、testing 设备恢复 online。"""
    device_testing = Device(
        serial_number="recovery-testing",
        status="testing",
        pc_identifier="test-pc-admin",
        owner_id=admin_user.id,
    )
    device_offline = Device(
        serial_number="recovery-offline",
        status="offline",
        pc_identifier="test-pc-admin",
        owner_id=admin_user.id,
    )
    module = TestModule(name="RecoveryModule", created_by=admin_user.id)
    test_db.add_all([device_testing, device_offline, module])
    await test_db.commit()
    for obj in (device_testing, device_offline, module):
        await test_db.refresh(obj)

    item = TestItem(
        module_id=module.id,
        name="Recovery Item",
        exec_type="adb_shell",
        exec_command="echo ok",
        parameters={},
        compatibility={},
        created_by=admin_user.id,
    )
    test_db.add(item)
    await test_db.commit()
    await test_db.refresh(item)

    task_running = TestTask(
        user_id=admin_user.id,
        device_id=device_testing.id,
        name="running-task",
        selected_items=[item.id],
        status="running",
    )
    task_pending = TestTask(
        user_id=admin_user.id,
        device_id=device_testing.id,
        name="pending-task",
        selected_items=[item.id],
        status="pending",
    )
    task_completed = TestTask(
        user_id=admin_user.id,
        device_id=device_testing.id,
        name="completed-task",
        selected_items=[item.id],
        status="completed",
    )
    test_db.add_all([task_running, task_pending, task_completed])
    await test_db.commit()
    for t in (task_running, task_pending, task_completed):
        await test_db.refresh(t)

    record_running = TestRecord(task_id=task_running.id, item_id=item.id, status="running")
    record_pass = TestRecord(task_id=task_running.id, item_id=item.id, status="pass")
    test_db.add_all([record_running, record_pass])
    await test_db.commit()
    await test_db.refresh(record_running)
    await test_db.refresh(record_pass)

    await recover_interrupted_state(test_db)

    # running / pending 任务 → failed，并注明中断原因
    await test_db.refresh(task_running)
    assert task_running.status == "failed"
    assert task_running.error_message == INTERRUPTED_MESSAGE
    assert task_running.completed_at is not None

    await test_db.refresh(task_pending)
    assert task_pending.status == "failed"
    assert task_pending.error_message == INTERRUPTED_MESSAGE

    # 已完成任务不受影响
    await test_db.refresh(task_completed)
    assert task_completed.status == "completed"

    # 未完成的记录 → error，已完成的记录不动
    await test_db.refresh(record_running)
    assert record_running.status == "error"
    assert record_running.fail_reason == INTERRUPTED_MESSAGE

    await test_db.refresh(record_pass)
    assert record_pass.status == "pass"

    # testing 设备恢复 online；其他状态设备不动
    await test_db.refresh(device_testing)
    assert device_testing.status == "online"

    await test_db.refresh(device_offline)
    assert device_offline.status == "offline"
