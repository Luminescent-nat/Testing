# T-06 补充（V1 readiness 修订）— 判定 fail-open 关闭 + 执行器安全异常摘要

- 关联：共享任务 task-10；审计 `docs/verification/reviews/RR-V1-READINESS-20261112.md` V1-02、V1-07（执行器部分）
- 复现源：`docs/verification/reviews/evidence/v1-readiness-20261112/targeted-defect-repro.py` L59-79（falsy_rules / approx_ratio_zero）
- 执行人：execution-engine；时间：2026-11-12T16:25～16:47 +08:00
- 环境：Windows / Python 3.12.10 / pytest 7.4.4；后端 `D:\MCTEST\test-platform\backend`；解释器 `D:\MCTEST\test-platform\.venv\Scripts\python.exe`
- 变更集：未 git commit。改动文件：`app/services/judgement_engine.py`、`app/services/execution_engine.py`、`app/services/task_executor.py`、`app/services/device.py`；新增 `tests/unit/test_v1_judgement_stop.py`

## 1. 修复内容（V1-02 / V1-07 执行器）

| 缺陷 | 修复 | 位置 |
|---|---|---|
| `conditional_rules=[]`/标量/null 被 `or {}` 归一化为空对象，随后 pass_pattern 判 pass（fail-open） | 在 `or {}` **之前**按原始 JSON 类型校验根结构：非 dict 一律 `error`（"判定配置不可用"）。judge() API 层对 `rules=None` 同样 error；`result_parse`/`rubric_criteria` 非法根结构同样 error。DB 列 NULL 表示"字段缺省/未配置规则"，显式映射为空对象走正则层（否则所有存量/种子项将全部 error）。 | `judgement_engine.py::JudgementEngine.judge`；`execution_engine.py::_judge_result`（原始类型校验在 `or {}` 前） |
| `approx_ratio` 零目标把偏差强制置 0 → pass | `_compare` 对零目标/非有限值返回 `False`；`judge_assertion` 对 `approx_ratio` 零目标、NaN/Inf、非数值比较运行时 `error` 兜底；rubric 基线非数值/零目标同样 error | `judgement_engine.py::_compare`、`judge_assertion`、`judge_rubric` |
| 非法正则/未知操作符/无法提取/非数值 → 曾回退默认 pass | 全部 `error`（"判定配置不可用"），不回退 pass | `judge_assertion` |
| `device.py` 把含子进程启动失败在内的异常转成 rc=-1 → 执行引擎按普通非零判 fail | 新增专用返回码 `INTERNAL_ERROR_RC=-2`（异常→rc 分类，**仅此一处**改动 device.py）；执行引擎据此判 **error**；异常摘要只含异常类型，`str(exc)`/堆栈不进入 stdout/stderr | `device.py`（`execute_shell`/`_run_adb_command`）；`execution_engine.py::AdbShellEngine/PushExecEngine`（rc==-2→error） |
| 平台异常把 `str(exc)` 持久化到 record.fail_reason / record.output / task.error_message（可在 200 任务详情返回） | 只持久化安全摘要（异常类型名），完整堆栈仅 `logger.exception` 进服务端日志；HostExecEngine 内部异常不再把 `str(e)` 写入 output/fail_reason | `task_executor.py`（`_execute_item`、`_run_task`）；`execution_engine.py::HostExecEngine` |

语义决策（请评审）：judge() 的 `rules=None` 按"非法根结构 → error"（满足审计 null 用例与 API 契约）；而 DB `conditional_rules` 列 NULL 视为"未配置规则"→ 走正则层。若把 DB NULL 也判 error，则存量样例项/种子项（`conditional_rules=NULL`+`pass_pattern`）全部 error，e2e 与任务执行整体失效，故二者区分处理。

## 2. 命令、退出码、原始日志

| 命令（workdir=backend） | 时间 | 退出码 | 日志 |
|---|---|---|---|
| 定向 3 用例：`pytest tests/unit/test_v1_judgement_stop.py::test_audit_falsy_invalid_rules_cannot_be_passed_by_pattern ::test_audit_approx_ratio_zero_target_cannot_pass ::test_audit_stop_on_failure_completes_remaining_items_as_skip -v -W error::pytest.PytestUnraisableExceptionWarning` | 16:46 | 0（3 passed） | [v1-targeted-3-cases.log](v1-targeted-3-cases.log) |
| 新文件全量：`pytest tests/unit/test_v1_judgement_stop.py -q -W error::pytest.PytestUnraisableExceptionWarning` | 16:45 | 0（32 passed） | 终端留痕 |
| 单元全量：`pytest tests/unit -q -W error::pytest.PytestUnraisableExceptionWarning` | 16:46 | 0（243 passed） | [v1-pytest-unit.log](v1-pytest-unit.log) |
| 严格全量：`pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning` | 16:39~16:42 | 1（7 failed / 362 passed） | [v1-pytest-full.log](v1-pytest-full.log)（失败证据保留） |
| 全量（排除队友在途）：同上 `--ignore=tests/integration/test_v1_authorization.py --ignore=tests/integration/test_websocket.py` | 16:43~16:45 | 0（**358 passed，0 failed**） | [v1-pytest-full-excluding-inflight.log](v1-pytest-full-excluding-inflight.log) |

严格全量的 7 failed 归因（见 [v1-pytest-full.log](v1-pytest-full.log)）：
- 5 条 `app.database.SchemaMismatchError`（`test_v1_authorization.py` 2 条、`test_websocket.py` 3 条）：来自其他任务在途的 `app/database.py`/`app/models`/`alembic` 与 `app/websocket.py` 改动（git status 显示 `M app/database.py`、`M app/models/__init__.py`、`M alembic/versions/...`、`M app/websocket.py`、`?? tests/integration/test_v1_authorization.py`），均不在本任务 scope，未改动；本任务文件不涉及 database/models/websocket。
- 2 条为本文件新增的日志断言（受整套运行全局 logging 影响，`caplog` 未采集），已改为对具体 logger `logger.exception` 打桩验证并复跑通过（见上，最终 358 passed）。

## 3. DoD 逐条证据

| DoD | 结论 | 证据 |
|---|---|---|
| ① `rules=[]`/标量/null 非法根结构 → error，不被 pass_pattern 变 pass | ✅ | `test_audit_falsy_invalid_rules_cannot_be_passed_by_pattern`（审计原样复现，rules=[]→error）；`test_illegal_rules_root_is_error_even_with_pass_pattern`（[]/非空数组/"str"/5/5.0/True/None 共 7 种 → error）；`test_illegal_result_parse_root_is_error`；`test_empty_dict_rules_still_route_to_pattern_layer`（合法空对象仍走正则层，既有语义保留） |
| ② approx_ratio target=0 禁止；_compare 返回 False；运行时 error 兜底 | ✅（写入拒绝属 app/api，见 §4） | `test_audit_approx_ratio_zero_target_cannot_pass`（`_compare(100,"approx_ratio",0,"0%") is False`）；`test_approx_ratio_zero_target_runtime_error`（target 0/0.0/"0"/"0.0"/spec:zero → error）；`test_approx_ratio_nonzero_target_still_works`（非零目标行为不变） |
| ③ 非法正则/未知操作符/无法提取/非数值 → error | ✅ | `test_illegal_regex_is_error`、`test_unknown_operator_is_error`、`test_extract_failure_is_error`、`test_non_numeric_comparison_is_error`、`test_nan_target_is_error` |
| ④ stop：第 2 项 fail+stop 后剩余 3 项补 skip（stopped_by_item_id），不执行/不重试/不伪造输出；5 记录 pass,fail,skip,skip,skip；completed/100/pass_rate=50.0；fail/error/timeout 触发 | ✅ | `test_audit_stop_on_failure_completes_remaining_items_as_skip`（审计原样复现 + execute 次数=2、reason==`stopped_by_item_id=<id>`、skip 无 output、pass_rate=50.0）；`test_stop_on_failure_all_trigger_kinds_fill_skip[fail/error/timeout]` |
| ⑤ 执行器无法启动/子进程启动失败 → error（非 fail）；平台异常只存安全摘要，细节仅日志，200 详情不含原始异常文本 | ✅ | `test_real_adb_launch_failure_classified_internal_error_rc`（真实 ADBService 路径 → rc=INTERNAL_ERROR_RC、摘要无 canary）；`test_adb_shell_engine_internal_error_rc_is_error_not_fail`；`test_host_exec_launch_failure_is_error_and_canary_absent`；`test_platform_exception_record_fields_safe`（record.fail_reason/output 与 task.error_message 无 canary）；`test_task_error_message_persists_safe_summary` |
| 将 repro 三条用例纳入 `tests/unit/test_v1_judgement_stop.py`（fail→pass，永久回归） | ✅ | 见 [v1-targeted-3-cases.log](v1-targeted-3-cases.log) 3 passed |
| 既有单测更严不放宽 | ✅ | 本轮未修改任何既有单测断言（仅新增 `test_v1_judgement_stop.py` 与业务实现）；既有 35+ 判定/执行器用例保持通过 |
| 全量 pytest 0 failed（他人在途可 ignore 并说明） | ✅ | 排除 2 个队友在途文件后 358 passed / 0 failed / exit 0（见 §2） |

## 4. 未验证项 / 限制

- **写入侧拒绝**（`conditional_rules=[]`/标量、`approx_ratio` 零目标、NaN/Inf 的 400 拒绝）位于 `app/api/*` 与 `app/schemas.py`，属本任务 **禁止改动范围**，由 API 层任务负责；本任务只保证运行时 `error` 兜底（失败关闭）。
- "API 落库测试"（审计 V1-02 提及）同属 API 层，不在本任务测试文件范围。
- pass_rate=50.0 在记录层测算（pass/(pass+fail+error+timeout)）；报告/WS/Dashboard 的统一聚合口径属 V1-06（T-07/T-08 其它范围），本任务未改 `app/api/reports.py`、`websocket.py`。
- V1-03 附带要求的"取消、running 残留"由既有用例覆盖（`test_cancel_running_task_keeps_cancelled`、`test_startup_recovery`）；"平台异常"由本文件 canary 用例覆盖。
- 严格全量当前受队友在途 `database.py/models/alembic/websocket.py` 的 SchemaMismatchError 影响（5 条），已说明并按上述 `--ignore` 复跑达成 0 failed；待相关任务完成后应复跑严格命令。
- 副作用提示：`knowledge_converter.py` 目前会把 `conditional_rules` 写成 list 根结构；该结构在本契约下运行时将判 `error`（失败关闭正确），写入侧应改为对象或拒绝——属知识转换任务范围，本任务未改该文件。

## 5. 回退说明

无迁移/配置变更。回退：还原 `app/services/judgement_engine.py`、`execution_engine.py`、`task_executor.py`、`device.py` 四个文件并删除 `tests/unit/test_v1_judgement_stop.py` 即可；回退后恢复旧 fail-open / stop 伪收尾 / 原始异常落库行为（不建议）。
