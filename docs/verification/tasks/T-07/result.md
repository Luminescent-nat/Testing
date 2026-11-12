# T-07 落地 — stop-on-failure 收尾 + 执行器异常分类（V1 readiness 修订）

- 关联：共享任务 task-10；审计 `docs/verification/reviews/RR-V1-READINESS-20261112.md` V1-03、V1-07（执行器部分）
- 复现源：`docs/verification/reviews/evidence/v1-readiness-20261112/targeted-defect-repro.py` L82-148（stop_remaining_skip）
- 设计依据：`docs/design/execution-state-machine.md` §4 stop-on-failure、§2 行2（执行器内部异常 → error）
- 执行人：execution-engine；时间：2026-11-12T16:25～16:47 +08:00
- 环境/解释器/变更集：同 `../T-06/V1-followup-result.md`（未 git commit）

## 1. 修复内容（V1-03 stop 收尾）

`task_executor.py::_execute_with_db` 中，失败项（fail/error/timeout）且 `on_failure=stop` 时，原实现只 `break`，随后无条件 `completed/100%`，导致 5 项只剩 `pass,fail` 两条记录、伪造完整收尾。

修复：新增 `TaskExecutor._skip_remaining_items(task, trigger_idx, trigger_item_id, db)`，在 break 前为**剩余未执行项**补建 `skip` 记录：
- `fail_reason = "stopped_by_item_id=<触发项 id>"`（严格对齐状态机 §4 的 `stopped_by_item_id=2` 语义）；
- 不执行命令、不消耗重试、不写 output（不伪造输出）；
- 之后由主流程统一收尾：`task.status=completed`、`progress_percent=100`。

记录真值（5 项第 2 项 fail+stop）：`pass, fail, skip, skip, skip`；C=N=5；pass=1、fail=1、skip=3；pass_rate=pass/(pass+fail+error+timeout)=1/2=**50.0%**（skip 不进分母）。任务 status=completed、业务结果层 failed（业务 result 由 V1-06 聚合层派生，见 §4）。

同时 `skip` 不在 stop 触发集合内（触发集合仍为 fail/error/timeout），skip 项不触发停止——既有语义未破坏。

## 2. 修复内容（V1-07 执行器异常分类）

- `device.py`：新增专用返回码 `INTERNAL_ERROR_RC=-2`；`execute_shell`/`_run_adb_command` 的非超时异常（含 adb 子进程无法启动）返回 `("", "执行器内部异常（<异常类型>）", -2)`，不再用 `-1`+`str(e)`。
- `execution_engine.py`：`AdbShellEngine`/`PushExecEngine` 对 `rc==INTERNAL_ERROR_RC` 直接 `ExecutionResult(status="error")`（不是测试 fail）；`HostExecEngine` 内部异常落 error，且 output/fail_reason 不含原始异常文本。
- `task_executor.py`：`_execute_item` 与 `_run_task` 的异常分支只持久化安全摘要（异常类型名），完整堆栈仅 `logger.exception` 进服务端日志。

## 3. 命令、退出码、原始日志

| 命令（workdir=backend） | 退出码 | 日志 |
|---|---|---|
| `pytest tests/unit/test_v1_judgement_stop.py::test_audit_stop_on_failure_completes_remaining_items_as_skip -v -W error::pytest.PytestUnraisableExceptionWarning` | 0 | [../T-06/v1-targeted-3-cases.log](../T-06/v1-targeted-3-cases.log)（含该用例） |
| `pytest tests/unit/test_v1_judgement_stop.py -q -W error::pytest.PytestUnraisableExceptionWarning` | 0（32 passed） | 终端留痕；文件日志见 T-06 |
| `pytest tests/unit -q -W error::pytest.PytestUnraisableExceptionWarning` | 0（243 passed） | [../T-06/v1-pytest-unit.log](../T-06/v1-pytest-unit.log) |
| `pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning`（严格） | 1（7 failed/362 passed，均为队友在途 SchemaMismatch 或已修日志断言） | [../T-06/v1-pytest-full.log](../T-06/v1-pytest-full.log) |
| `pytest tests -q ... --ignore=tests/integration/test_v1_authorization.py --ignore=tests/integration/test_websocket.py` | 0（**358 passed，0 failed**） | [../T-06/v1-pytest-full-excluding-inflight.log](../T-06/v1-pytest-full-excluding-inflight.log) |

## 4. DoD 逐条证据

| DoD | 结论 | 证据 |
|---|---|---|
| 第 2 项 fail+stop 后剩余 3 项补 skip，reason 含 stopped_by_item_id | ✅ | `test_audit_stop_on_failure_completes_remaining_items_as_skip`：`[r.status]==["pass","fail","skip","skip","skip"]`，`records[2:].fail_reason == "stopped_by_item_id=<id>"` |
| 不执行/不重试/不伪造输出 | ✅ | 同上：`execute_shell` 调用次数==2；skip 记录 `output` 为空 |
| 任务 completed、progress=100、pass_rate=50.0、C=N | ✅ | 同上：`task.status=="completed"`、`progress_percent==100`、记录数 5、`round(1/2*100,1)==50.0` |
| 覆盖 fail/error/timeout 三种触发 | ✅ | `test_stop_on_failure_all_trigger_kinds_fill_skip[fail/error/timeout]`：分别得 `[pass,<fail\|error\|timeout>,skip,skip,skip]`，completed/100、execute 次数 2 |
| 执行器无法启动/子进程启动失败 → error（非 fail） | ✅ | `test_real_adb_launch_failure_classified_internal_error_rc`（真实 ADBService → rc=-2）；`test_adb_shell_engine_internal_error_rc_is_error_not_fail` |
| 平台异常只存安全摘要，堆栈仅日志，200 详情不含原始异常文本 | ✅ | `test_platform_exception_record_fields_safe`、`test_task_error_message_persists_safe_summary`、`test_host_exec_launch_failure_is_error_and_canary_absent`（canary 不出现在 record.fail_reason/output、task.error_message） |
| repro stop 用例纳入永久回归（fail→pass） | ✅ | [../T-06/v1-targeted-3-cases.log](../T-06/v1-targeted-3-cases.log) 3 passed |
| 既有单测更严不放宽 | ✅ | 未修改既有断言；`test_task_executor.py` 全部通过 |
| 全量 pytest 0 failed（他人在途可 ignore 并说明） | ✅ | 358 passed / 0 failed / exit 0（排除说明见 §3 与 T-06 §2） |

## 5. 未验证项 / 限制

- 业务 `result=passed/failed` 与 pass_rate 的对外统一口径（任务详情/WS/报告/Dashboard）属 V1-06（T-07/T-08 聚合层，禁止改 `app/api/reports.py`、`websocket.py`、`schemas.py`）；本任务在记录层验证 50.0%。
- "取消、running 残留"由既有用例覆盖（`test_cancel_running_task_keeps_cancelled`、`test_startup_recovery.py`），本任务未新增。
- 严格全量当前受队友在途 `app/database.py`/`app/models`/`alembic`/`app/websocket.py` 的 SchemaMismatchError 影响（5 条），已说明并排除后复跑 0 failed；待相关任务完成后复跑严格命令。

## 6. 回退说明

无迁移/配置变更。回退：还原 `app/services/task_executor.py`、`execution_engine.py`、`device.py`、`judgement_engine.py` 并删除 `tests/unit/test_v1_judgement_stop.py`。回退后恢复"stop 只 break、无剩余 skip"与"执行器异常转 rc=-1 判 fail"的旧行为（不建议）。
