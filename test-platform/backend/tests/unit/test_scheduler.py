"""任务调度器单元测试。"""
from datetime import datetime, timedelta, timezone

import pytest

from app.main import INTERRUPTED_MESSAGE, recover_interrupted_state
from app.models import Device, TestTask
from app.services import scheduler
from app.services.scheduler import compute_next_run, trigger_due_tasks
from app.services.task_executor import TaskExecutor


@pytest.fixture
def fake_start_task(monkeypatch):
    """拦截 TaskExecutor.start_task，避免真实启动后台执行。"""
    started = []
    monkeypatch.setattr(TaskExecutor, "start_task", lambda task_id: started.append(task_id) or True)
    return started


async def _make_device(test_db, admin_user, serial="sched-serial"):
    device = Device(
        serial_number=serial,
        status="online",
        pc_identifier="test-pc-admin",
        owner_id=admin_user.id,
    )
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)
    return device


def _make_task(admin_user, device, schedule_type, scheduled_time, next_run_at, name="sched-task"):
    return TestTask(
        user_id=admin_user.id,
        device_id=device.id,
        name=name,
        selected_items=[],
        status="pending",
        schedule_type=schedule_type,
        scheduled_time=scheduled_time,
        next_run_at=next_run_at,
    )


@pytest.mark.asyncio
async def test_once_task_triggered_when_due(test_db, admin_user, fake_start_task):
    """TC-SCHED-001: once 任务到期被调度器启动，触发后清除 next_run_at。"""
    device = await _make_device(test_db, admin_user)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    task = _make_task(admin_user, device, "once", "2099-01-01 02:00", past)
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    triggered = await trigger_due_tasks(test_db)

    assert triggered == [task.id]
    assert fake_start_task == [task.id]
    await test_db.refresh(task)
    assert task.next_run_at is None
    assert task.status == "pending"  # 状态由执行器推进，调度器不改


@pytest.mark.asyncio
async def test_daily_task_rolls_to_next_day(test_db, admin_user, fake_start_task):
    """TC-SCHED-002: daily 任务触发后 next_run_at 滚到下一天同一时刻。"""
    device = await _make_device(test_db, admin_user)
    past = datetime.now(timezone.utc) - timedelta(minutes=1)
    task = _make_task(admin_user, device, "daily", "02:00", past)
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    triggered = await trigger_due_tasks(test_db)

    assert triggered == [task.id]
    assert fake_start_task == [task.id]
    await test_db.refresh(task)
    assert task.next_run_at is not None
    # 下次触发时间在将来，且本地时刻为 02:00
    next_run = task.next_run_at
    if next_run.tzinfo is None:
        next_run = next_run.replace(tzinfo=timezone.utc)
    assert next_run > datetime.now(timezone.utc)
    local_next = next_run.astimezone()
    assert (local_next.hour, local_next.minute) == (2, 0)


@pytest.mark.asyncio
async def test_task_not_triggered_before_due(test_db, admin_user, fake_start_task):
    """TC-SCHED-003: 未到期的调度任务不触发，next_run_at 保持不变。"""
    device = await _make_device(test_db, admin_user)
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    task = _make_task(admin_user, device, "once", "2099-01-01 02:00", future)
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    triggered = await trigger_due_tasks(test_db)

    assert triggered == []
    assert fake_start_task == []
    await test_db.refresh(task)
    assert task.next_run_at is not None
    assert task.status == "pending"


@pytest.mark.asyncio
async def test_recover_keeps_scheduled_pending_task(test_db, admin_user):
    """TC-SCHED-004: 启动恢复不误杀未触发的调度任务（pending + next_run_at）。"""
    device = await _make_device(test_db, admin_user)
    future = datetime.now(timezone.utc) + timedelta(hours=2)
    scheduled_task = _make_task(admin_user, device, "daily", "02:00", future, name="scheduled")
    queued_task = _make_task(admin_user, device, "immediate", None, None, name="queued")
    test_db.add_all([scheduled_task, queued_task])
    await test_db.commit()
    await test_db.refresh(scheduled_task)
    await test_db.refresh(queued_task)

    await recover_interrupted_state(test_db)

    # 调度任务保留 pending 等待触发
    await test_db.refresh(scheduled_task)
    assert scheduled_task.status == "pending"
    assert scheduled_task.next_run_at is not None

    # 普通 pending 任务（排队执行被中断）仍按中断处理
    await test_db.refresh(queued_task)
    assert queued_task.status == "failed"
    assert queued_task.error_message == INTERRUPTED_MESSAGE


def test_compute_next_run_once():
    """once：本地时间字符串转换为 UTC。"""
    now = datetime.now(timezone.utc)
    result = compute_next_run("once", "2099-06-01 08:30", now)
    assert result.tzinfo is not None
    local = result.astimezone()
    assert (local.year, local.month, local.day, local.hour, local.minute) == (2099, 6, 1, 8, 30)


def test_compute_next_run_daily_past_time_rolls_tomorrow():
    """daily：当天时刻已过时顺延到次日。"""
    now = datetime.now(timezone.utc)
    local_now = now.astimezone()
    past_hour = (local_now.hour - 1) % 24
    result = compute_next_run("daily", f"{past_hour:02d}:00", now)
    local_result = result.astimezone()
    assert local_result.date() > local_now.date() or local_result.hour != local_now.hour
    assert result > now


def test_compute_next_run_invalid_format():
    """格式非法抛 ValueError，由 API 层转 400。"""
    with pytest.raises(ValueError):
        compute_next_run("once", "not-a-time")
    with pytest.raises(ValueError):
        compute_next_run("daily", "25:99")
