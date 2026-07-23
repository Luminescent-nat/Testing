"""ADB 子进程在超时/取消时被正确终止的单元测试。"""
import asyncio

import pytest

from app.services.device import ADBService


class FakeProcess:
    """模拟一个永不返回的子进程。"""

    def __init__(self):
        self.pid = 4321
        self.returncode = None
        self.terminated = False
        self.killed = False

    def terminate(self):
        self.terminated = True

    def kill(self):
        self.killed = True

    async def communicate(self):
        await asyncio.sleep(60)
        return b"", b""

    async def wait(self):
        if self.returncode is None:
            self.returncode = -9
        return self.returncode


@pytest.fixture
def fake_process(monkeypatch):
    """替换 create_subprocess_exec，返回可控的假进程。"""
    process = FakeProcess()

    async def fake_create_subprocess_exec(*args, **kwargs):
        return process

    monkeypatch.setattr(asyncio, "create_subprocess_exec", fake_create_subprocess_exec)
    return process


@pytest.mark.asyncio
async def test_execute_shell_timeout_kills_process(fake_process):
    """TC-ADB-001: execute_shell 超时后终止底层 adb 子进程。"""
    adb = ADBService()
    stdout, stderr, returncode = await adb.execute_shell("serial-1", "sleep 60", timeout=0.1)

    assert returncode == -1
    assert "Timeout" in stderr
    assert fake_process.terminated or fake_process.killed


@pytest.mark.asyncio
async def test_run_adb_command_timeout_kills_process(fake_process):
    """TC-ADB-002: _run_adb_command 超时后终止底层 adb 子进程。"""
    adb = ADBService()
    adb.timeout = 0.1
    stdout, stderr, returncode = await adb._run_adb_command(["devices"])

    assert returncode == -1
    assert fake_process.terminated or fake_process.killed


@pytest.mark.asyncio
async def test_execute_shell_cancel_kills_process(fake_process):
    """TC-ADB-003: 外层取消 execute_shell 时终止子进程并继续传播 CancelledError。"""
    adb = ADBService()
    task = asyncio.create_task(adb.execute_shell("serial-1", "sleep 60", timeout=60))
    await asyncio.sleep(0.05)
    task.cancel()
    with pytest.raises(asyncio.CancelledError):
        await task

    assert fake_process.terminated or fake_process.killed
