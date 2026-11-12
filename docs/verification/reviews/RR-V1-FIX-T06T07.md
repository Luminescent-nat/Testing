# RR-V1-FIX-T06T07：V1-02/V1-03/V1-07 判定 fail-open、stop 收尾、执行器异常（task-10）

- 评审编号：RR-V1-FIX-T06T07
- 评审对象/任务编号：task-10（V1-02/V1-03/V1-07 执行器部分；对应 T-06/T-07）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/design/execution-state-machine.md` v1.0 §2 行2/行11、§4 stop-on-failure、`RR-V1-READINESS-20261112.md` V1-02/V1-03/V1-07、`targeted-defect-repro.py` R3/R4/R5、`verification-rules-v1.0.md` §4
- 环境与 commit/变更集：Windows 10；Python 3.12.10；git HEAD `fa70d3b` + 工作区（task-10 未提交）。变更：`app/services/judgement_engine.py`、`execution_engine.py`、`task_executor.py`、`device.py`（仅异常→rc 分类）、新增 `tests/unit/test_v1_judgement_stop.py`（32 项）
- 证据路径：`docs/verification/tasks/T-06/V1-followup-result.md`、`T-07/result.md`、`T-06/v1-targeted-3-cases.log`；评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-fix-t06t07-unit-reviewer.log`（67 passed）、`v1-repro-R3R4R5-after-task10.log`（3 passed）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | ① rules=[]/标量/null 在 `or {}` 前被原始类型校验→error | 读 judgement_engine.py:641-662（judge 前置 `not isinstance(rules,dict)`→error，先于 result_parse 处理）；execution_engine.py:_judge_result 原始类型校验（raw_rules/rubric/result_parse `is not None and not dict`→error，在 `or {}` 前） | 反例 R3 rules=[]→error（独立重跑 PASS）；单测 test_illegal_rules_root_is_error_even_with_pass_pattern 覆盖 []/"str"/5/5.0/True/None 七种 | 通过 |
| 2 | ① 决策合理性：judge API None→error vs DB NULL→正则层 | 读代码 + 状态机 §2 | 见 §2 P-V1T06-1 评估：**合理且与状态机不矛盾**（NULL=字段缺省未配置→无断言规则走正则/pass_pattern 有效判定层；显式非法根结构=输入错误→error；空规则+空pattern 最终 error 失败关闭） | 通过（附评估） |
| 3 | ② approx_ratio 零目标→error / _compare False | 读 judgement_engine.py:486-497（零/非有限→False）、judge_assertion 前置 math.isfinite + 零目标 error | 反例 R4 `_compare(100,approx_ratio,0,0%) is False`（PASS）；单测 zero target 0/0.0/"0"/"0.0"/spec:zero→error；非零目标不变 | 通过 |
| 4 | ② NaN/Inf/非数值→error | 读 judge_assertion:231-247（非数值/非有限→error）；rubric 基线非数值/零目标→error | 单测 test_non_numeric_comparison_is_error / test_nan_target_is_error / 非法正则/未知操作符/无法提取→error | 通过 |
| 5 | ③ stop 三触发补 skip、reason stopped_by_item_id、C=5、progress100、pass_rate50 | 读 task_executor.py:_skip_remaining_items + break 前调用；单测 | 反例 R5 [pass,fail,skip,skip,skip]（PASS）；单测 all_trigger_kinds fail/error/timeout 均补 skip；execute 调用 2 次、skip 无 output、pass_rate=50.0 | 通过 |
| 6 | ④ 执行器启动失败→error（INTERNAL_ERROR_RC=-2） | 读 device.py:INTERNAL_ERROR_RC=-2 + 异常分支返回 -2+安全摘要；execution_engine rc==-2→error | 单测 test_real_adb_launch_failure_classified_internal_error_rc（rc=-2、无 canary）；adb shell engine rc=-2→error not fail | 通过 |
| 7 | ④ 平台异常只存安全摘要、详情无 str(exc) canary | 读 task_executor 异常分支/device/execution_engine HostExec 只存异常类型名，堆栈仅 logger.exception；单测 canary | test_platform_exception_record_fields_safe（record.fail_reason/output/task.error_message 无 canary）、test_host_exec_launch_failure_is_error_and_canary_absent、test_task_error_message_persists_safe_summary | 通过 |
| 8 | repro R3/R4/R5 转 PASS（永久回归） | 独立重跑 3 项（shim 插件方式） | **3 passed, 3 deselected, exit 0** | 通过 |
| 9 | 新增用例真实执行无 skip | 独立重跑 test_v1_judgement_stop + judgement/execution/task_executor | **67 passed**（32 新 + 35 既有），无 skip | 通过 |
| 10 | 既有单测未放宽 | git diff 测试文件 | 未修改既有测试断言，仅新增文件 | 通过 |

## 2. 关键语义决策评估（①）

**决策**：`judge(rules=None)`（API 显式传入）→ error；DB `conditional_rules` 列 NULL（字段缺省）→ 视为 `{}` 走正则/`pass_pattern` 层。

**评审意见：合理，且与状态机一致，不冲突。**
- 状态机 §2 行11「无判定配置/空规则/…→error」指的是**没有任何有效判定配置**。一个项若有 `result_parse.pass_pattern`（正则模式，行 6/7 的合法判据），就**不是**"无判定配置"；DB NULL 仅表示"未配置 conditional_rules 断言规则"，不是非法输入。
- 显式 `[]`/标量/`None`（API/导入写入）属**非法根结构**（契约要求对象），必须 error，且不得被 `or {}`（truthiness）擦成空对象后经 pass_pattern 变 pass——这正是 V1-02 的 fail-open 漏洞，已关闭。
- 失败关闭完整性：空 rules（`{}`）+ 空 result_parse（无 pass/fail pattern）时 `parse_patterns` 返回 `_unavailable` → error；因此"真·无配置"仍 error，不 fail-open。单测 `test_empty_dict_rules_still_route_to_pattern_layer`（有 pass_pattern）与 `parse_patterns` 空配置路径共同印证。
- 残余风险：若 API 层仍允许把 `[]/标量/null` 写入 DB（写入侧校验属 API/schemas，本轮未做，见 L1），运行时对此类 DB 值会 error（失败关闭，安全，不 fail-open）。属"应写入拒绝但运行时兜底"的守门，列入后续 API 任务。

## 3. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V1T06-1 | 写入侧 400 拒绝（conditional_rules=[]/标量/null、approx_ratio 零目标、NaN/Inf）未实现，仅运行时 error 兜底 | V1-followup §4；task-10 禁止改 app/api/schemas | 非法配置仍可能进库，但运行时失败关闭（安全）；契约"写入前 400"未满足 | 中（范围外） | API/schemas 后续任务（T-09/T-15） |
| P-V1T06-2 | pass_rate=50.0 在记录层测算；报告/WS/Dashboard 统一聚合口径属 V1-06（T-07/T-08 其它范围） | V1-followup §4；T-07 §5 | 对外统一 result/pass_rate 未在本任务闭环 | 中（V1-06） | T-08 |
| P-V1T06-3 | knowledge_converter 仍可能把 conditional_rules 写成 list；本契约下运行时 error（失败关闭正确），写入侧应改/拒绝 | V1-followup §4 副作用提示 | 转换写入的非法结构运行时报 error（不 fail-open），但需写入修复 | 低-中 | T-15 |

## 4. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 写入侧（app/api/schemas）400 拒绝 | 不在 task-10 write scope | 运行时 error 兜底已具备；写入校验待后续 API 任务 |
| L2 | 严格全量当前 7 failed 均为队友在途 database/models/websocket 的 SchemaMismatchError | 非 task-10 文件；已 --ignore 复跑 358 passed | 全量以 Lead 最终严格日志为准 |
| L3 | 报告/WS/Dashboard result/pass_rate 对外口径 | 属 V1-06（T-08） | 未在本任务闭环 |

## 5. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| repro R3/R4/R5（shim 插件，临时库） | **3 passed / 3 deselected** | 0 | `evidence/v1-fix-20261112/v1-repro-R3R4R5-after-task10.log` |
| `pytest tests/unit/test_v1_judgement_stop.py + test_judgement_engine + test_execution_engine + test_task_executor` | **67 passed**（32 新+35 既有） | 0 | `evidence/v1-fix-20261112/v1-fix-t06t07-unit-reviewer.log` |
| 开发证据：严格全量 | 362 passed / 7 failed（均队友在途） | 1 | `docs/verification/tasks/T-06/v1-pytest-full.log` |
| 开发证据：排除在途 | 358 passed / 0 failed | 0 | `docs/verification/tasks/T-06/v1-pytest-full-excluding-inflight.log` |
| 最终严格全量 | 待 Lead 最终日志，届时补记 | — | — |

## 6. 最终结论

**通过（V1-02/V1-03/V1-07 执行器范围内）。** 三条定向反例 R3/R4/R5 已由 FAILED 转 **PASS**（独立重跑 3 passed）；判定根结构在 `or {}` 前按原始类型校验→error、approx_ratio 零目标/NaN/Inf/非数值→error 且 `_compare` 返回 False；stop 三触发均补 3 skip（reason `stopped_by_item_id`）、C=N=5、progress=100、pass_rate=50.0；执行器启动失败→error（INTERNAL_ERROR_RC=-2）、平台异常只存安全摘要且 200 详情无 `str(exc)` canary。新增 32 用例真实执行，独立重跑 67 passed。①「judge None→error / DB NULL→正则层」区分经评估**合理且与状态机一致**。限制：写入侧 400 拒绝（P-V1T06-1）、统一聚合口径（P-V1T06-2/V1-06）、knowledge_converter 写入（P-V1T06-3）为范围外后续任务；严格全量以 Lead 最终日志为准（当前 7 failed 均队友在途 SchemaMismatch，非本任务）。

## 7. 签名

reviewer，2026-11-12；本记录基于源码 diff、单测与独立反例重跑日志作出，未替开发修改任何代码。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
