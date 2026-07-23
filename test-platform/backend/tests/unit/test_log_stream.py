"""日志实时流与落盘：execute_shell 流式回调、任务执行日志文件、output 截断、日志下载 API。"""
import asyncio
import os
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import Device, TestItem, TestModule, TestRecord, TestTask
from app.services.device import ADBService
from app.services.task_executor import (
    OUTPUT_MAX_LENGTH,
    DeviceLock,
    TaskExecutor,
    _truncate_output,
)


class FakeStreamProcess:
    """模拟一个 stdout/stderr 已有数据的子进程。"""

    def __init__(self, stdout_chunks, stderr_chunks, returncode=0):
        self.pid = 4321
        self.returncode = returncode
        self.terminated = False
        self.killed = False
        self.stdout = asyncio.StreamReader()
        self.stderr = asyncio.StreamReader()
        for chunk in stdout_chunks:
            self.stdout.feed_data(chunk)
        self.stdout.feed_eof()
        for chunk in stderr_chunks:
            self.stderr.feed_data(chunk)
        self.stderr.feed_eof()

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    async def wait(self):
        return self.returncode

    async def communicate(self):
        return b"", b""


@pytest.fixture
def fake_stream_process(monkeypatch):
    """替换 create_subprocess_exec，返回带预置输出流的假进程。"""
    process = FakeStreamProcess([b"line1\n", b"line2\n"], [b"err1\n"])

    async def fake_create_subprocess_exec(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    return process


@pytest.mark.asyncio
async def test_execute_shell_streams_lines_with_sync_callback(fake_stream_process):
    """TC-LOG-001: execute_shell 带同步回调时逐行回调，且返回值结构不变。"""
    lines = []
    adb = ADBService()
    stdout, stderr, returncode = await adb.execute_shell(
        "serial-1", "cmd", timeout=5, on_output=lines.append
    )

    assert returncode == 0
    # 累积完整输出，与 communicate 路径返回值结构一致
    assert stdout == "line1\nline2\n"
    assert stderr == "err1\n"
    # stdout/stderr 每行都回调过（两流各自有序，合并顺序不保证）
    assert sorted(lines) == sorted(["line1\n", "line2\n", "err1\n"])


@pytest.mark.asyncio
async def test_execute_shell_streams_lines_with_async_callback(fake_stream_process):
    """TC-LOG-002: execute_shell 支持异步回调。"""
    lines = []

    async def on_output(line):
        await asyncio.sleep(0)
        lines.append(line)

    adb = ADBService()
    stdout, stderr, returncode = await adb.execute_shell(
        "serial-1", "cmd", timeout=5, on_output=on_output
    )

    assert returncode == 0
    assert stdout == "line1\nline2\n"
    assert stderr == "err1\n"
    assert sorted(lines) == sorted(["line1\n", "line2\n", "err1\n"])


async def _run_single_item_task(test_db, admin_user, *, serial, item_kwargs):
    """创建设备/模块/测试项/任务并同步跑完，返回 (task, records)。"""
    device = Device(
        serial_number=serial,
        status="testing",
        pc_identifier="test-pc-admin",
        owner_id=admin_user.id,
    )
    module = TestModule(name=f"LogModule-{serial}", created_by=admin_user.id)
    test_db.add_all([device, module])
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(module)

    item = TestItem(
        module_id=module.id,
        name=f"LogItem-{serial}",
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
        name=f"log-task-{serial}",
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
async def test_task_execution_writes_log_file(test_db, mock_adb, admin_user, monkeypatch, tmp_path):
    """TC-LOG-003: 任务执行后 log_file_path 已赋值，日志文件存在且包含输出。"""
    monkeypatch.setattr(get_settings(), "LOGS_PATH", str(tmp_path))

    async def _shell(serial, command, timeout=300, on_output=None):
        if on_output is not None:
            await on_output("mock output line\n")
        return ("mock output line", "", 0)

    mock_adb.execute_shell = AsyncMock(side_effect=_shell)

    task, records = await _run_single_item_task(
        test_db, admin_user,
        serial="log-file-serial",
        item_kwargs={"result_parse": {"pass_pattern": "mock"}, "timeout": 30},
    )

    assert len(records) == 1
    record = records[0]
    assert record.status == "pass"
    assert record.log_file_path == f"task_{task.id}/record_{record.id}.log"

    log_path = tmp_path / record.log_file_path
    assert log_path.is_file()
    content = log_path.read_text(encoding="utf-8")
    assert "mock output line" in content


@pytest.mark.asyncio
async def test_record_output_truncated_when_too_long(test_db, mock_adb, admin_user, monkeypatch, tmp_path):
    """TC-LOG-004: output 超长时落库截断（保留尾部并标注），完整内容在日志文件。"""
    monkeypatch.setattr(get_settings(), "LOGS_PATH", str(tmp_path))

    big_output = "x" * (OUTPUT_MAX_LENGTH + 10000)
    # mock 不调用 on_output，执行器应兜底把完整输出写入日志文件
    mock_adb.execute_shell = AsyncMock(return_value=(big_output, "", 0))

    task, records = await _run_single_item_task(
        test_db, admin_user,
        serial="log-truncate-serial",
        item_kwargs={"result_parse": {"pass_pattern": "x"}, "timeout": 30},
    )

    assert len(records) == 1
    record = records[0]
    assert "已截断" in record.output
    assert len(record.output) <= OUTPUT_MAX_LENGTH + 200
    # 保留尾部（引擎输出末尾带换行，尾部内容应完整保留）
    assert big_output[-100:] in record.output

    log_path = tmp_path / record.log_file_path
    assert log_path.is_file()
    content = log_path.read_text(encoding="utf-8")
    assert big_output in content


def test_truncate_output_helper():
    """TC-LOG-005: _truncate_output 短输出原样返回，长输出保留尾部并标注。"""
    assert _truncate_output(None) is None
    assert _truncate_output("short") == "short"
    long_text = "y" * (OUTPUT_MAX_LENGTH + 10)
    truncated = _truncate_output(long_text)
    assert "已截断" in truncated
    assert truncated.endswith(long_text[-OUTPUT_MAX_LENGTH:])


@pytest.mark.asyncio
async def test_download_record_log(client, test_db, admin_user, admin_token, monkeypatch, tmp_path):
    """TC-LOG-006: GET /records/{id}/log 返回日志文件内容；记录或文件不存在时 404。"""
    monkeypatch.setattr(get_settings(), "LOGS_PATH", str(tmp_path))

    device = Device(
        serial_number="log-api-serial",
        status="online",
        pc_identifier="test-pc-admin",
        owner_id=admin_user.id,
    )
    module = TestModule(name="LogApiModule", created_by=admin_user.id)
    test_db.add_all([device, module])
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(module)

    item = TestItem(
        module_id=module.id,
        name="LogApiItem",
        exec_type="adb_shell",
        exec_command="echo ok",
        parameters={},
        compatibility={},
        judgement_type="assertion",
        created_by=admin_user.id,
    )
    test_db.add(item)
    await test_db.commit()
    await test_db.refresh(item)

    task = TestTask(
        user_id=admin_user.id,
        device_id=device.id,
        name="log-api-task",
        selected_items=[item.id],
        status="completed",
    )
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    # 准备日志文件与两条记录（一条有日志文件、一条没有）
    rel_path = f"task_{task.id}/record_manual.log"
    abs_path = tmp_path / rel_path
    abs_path.parent.mkdir(parents=True, exist_ok=True)
    abs_path.write_text("完整日志内容\nline2\n", encoding="utf-8")

    record_with_log = TestRecord(
        task_id=task.id, item_id=item.id, status="pass", log_file_path=rel_path
    )
    record_without_log = TestRecord(task_id=task.id, item_id=item.id, status="skip")
    test_db.add_all([record_with_log, record_without_log])
    await test_db.commit()
    await test_db.refresh(record_with_log)
    await test_db.refresh(record_without_log)

    headers = {"Authorization": f"Bearer {admin_token}"}

    resp = await client.get(f"/api/v1/records/{record_with_log.id}/log", headers=headers)
    assert resp.status_code == 200
    assert "完整日志内容" in resp.text
    assert "line2" in resp.text

    resp = await client.get(f"/api/v1/records/{record_without_log.id}/log", headers=headers)
    assert resp.status_code == 404

    resp = await client.get("/api/v1/records/999999/log", headers=headers)
    assert resp.status_code == 404
