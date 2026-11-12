"""T-06 失败关闭与原生 SKIP 判定单元测试。

覆盖 verification-rules-v1.0 §4：
- EXEC-01 非零退出，同时出现 pass_pattern 或 SKIP → fail；
- EXEC-02 rc=0、pass_pattern 未命中 → fail；
- EXEC-03 pass/fail 同时命中 → fail；
- EXEC-04 无配置/空规则/未知操作符/AI 无有效结论 → error（不得 pass）；
- EXEC-05 超时、子进程启动异常 → timeout/error 分类准确；
- SKIP-01 rc=0 独立行 `RESULT: SKIP: 原因` → skip，原因贯通 record；
- SKIP-02 `foo RESULT: SKIP`、`RESULT: SKIPPED` 等不误判 skip（真值表）。

并覆盖 docs/design/execution-state-machine.md §2 判定优先级真值表的关键行，
含 T-06 语义决策：assertion 条件为 false → fail；仅 fail_pattern 且未命中 → error。
"""
import asyncio
from unittest.mock import AsyncMock

import pytest
from sqlalchemy import select

from app.models import Device, TestItem, TestModule, TestRecord, TestTask
from app.services.execution_engine import AdbShellEngine, HostExecEngine
from app.services.judgement_engine import (
    JudgementEngine,
    RuleBasedJudger,
    find_native_skip,
    parse_patterns,
)
from app.services.task_executor import DeviceLock, TaskExecutor


# --------------------------------------------------------------------------- #
# 辅助构造
# --------------------------------------------------------------------------- #

def _device(serial="unit-fc-serial"):
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
        name="FC Item",
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


async def _judge(output, returncode=0, *, judgement_type="assertion", rules=None,
                 rubric_criteria=None, result_parse=None, spec=None,
                 baselines=None, ai_client=None):
    engine = JudgementEngine(ai_client=ai_client) if ai_client is not None else JudgementEngine()
    return await engine.judge(
        output=output,
        returncode=returncode,
        item_name="item",
        item_description="",
        judgement_type=judgement_type,
        rules=rules or {},
        rubric_criteria=rubric_criteria or {},
        device_context={"model": "rk3568"},
        spec=spec,
        baselines=baselines,
        result_parse=result_parse,
    )


class _StubLLM:
    """模拟 LLMClient.chat_completion_structured 的返回/异常。"""

    def __init__(self, result=None, exc=None):
        self._result = result
        self._exc = exc

    async def chat_completion_structured(self, messages, schema, temperature=None):
        if self._exc is not None:
            raise self._exc
        return self._result


async def _run_adb_engine(output, returncode=0, *, item=None):
    engine = AdbShellEngine()
    engine.adb.execute_shell = AsyncMock(return_value=(output, "", returncode))
    return await engine.execute(_device(), item or _item())


# --------------------------------------------------------------------------- #
# EXEC-01：非零退出码最高优先（即使输出含 pass_pattern / SKIP）
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_exec01_nonzero_rc_with_pass_and_skip_is_fail_engine():
    """EXEC-01：rc=1 同时命中 pass_pattern 且含 SKIP 行 → fail，reason 含退出码。"""
    result = await _run_adb_engine("ok\nRESULT: SKIP: 设备缺失\n", 1)
    assert result.status == "fail"
    assert "1" in result.fail_reason
    assert result.status != "pass" and result.status != "skip"


@pytest.mark.asyncio
async def test_exec01_nonzero_rc_with_pass_pattern_is_fail_judge():
    """EXEC-01：judge 层 rc!=0 + pass_pattern 命中 → fail（不得 pass）。"""
    result = await _judge("ok all good", returncode=1, result_parse={"pass_pattern": "ok"})
    assert result.status == "fail"
    assert "1" in result.fail_reason


@pytest.mark.asyncio
async def test_exec01_nonzero_rc_with_skip_line_is_fail_judge():
    """EXEC-01：judge 层 rc!=0 + 原生 SKIP 行 → fail（不得 skip）。"""
    result = await _judge("\nRESULT: SKIP: 无设备\n", returncode=2)
    assert result.status == "fail"
    assert "2" in result.fail_reason


# --------------------------------------------------------------------------- #
# EXEC-02：rc=0 且 pass_pattern 未命中 → fail
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_exec02_pass_pattern_miss_is_fail_judge():
    result = await _judge("no marker here", returncode=0, result_parse={"pass_pattern": "PASS"})
    assert result.status == "fail"
    assert "pass_pattern" in result.fail_reason


@pytest.mark.asyncio
async def test_exec02_pass_pattern_miss_is_fail_engine():
    result = await _run_adb_engine("clean run with nothing to report", 0)
    assert result.status == "fail"


def test_exec02_parse_result_no_longer_returns_unknown():
    """parse_result 不再产出 unknown：pass_pattern 未命中 → fail。"""
    engine = AdbShellEngine()
    parsed = engine.parse_result("nothing matches", {"pass_pattern": "ok"})
    assert parsed["status"] == "fail"


# --------------------------------------------------------------------------- #
# EXEC-03：pass/fail 同时命中 → fail
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_exec03_both_patterns_hit_is_fail_judge():
    result = await _judge(
        "ERROR: boom\nSTATUS ok\n",
        returncode=0,
        result_parse={"pass_pattern": "ok", "fail_pattern": "ERROR"},
    )
    assert result.status == "fail"
    assert "失败模式" in result.fail_reason


@pytest.mark.asyncio
async def test_exec03_both_patterns_hit_is_fail_engine():
    result = await _run_adb_engine(
        "ERROR: boom\nok\n", 0, item=_item(result_parse={"pass_pattern": "ok", "fail_pattern": "ERROR"})
    )
    assert result.status == "fail"


# --------------------------------------------------------------------------- #
# EXEC-04：无配置 / 空规则 / 未知操作符 / 非法正则 / 非法结构 / AI 无结论 → error
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_exec04_no_config_is_error():
    result = await _judge("anything", returncode=0, result_parse=None)
    assert result.status == "error"
    assert "判定配置不可用" in result.fail_reason


@pytest.mark.asyncio
async def test_exec04_empty_conditions_is_error():
    result = await _judge("x", returncode=0, rules={"conditions": []})
    assert result.status == "error"
    assert "判定配置不可用" in result.fail_reason


@pytest.mark.asyncio
async def test_exec04_unknown_operator_is_error():
    result = await _judge(
        "value=1",
        returncode=0,
        rules={"conditions": [
            {"source": r"regex:value=(\d+)", "operator": "roughly", "target": "1"}
        ]},
    )
    assert result.status == "error"
    assert "未知操作符" in result.fail_reason


@pytest.mark.asyncio
async def test_exec04_illegal_regex_is_error():
    result = await _judge(
        "value=1",
        returncode=0,
        rules={"conditions": [
            {"source": r"regex:([unclosed", "operator": "eq", "target": "1"}
        ]},
    )
    assert result.status == "error"
    assert "非法正则" in result.fail_reason


@pytest.mark.asyncio
async def test_exec04_illegal_structure_is_error():
    # conditions 非列表
    r1 = await _judge("x", returncode=0, rules={"conditions": "not-a-list"})
    assert r1.status == "error"
    # 条件非对象
    r2 = await _judge("x", returncode=0, rules={"conditions": ["not-a-dict"]})
    assert r2.status == "error"
    # 缺少 source/operator
    r3 = await _judge("x", returncode=0, rules={"conditions": [{"target": "1"}]})
    assert r3.status == "error"


@pytest.mark.asyncio
async def test_exec04_assertion_extract_failure_is_error_not_default_pass():
    """无法从输出提取 → error（旧语义此路径会回退默认 pass）。"""
    result = await _judge(
        "no numeric value",
        returncode=0,
        rules={"conditions": [
            {"source": r"regex:value=(\d+)", "operator": "gte", "target": "10"}
        ]},
    )
    assert result.status == "error"
    assert "判定配置不可用" in result.fail_reason


@pytest.mark.asyncio
async def test_exec04_ai_no_conclusion_is_error():
    stub = _StubLLM(result={"status": "unknown", "confidence": 0.3, "evidence": [],
                            "fail_reason": "", "suggestions": ""})
    result = await _judge("some output", returncode=0, judgement_type="ai_fallback", ai_client=stub)
    assert result.status == "error"
    assert result.status != "pass" and result.status != "unknown"
    assert "AI 判定无有效结论" in result.fail_reason


@pytest.mark.asyncio
async def test_exec04_ai_exception_is_error():
    stub = _StubLLM(exc=RuntimeError("boom"))
    result = await _judge("some output", returncode=0, judgement_type="ai_fallback", ai_client=stub)
    assert result.status == "error"
    assert "AI 判定服务异常" in result.fail_reason


@pytest.mark.asyncio
async def test_exec04_unknown_judgement_type_is_error():
    result = await _judge("x", returncode=0, judgement_type="magic_mode")
    assert result.status == "error"
    assert "判定配置不可用" in result.fail_reason


# --------------------------------------------------------------------------- #
# SKIP 语义决策（Lead 确认）：仅 fail_pattern 且未命中 → error
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_fail_pattern_only_without_hit_is_error():
    """rc=0、仅配置 fail_pattern 且未命中，缺少正向通过判据 → error（非 pass/fail）。"""
    result = await _judge("all clean", returncode=0, result_parse={"fail_pattern": "FATAL"})
    assert result.status == "error"
    assert "判定配置不可用" in result.fail_reason


# --------------------------------------------------------------------------- #
# EXEC-05：超时 / 子进程启动异常 分类准确
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_exec05_timeout_is_timeout():
    item = _item(exec_type="host_exec", exec_command='python -c "import time; time.sleep(5)"', timeout=1)
    result = await HostExecEngine().execute(_device(), item)
    assert result.status == "timeout"
    assert "超时" in result.fail_reason


@pytest.mark.asyncio
async def test_exec05_subprocess_start_error_is_error(monkeypatch):
    """HostExecEngine 内部异常（子进程无法启动）→ error，不落 fail。"""
    async def _boom(*args, **kwargs):
        raise OSError("spawn failed")
    monkeypatch.setattr("app.services.execution_engine.asyncio.create_subprocess_shell", _boom)
    item = _item(exec_type="host_exec", exec_command="whatever")
    result = await HostExecEngine().execute(_device(), item)
    assert result.status == "error"
    assert "执行异常" in result.fail_reason


@pytest.mark.asyncio
async def test_exec05_adb_shell_exception_maps_to_error_record(test_db, mock_adb, admin_user):
    """ADB 执行异常经 TaskExecutor 收尾为 error（行2：执行器内部异常 → error）。"""
    from tests.unit.test_task_executor import _run_single_item_task, _cleanup_executor
    mock_adb.execute_shell = AsyncMock(side_effect=RuntimeError("adb 启动失败"))
    task, records = await _run_single_item_task(
        test_db, admin_user,
        serial="fc-exec05-serial",
        item_kwargs={"result_parse": {"pass_pattern": "ok"}, "timeout": 30},
    )
    try:
        assert len(records) == 1
        assert records[0].status == "error"
        assert "执行异常" in records[0].fail_reason
        await test_db.refresh(task)
        assert task.status == "completed"
    finally:
        await _cleanup_executor(task.id)


# --------------------------------------------------------------------------- #
# SKIP-01：原生独立行 SKIP → skip，原因贯通 record
# --------------------------------------------------------------------------- #

def test_skip01_find_native_skip_reason():
    assert find_native_skip("log\nRESULT: SKIP: 电池缺失\nend") == "电池缺失"
    assert find_native_skip("RESULT: SKIP") == ""
    assert find_native_skip("   RESULT: SKIP: 无外设   ") == "无外设"


@pytest.mark.asyncio
async def test_skip01_engine_skip_with_reason():
    result = await _run_adb_engine("start\nRESULT: SKIP: 外设未连接\ndone", 0)
    assert result.status == "skip"
    assert result.fail_reason == "外设未连接"


@pytest.mark.asyncio
async def test_skip01_skip_beats_pass_pattern():
    """rc=0 原生 SKIP 行优先于 pass_pattern 命中（行4 先于行6）。"""
    result = await _judge(
        "ok\nRESULT: SKIP: 采集被跳过\nok", returncode=0,
        result_parse={"pass_pattern": "ok"},
    )
    assert result.status == "skip"
    assert result.fail_reason == "采集被跳过"


@pytest.mark.asyncio
async def test_skip01_reason_persists_to_record(test_db, mock_adb, admin_user):
    """SKIP-01：原生 SKIP 原因落 record.fail_reason（贯通 DB/报告/WS 已有链路）。"""
    from tests.unit.test_task_executor import _run_single_item_task, _cleanup_executor
    mock_adb.execute_shell = AsyncMock(return_value=("RESULT: SKIP: 设备无电池", "", 0))
    task, records = await _run_single_item_task(
        test_db, admin_user,
        serial="fc-skip01-serial",
        item_kwargs={"result_parse": {"pass_pattern": "ok"}, "timeout": 30},
    )
    try:
        assert len(records) == 1
        record = records[0]
        assert record.status == "skip"
        assert record.fail_reason == "设备无电池"
        # 报告/WS 均读取 record.fail_reason，此处断言其未被丢失
        await test_db.refresh(record)
        assert record.fail_reason == "设备无电池"
    finally:
        await _cleanup_executor(task.id)


# --------------------------------------------------------------------------- #
# SKIP-02：非独立行 / 大小写 / 相似词 不误判 skip（真值表）
# --------------------------------------------------------------------------- #

@pytest.mark.parametrize(
    "text",
    [
        "foo RESULT: SKIP",                    # 行内前缀文本
        "prefix RESULT: SKIP: reason",         # 行内前缀文本带原因
        "RESULT: SKIPPED",                     # 相似词
        "RESULT: SKIPPED: reason",
        "RESULT: skip",                        # 大小写敏感
        "result: skip: reason",
        "你将看到 RESULT: SKIP 的说明",          # 自然语言
        "You may use RESULT: SKIP when absent",
    ],
)
def test_skip02_not_native_skip(text):
    assert find_native_skip(text) is None


@pytest.mark.asyncio
async def test_skip02_skipped_word_is_not_skip_but_fail():
    """`RESULT: SKIPPED` 不判 skip：rc=0 且 pass_pattern 未命中 → fail。"""
    result = await _judge(
        "RESULT: SKIPPED", returncode=0, result_parse={"pass_pattern": "ok"}
    )
    assert result.status != "skip"
    assert result.status == "fail"


@pytest.mark.asyncio
async def test_skip02_embedded_phrase_is_not_skip_but_error():
    """`foo RESULT: SKIP` 非独立行，不判 skip；无其它通过判据 → error。"""
    result = await _judge("foo RESULT: SKIP", returncode=0, result_parse=None)
    assert result.status != "skip"
    assert result.status == "error"


@pytest.mark.asyncio
async def test_skip02_native_skip_beats_fail_pattern():
    """rc=0 原生 SKIP 优先于 fail_pattern 命中（行4 先于行5）。"""
    result = await _judge(
        "ERROR: transient\nRESULT: SKIP: 未执行\n",
        returncode=0,
        result_parse={"fail_pattern": "ERROR"},
    )
    assert result.status == "skip"
    assert result.fail_reason == "未执行"


# --------------------------------------------------------------------------- #
# 判定优先级真值表补充（状态机 §2 关键行）
# --------------------------------------------------------------------------- #

@pytest.mark.asyncio
async def test_truth_table_assertion_true_pass():
    result = await _judge(
        "value=120", returncode=0,
        rules={"conditions": [
            {"source": r"regex:value=(\d+)", "operator": "gte", "target": "100"}
        ]},
    )
    assert result.status == "pass"


@pytest.mark.asyncio
async def test_truth_table_assertion_false_fail():
    """状态机行7：有效断言完整执行且为 false → fail（指出未满足断言）。"""
    result = await _judge(
        "value=50", returncode=0,
        rules={"conditions": [
            {"source": r"regex:value=(\d+)", "operator": "gte", "target": "100"}
        ]},
    )
    assert result.status == "fail"
    assert "未满足断言" in result.fail_reason


@pytest.mark.asyncio
async def test_truth_table_rubric_above_threshold_pass():
    criteria = {"bw": {"extract_pattern": r"bw=([\d.]+)", "levels": [
        {"score": 4, "threshold": 100}, {"score": 2, "threshold": 50}, {"score": 1}
    ]}}
    result = await _judge("bw=200", returncode=0, judgement_type="rubric", rubric_criteria=criteria)
    assert result.status == "pass"


@pytest.mark.asyncio
async def test_truth_table_rubric_below_threshold_fail():
    criteria = {"bw": {"extract_pattern": r"bw=([\d.]+)", "levels": [
        {"score": 4, "threshold": 100}, {"score": 2, "threshold": 50}, {"score": 1}
    ]}}
    result = await _judge("bw=10", returncode=0, judgement_type="rubric", rubric_criteria=criteria)
    assert result.status == "fail"


@pytest.mark.asyncio
async def test_truth_table_rubric_no_valid_score_error():
    criteria = {"bw": {"extract_pattern": r"bw=([\d.]+)", "levels": [{"score": 4, "threshold": 100}]}}
    result = await _judge("no number here", returncode=0, judgement_type="rubric", rubric_criteria=criteria)
    assert result.status == "error"


@pytest.mark.asyncio
async def test_truth_table_ai_explicit_pass():
    stub = _StubLLM(result={"status": "pass", "confidence": 0.9, "evidence": ["ok"],
                            "fail_reason": "", "suggestions": ""})
    result = await _judge("out", returncode=0, judgement_type="ai_fallback", ai_client=stub)
    assert result.status == "pass"


@pytest.mark.asyncio
async def test_truth_table_ai_explicit_fail():
    stub = _StubLLM(result={"status": "fail", "confidence": 0.9, "evidence": ["bad"],
                            "fail_reason": "指标不达标", "suggestions": ""})
    result = await _judge("out", returncode=0, judgement_type="ai_fallback", ai_client=stub)
    assert result.status == "fail"
    assert result.fail_reason == "指标不达标"


@pytest.mark.asyncio
async def test_truth_table_ai_skip_status_is_error_not_skip():
    """AI 返回 skip 不属于「明确 pass/fail」，落 error（不做成 skip）。"""
    stub = _StubLLM(result={"status": "skip", "confidence": 0.5, "evidence": [],
                            "fail_reason": "", "suggestions": ""})
    result = await _judge("out", returncode=0, judgement_type="ai_fallback", ai_client=stub)
    assert result.status == "error"


# --------------------------------------------------------------------------- #
# skip 不触发 stop-on-failure
# --------------------------------------------------------------------------- #

async def _run_multi_item_task(test_db, admin_user, *, serial, item_specs):
    """创建多测试项任务并同步跑完，返回 (task, {item_id: record})。"""
    device = Device(serial_number=serial, status="testing",
                    pc_identifier="test-pc-admin", owner_id=admin_user.id)
    module = TestModule(name=f"FCModule-{serial}", created_by=admin_user.id)
    test_db.add_all([device, module])
    await test_db.commit()
    await test_db.refresh(device)
    await test_db.refresh(module)

    items = []
    for idx, spec in enumerate(item_specs):
        item = TestItem(
            module_id=module.id, name=f"FCItem-{serial}-{idx}", exec_type="adb_shell",
            exec_command="echo ok", parameters={}, compatibility={},
            judgement_type=spec.get("judgement_type", "assertion"),
            created_by=admin_user.id, **{k: v for k, v in spec.items() if k != "judgement_type"},
        )
        test_db.add(item)
        items.append(item)
    await test_db.commit()
    for item in items:
        await test_db.refresh(item)

    task = TestTask(user_id=admin_user.id, device_id=device.id, name=f"fc-task-{serial}",
                    selected_items=[i.id for i in items], status="pending")
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
        result = await test_db.execute(select(TestRecord).where(TestRecord.task_id == task.id))
        records = {r.item_id: r for r in result.scalars().all()}
        return task, records, items
    finally:
        leftover = TaskExecutor._running_tasks.get(task.id)
        if leftover and not leftover.done():
            leftover.cancel()
            await asyncio.gather(leftover, return_exceptions=True)
        TaskExecutor._running_tasks.clear()
        DeviceLock._locks.clear()
        DeviceLock._holders.clear()


@pytest.mark.asyncio
async def test_skip_does_not_trigger_stop_on_failure(test_db, mock_adb, admin_user):
    """skip 不属于 fail/error/timeout：即使 on_failure=stop 也不停止后续测试项。"""
    mock_adb.execute_shell = AsyncMock(side_effect=[
        ("RESULT: SKIP: 无外设", "", 0),
        ("ok", "", 0),
    ])
    task, records, items = await _run_multi_item_task(
        test_db, admin_user,
        serial="fc-skip-nostop",
        item_specs=[
            {"result_parse": {"pass_pattern": "ok"}, "timeout": 30, "on_failure": "stop"},
            {"result_parse": {"pass_pattern": "ok"}, "timeout": 30, "on_failure": "stop"},
        ],
    )
    assert records[items[0].id].status == "skip"
    assert records[items[1].id].status == "pass"
    assert mock_adb.execute_shell.call_count == 2
    await test_db.refresh(task)
    assert task.status == "completed"
