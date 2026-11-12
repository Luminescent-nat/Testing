"""V1 readiness 定向缺陷回归（V1-02 / V1-03 / V1-07 执行器部分）。

源自审计 RR-V1-READINESS-20261112 的动态复现：
- V1-02：conditional_rules=[]/标量/null 非法根结构不得被 pass_pattern 变成 pass；
  approx_ratio 零目标禁止；非法正则/未知操作符/无法提取/非数值 → error。
- V1-03：stop-on-failure 第 2 项失败后剩余 3 项必须补 skip（stopped_by_item_id），
  不执行、不重试、不伪造输出；记录 pass,fail,skip,skip,skip；completed/100/pass_rate=50.0；
  覆盖 fail/error/timeout 三种触发。
- V1-07：执行器无法启动/子进程启动失败 → error（非测试 fail）；平台异常只持久化
  安全摘要，原始异常文本/堆栈不进入 200 任务详情字段，完整堆栈仅进服务端日志。

这些用例为永久回归（fail → pass）。
"""
import asyncio
import logging
from unittest.mock import AsyncMock, patch

import pytest
from sqlalchemy import select

from app.models import Device, TestItem, TestModule, TestRecord, TestTask
from app.services.device import ADBService, INTERNAL_ERROR_RC
from app.services.execution_engine import AdbShellEngine, HostExecEngine
from app.services.judgement_engine import JudgementEngine, RuleBasedJudger
from app.services.task_executor import DeviceLock, TaskExecutor

_UNSET = object()


def _device(serial="v1-unit-serial"):
    return Device(
        serial_number=serial,
        model="rk3568",
        android_version="11",
        sdk_version="30",
        cpu_abi="arm64-v8a",
        ddr_info={"total_mb": 2048},
        emmc_info={"total_gb": 32},
        features=["wifi"],
        board="rk3568",
        hardware="rk3568-evb",
    )


def _item(**kwargs):
    base = dict(
        module_id=1,
        name="V1 Item",
        exec_type="adb_shell",
        exec_command="echo ok",
        parameters={},
        compatibility={},
        judgement_type="assertion",
        result_parse={"pass_pattern": "ok"},
        timeout=30,
    )
    base.update(kwargs)
    return TestItem(**base)


async def _judge(output, returncode=0, *, judgement_type="assertion", rules=_UNSET,
                 rubric_criteria=None, result_parse=None, spec=None,
                 baselines=None, ai_client=None):
    if rules is _UNSET:
        rules = {}
    engine = JudgementEngine(ai_client=ai_client) if ai_client is not None else JudgementEngine()
    return await engine.judge(
        output=output,
        returncode=returncode,
        item_name="item",
        item_description="",
        judgement_type=judgement_type,
        rules=rules,
        rubric_criteria=rubric_criteria or {},
        device_context={"model": "rk3568"},
        spec=spec,
        baselines=baselines,
        result_parse=result_parse,
    )


# =========================================================================== #
# V1-02 ①：非法根结构不得被 pass_pattern 变成 pass（含审计原始复现）
# =========================================================================== #

@pytest.mark.asyncio
async def test_audit_falsy_invalid_rules_cannot_be_passed_by_pattern():
    """审计复现（RR-V1-READINESS targeted line 59-73）：conditional_rules=[] → error。"""
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


@pytest.mark.parametrize(
    "bad_rules",
    [
        [],                                              # 空数组
        [{"source": "regex:x=(\\d+)", "operator": "eq", "target": "1"}],  # 非空数组
        "conditions",                                    # 字符串标量
        5,                                               # 数字标量
        5.0,
        True,                                            # 布尔标量
        None,                                            # null（judge API 层）
    ],
)
@pytest.mark.asyncio
async def test_illegal_rules_root_is_error_even_with_pass_pattern(bad_rules):
    """[]/标量/null 等非法根结构：先按原始类型校验 → error，绝不被 pass_pattern 变成 pass。"""
    result = await _judge(output="ok", returncode=0, rules=bad_rules,
                          result_parse={"pass_pattern": "ok"})
    assert result.status == "error", (bad_rules, result.to_dict())
    assert "判定配置不可用" in result.fail_reason


@pytest.mark.asyncio
async def test_illegal_result_parse_root_is_error():
    result = await _judge(output="ok", returncode=0, rules={}, result_parse=[{"pass_pattern": "ok"}])
    assert result.status == "error"
    assert "判定配置不可用" in result.fail_reason


@pytest.mark.asyncio
async def test_empty_dict_rules_still_route_to_pattern_layer():
    """合法的空对象（无断言规则）仍走正则层：pass_pattern 命中 → pass（既有语义保留）。"""
    result = await _judge(output="ok here", returncode=0, rules={},
                          result_parse={"pass_pattern": "ok"})
    assert result.status == "pass"


# =========================================================================== #
# V1-02 ②：approx_ratio 零目标禁止（审计原始复现 + 运行时 error 兜底）
# =========================================================================== #

def test_audit_approx_ratio_zero_target_cannot_pass():
    """审计复现（targeted line 76-79）：_compare 对零目标必须返回 False。"""
    ok, _ = RuleBasedJudger()._compare(100, "approx_ratio", 0, "0%")
    assert ok is False


@pytest.mark.parametrize("target", [0, 0.0, "0", "0.0", "spec:zero"])
@pytest.mark.asyncio
async def test_approx_ratio_zero_target_runtime_error(target):
    rules = {"conditions": [{
        "source": r"regex:value=(\d+)",
        "operator": "approx_ratio",
        "target": target,
        "tolerance": "0%",
    }]}
    result = await _judge("value=100", returncode=0, rules=rules, spec={"zero": 0})
    assert result.status == "error", result.to_dict()
    assert "判定配置不可用" in result.fail_reason


@pytest.mark.asyncio
async def test_approx_ratio_nonzero_target_still_works():
    rules = {"conditions": [{
        "source": r"regex:value=(\d+)", "operator": "approx_ratio",
        "target": "100", "tolerance": "5%",
    }]}
    assert (await _judge("value=103", returncode=0, rules=rules)).status == "pass"
    assert (await _judge("value=130", returncode=0, rules=rules)).status == "fail"


# =========================================================================== #
# V1-02 ③：非数值 / NaN / 非法正则 / 未知操作符 / 无法提取 → error
# =========================================================================== #

@pytest.mark.asyncio
async def test_non_numeric_comparison_is_error():
    rules = {"conditions": [{
        "source": r"regex:value=(\w+)", "operator": "gte", "target": "100",
    }]}
    result = await _judge("value=abc", returncode=0, rules=rules)
    assert result.status == "error"
    assert "非数值" in result.fail_reason


@pytest.mark.asyncio
async def test_nan_target_is_error():
    rules = {"conditions": [{
        "source": r"regex:value=(\d+)", "operator": "gte", "target": "nan",
    }]}
    result = await _judge("value=100", returncode=0, rules=rules)
    assert result.status == "error"


@pytest.mark.asyncio
async def test_illegal_regex_is_error():
    rules = {"conditions": [{
        "source": r"regex:([unclosed", "operator": "eq", "target": "1",
    }]}
    result = await _judge("value=1", returncode=0, rules=rules)
    assert result.status == "error"
    assert "非法正则" in result.fail_reason


@pytest.mark.asyncio
async def test_unknown_operator_is_error():
    rules = {"conditions": [{
        "source": r"regex:value=(\d+)", "operator": "roughly", "target": "1",
    }]}
    result = await _judge("value=1", returncode=0, rules=rules)
    assert result.status == "error"
    assert "未知操作符" in result.fail_reason


@pytest.mark.asyncio
async def test_extract_failure_is_error():
    rules = {"conditions": [{
        "source": r"regex:value=(\d+)", "operator": "gte", "target": "1",
    }]}
    result = await _judge("no number", returncode=0, rules=rules)
    assert result.status == "error"
    assert "判定配置不可用" in result.fail_reason


@pytest.mark.asyncio
async def test_both_patterns_hit_is_fail():
    """双模式：pass/fail 同时命中 → fail（不得 pass）。"""
    result = await _judge("ERROR\nok\n", returncode=0,
                          result_parse={"pass_pattern": "ok", "fail_pattern": "ERROR"})
    assert result.status == "fail"


# =========================================================================== #
# V1-03：stop-on-failure 收尾（审计原始复现 + fail/error/timeout 三触发）
# =========================================================================== #

async def _run_five_item_stop(test_db, mock_adb, admin_user, *, serial, trigger):
    """5 项全部 on_failure=stop，第 2 项按 trigger 触发 fail/error/timeout。"""
    device = Device(serial_number=serial, model="rk3568", status="online",
                    pc_identifier="test-pc-admin", owner_id=admin_user.id)
    module = TestModule(name=f"V1Stop-{serial}", created_by=admin_user.id)
    test_db.add_all([device, module])
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(module)

    items = []
    for index in range(5):
        item = TestItem(
            module_id=module.id,
            name=f"stop-item-{index}",
            exec_type="adb_shell",
            exec_command="echo ok",
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

    task = TestTask(user_id=admin_user.id, device_id=device.id, name=f"stop-task-{serial}",
                    selected_items=[i.id for i in items], status="pending")
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    calls = {"n": 0}

    async def _shell(*args, **kwargs):
        calls["n"] += 1
        if calls["n"] == 1:
            return ("ok", "", 0)
        if trigger == "error":
            raise RuntimeError("boom")
        if trigger == "timeout":
            return ("", "Timeout after 30 seconds", -1)
        return ("bad", "", 0)  # fail：pass_pattern 未命中

    mock_adb.execute_shell = AsyncMock(side_effect=_shell)

    TaskExecutor._running_tasks.clear()
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()
    try:
        assert TaskExecutor.start_task(task.id) is True
        running = TaskExecutor._running_tasks[task.id]
        await asyncio.gather(running, return_exceptions=True)
        records = (await test_db.execute(
            select(TestRecord).where(TestRecord.task_id == task.id).order_by(TestRecord.id)
        )).scalars().all()
        await test_db.refresh(task)
        return task, records, items, calls
    finally:
        leftover = TaskExecutor._running_tasks.get(task.id)
        if leftover and not leftover.done():
            leftover.cancel()
            await asyncio.gather(leftover, return_exceptions=True)
        TaskExecutor._running_tasks.clear()
        DeviceLock._locks.clear()
        DeviceLock._holders.clear()


@pytest.mark.asyncio
async def test_audit_stop_on_failure_completes_remaining_items_as_skip(
    test_db, mock_adb, admin_user
):
    """审计复现（targeted line 82-148）：第 2 项 fail+stop 后剩余 3 项补 skip。"""
    task, records, items, calls = await _run_five_item_stop(
        test_db, mock_adb, admin_user, serial="v1-stop-audit", trigger="fail"
    )

    assert [r.status for r in records] == ["pass", "fail", "skip", "skip", "skip"]
    assert task.status == "completed"
    assert task.progress_percent == 100
    # 仅执行前两项（剩余项不执行、不重试）
    assert calls["n"] == 2
    # 剩余项 reason 精确标注 stopped_by_item_id=<第 2 项 id>
    trigger_id = items[1].id
    for record in records[2:]:
        assert record.fail_reason == f"stopped_by_item_id={trigger_id}"
    # 不伪造输出
    for record in records[2:]:
        assert not record.output
    # 通过率：pass/(pass+fail+error+timeout)=1/2=50.0，skip 不进分母
    passed = sum(1 for r in records if r.status == "pass")
    denom = sum(1 for r in records if r.status in ("pass", "fail", "error", "timeout"))
    assert round(passed / denom * 100, 1) == 50.0


@pytest.mark.parametrize("trigger,expected", [
    ("fail", "fail"),
    ("error", "error"),
    ("timeout", "timeout"),
])
@pytest.mark.asyncio
async def test_stop_on_failure_all_trigger_kinds_fill_skip(
    test_db, mock_adb, admin_user, trigger, expected
):
    """fail / error / timeout 三种触发都会停止并补 3 条 skip。"""
    task, records, items, calls = await _run_five_item_stop(
        test_db, mock_adb, admin_user, serial=f"v1-stop-{trigger}", trigger=trigger
    )
    assert [r.status for r in records] == ["pass", expected, "skip", "skip", "skip"]
    assert task.status == "completed"
    assert task.progress_percent == 100
    assert calls["n"] == 2
    trigger_id = items[1].id
    for record in records[2:]:
        assert record.fail_reason == f"stopped_by_item_id={trigger_id}"
        assert not record.output


# =========================================================================== #
# V1-07：执行器无法启动/子进程启动失败 → error；安全摘要 + canary
# =========================================================================== #

@pytest.mark.asyncio
async def test_real_adb_launch_failure_classified_internal_error_rc(monkeypatch):
    """真实 ADBService 路径：adb 子进程无法启动 → 专用内部错误 rc + 安全摘要（无 canary）。"""
    canary = "SECRET-CANARY-ADB-LAUNCH-9876"

    async def _boom(*args, **kwargs):
        raise FileNotFoundError(canary)

    monkeypatch.setattr(asyncio, "create_subprocess_exec", _boom)
    adb = ADBService()
    out, err, rc = await adb.execute_shell("serial-x", "echo hi", timeout=5)

    assert rc == INTERNAL_ERROR_RC
    assert "执行器内部异常" in err
    assert canary not in out and canary not in err


@pytest.mark.asyncio
async def test_adb_shell_engine_internal_error_rc_is_error_not_fail():
    """执行器内部错误返回码经 AdbShellEngine → error（不是测试 fail）。"""
    engine = AdbShellEngine()
    engine.adb.execute_shell = AsyncMock(
        return_value=("", "执行器内部异常（FileNotFoundError）", INTERNAL_ERROR_RC)
    )
    result = await engine.execute(_device(), _item())
    assert result.status == "error"
    assert result.status != "fail"
    assert "执行异常" in result.fail_reason


@pytest.mark.asyncio
async def test_host_exec_launch_failure_is_error_and_canary_absent(monkeypatch):
    canary = "SECRET-CANARY-HOST-1234"

    async def _boom(*args, **kwargs):
        raise OSError(canary)

    monkeypatch.setattr("app.services.execution_engine.asyncio.create_subprocess_shell", _boom)
    item = _item(exec_type="host_exec", exec_command="whatever")
    ee_logger = logging.getLogger("app.services.execution_engine")
    with patch.object(ee_logger, "exception") as log_spy:
        result = await HostExecEngine().execute(_device(), item)

    assert result.status == "error"
    assert canary not in result.fail_reason
    assert canary not in (result.output or "")
    # 完整堆栈仅进服务端日志：确认走了 logger.exception（exc_info 落日志）
    assert log_spy.call_count >= 1


@pytest.mark.asyncio
async def test_platform_exception_record_fields_safe(
    test_db, mock_adb, admin_user
):
    """平台异常落库：record.fail_reason/output 只含安全摘要，原始异常文本不落库。"""
    from tests.unit.test_task_executor import _run_single_item_task, _cleanup_executor
    canary = "SECRET-CANARY-RECORD-5555"
    mock_adb.execute_shell = AsyncMock(side_effect=RuntimeError(canary))
    te_logger = logging.getLogger("app.services.task_executor")
    with patch.object(te_logger, "exception") as log_spy:
        task, records = await _run_single_item_task(
            test_db, admin_user,
            serial="v1-canary-record",
            item_kwargs={"result_parse": {"pass_pattern": "ok"}, "timeout": 30},
        )
    try:
        assert len(records) == 1
        record = records[0]
        assert record.status == "error"
        assert "执行异常" in record.fail_reason
        assert canary not in record.fail_reason
        assert canary not in (record.output or "")
        await test_db.refresh(task)
        assert canary not in (task.error_message or "")
        assert log_spy.call_count >= 1
    finally:
        await _cleanup_executor(task.id)


@pytest.mark.asyncio
async def test_task_error_message_persists_safe_summary(
    test_db, mock_adb, admin_user, monkeypatch
):
    """任务级平台异常：task.error_message 只保存安全摘要（不含原始异常文本）。"""
    canary = "SECRET-CANARY-TASK-7777"

    async def _boom_execute(*args, **kwargs):
        raise RuntimeError(canary)

    monkeypatch.setattr(TaskExecutor, "_execute_with_db", AsyncMock(side_effect=_boom_execute))
    monkeypatch.setattr("app.services.task_executor.generate_task_report_files", AsyncMock())

    device = Device(serial_number="v1-canary-task", status="online",
                    pc_identifier="test-pc-admin", owner_id=admin_user.id)
    test_db.add(device)
    await test_db.commit()
    await test_db.refresh(device)
    task = TestTask(user_id=admin_user.id, device_id=device.id,
                    name="v1-canary-task", selected_items=[], status="pending")
    test_db.add(task)
    await test_db.commit()
    await test_db.refresh(task)

    TaskExecutor._running_tasks.clear()
    DeviceLock._locks.clear()
    DeviceLock._holders.clear()
    te_logger = logging.getLogger("app.services.task_executor")
    try:
        with patch.object(te_logger, "exception") as log_spy:
            assert TaskExecutor.start_task(task.id) is True
            running = TaskExecutor._running_tasks[task.id]
            await asyncio.gather(running, return_exceptions=True)
        await test_db.refresh(task)
        assert task.status == "failed"
        assert task.error_message == "任务执行平台异常（RuntimeError）"
        assert canary not in (task.error_message or "")
        assert log_spy.call_count >= 1
    finally:
        TaskExecutor._running_tasks.clear()
        DeviceLock._locks.clear()
        DeviceLock._holders.clear()
