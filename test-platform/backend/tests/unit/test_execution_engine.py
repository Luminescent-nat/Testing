"""执行引擎单元测试。"""
import pytest
from unittest.mock import AsyncMock, MagicMock

from app.models import Device, TestItem
from app.services.execution_engine import (
    AdbShellEngine,
    PushExecEngine,
    HostExecEngine,
    EngineFactory,
)


@pytest.fixture
def sample_device():
    return Device(
        serial_number="rk3568-test",
        model="rk3568",
        android_version="11",
        sdk_version="30",
        cpu_abi="arm64-v8a",
        ddr_info={"total_mb": 2048},
        emmc_info={"total_gb": 32},
        features=["wifi", "bluetooth", "ethernet"],
        board="rk3568",
        hardware="rk3568-evb",
    )


@pytest.fixture
def sample_item():
    return TestItem(
        module_id=1,
        name="Test Item",
        exec_type="adb_shell",
        exec_command="echo ok",
        parameters={},
        compatibility={},
        judgement_type="assertion",
        result_parse={"pass_pattern": "ok"},
        timeout=30,
    )


@pytest.mark.asyncio
async def test_adb_shell_engine_pass(sample_device, sample_item, monkeypatch):
    engine = AdbShellEngine()
    engine.adb.execute_shell = AsyncMock(return_value=("ok", "", 0))

    result = await engine.execute(sample_device, sample_item)
    assert result.status == "pass"
    assert "ok" in result.output


@pytest.mark.asyncio
async def test_adb_shell_engine_with_parameters(sample_device, sample_item, monkeypatch):
    sample_item.exec_command = "echo {size}"
    sample_item.parameters = {"size": "{device.ddr_info.total_mb // 4}M"}
    engine = AdbShellEngine()
    engine.adb.execute_shell = AsyncMock(return_value=("512M", "", 0))

    result = await engine.execute(sample_device, sample_item)
    engine.adb.execute_shell.assert_awaited_once()
    assert "512M" in engine.adb.execute_shell.call_args[0][1]


@pytest.mark.asyncio
async def test_adb_shell_engine_unrendered_placeholder(sample_device, sample_item):
    sample_item.exec_command = "echo {missing}"
    engine = AdbShellEngine()
    result = await engine.execute(sample_device, sample_item)
    assert result.status == "error"
    assert "未替换" in result.fail_reason


@pytest.mark.asyncio
async def test_adb_shell_engine_adb_device_not_found(sample_device, sample_item):
    engine = AdbShellEngine()
    engine.adb.execute_shell = AsyncMock(return_value=("error: device 'xxx' not found", "", 1))
    result = await engine.execute(sample_device, sample_item)
    assert result.status == "fail"
    assert "ADB" in result.fail_reason


@pytest.mark.asyncio
async def test_push_exec_engine_missing_tool_file(sample_device, sample_item, test_db):
    sample_item.exec_type = "push_exec"
    sample_item.tool_id = 99999
    engine = PushExecEngine()
    result = await engine.execute(sample_device, sample_item)
    assert result.status == "error"


@pytest.mark.asyncio
async def test_host_exec_engine_pass(sample_device, sample_item, monkeypatch):
    sample_item.exec_type = "host_exec"
    sample_item.exec_command = 'python -c "print(\'ok\')"'
    engine = HostExecEngine()
    result = await engine.execute(sample_device, sample_item)
    assert result.status == "pass"
    assert "ok" in result.output


@pytest.mark.asyncio
async def test_host_exec_engine_timeout(sample_device, sample_item):
    sample_item.exec_type = "host_exec"
    sample_item.exec_command = 'python -c "import time; time.sleep(10)"'
    sample_item.result_parse = {"fail_pattern": "Timeout"}
    sample_item.timeout = 1
    engine = HostExecEngine()
    result = await engine.execute(sample_device, sample_item)
    # 超时不再走判定逻辑，直接标记为 timeout 状态
    assert result.status == "timeout"
    assert "超时" in result.fail_reason
    assert "Timeout" in result.output


@pytest.mark.asyncio
async def test_engine_factory():
    assert isinstance(EngineFactory.get_engine("adb_shell"), AdbShellEngine)
    assert isinstance(EngineFactory.get_engine("push_exec"), PushExecEngine)
    assert isinstance(EngineFactory.get_engine("host_exec"), HostExecEngine)


def test_engine_factory_unknown_type():
    with pytest.raises(ValueError):
        EngineFactory.get_engine("unknown")


@pytest.mark.asyncio
async def test_compatibility_android_version(sample_device, sample_item):
    sample_item.compatibility = {"min_android_version": "12"}
    engine = AdbShellEngine()
    valid, reason = await engine.validate(sample_device, sample_item)
    assert valid is False
    assert "Android版本过低" in reason


@pytest.mark.asyncio
async def test_compatibility_arch(sample_device, sample_item):
    sample_item.compatibility = {"supported_archs": ["x86_64"]}
    engine = AdbShellEngine()
    valid, reason = await engine.validate(sample_device, sample_item)
    assert valid is False
    assert "架构不兼容" in reason


@pytest.mark.asyncio
async def test_compatibility_features(sample_device, sample_item):
    sample_item.compatibility = {"required_features": ["nfc"]}
    engine = AdbShellEngine()
    valid, reason = await engine.validate(sample_device, sample_item)
    assert valid is False
    assert "缺少必要能力" in reason
