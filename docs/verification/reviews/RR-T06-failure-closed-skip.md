# RR-T06：失败关闭与原生 SKIP 判定

- 评审编号：RR-T06
- 评审对象/任务编号：T-06（task-2，owner execution-engine）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/design/execution-state-machine.md` v1.0 §1-2（状态集合、判定优先级 11 行、SKIP 行规则）、§4（stop-on-failure）、`docs/verification/verification-rules-v1.0.md` §4（EXEC-01～05、SKIP-01～02）、`docs/plan/task-board-v1.0.md` T-06
- 环境与 commit/变更集：Windows 10，Python 3.12.10，pytest 7.4.4 / pytest-asyncio 0.23.3；git HEAD `d0b415d` + 工作区。T-06 变更：`app/services/judgement_engine.py`（重写）、`app/services/execution_engine.py`、`app/services/task_executor.py`（仅注释+防御映射）、`tests/unit/test_judgement_engine.py`（2 条语义更新）、新增 `tests/unit/test_execution_failure_closed.py`；未触碰 docs/plan、main.py、test-tools、frontend、conftest、llm_client
- 证据路径：
  - 开发证据：`docs/verification/tasks/T-06/`（result.md、pytest-full.log（失败保留）、pytest-full-excluding-other-teammates-inflight.log、pytest-unit.log）
  - 评审方独立重跑：`docs/verification/reviews/evidence/test-rerun-20261112/backend-targeted-t06-reviewer.log`

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | 状态机 §2 行3：rc!=0 → fail（即使 SKIP/pass_pattern），reason 含退出码 | judgement_engine.py:598-606；test_exec01 三条 | fail 优先于一切输出判定，reason 含退出码 | 通过 |
| 2 | 行4：rc=0 独立整行原生 SKIP → skip，原因贯通 | judgement_engine.py:608-617；find_native_skip:31-45；test_skip01 系列 | skip 优先于 fail_pattern/双命中；fail_reason 保存原因 | 通过 |
| 3 | 行5：fail_pattern 命中或双命中 → fail | judgement_engine.py:619-633；parse_patterns:99-108；test_exec03 双命中、test_skip02_native_skip_beats_fail_pattern | 双命中 fail、skip 优先于 fail_pattern | 通过 |
| 4 | 行6/7：assertion true→pass / false→fail（未满足断言） | judge_assertion:205-255；test_truth_table_assertion_* | false→fail 并指出未满足断言 | 通过 |
| 5 | 行8/9：rubric 达阈 pass / 低于 fail | judge_rubric:257-358；test_truth_table_rubric_* | 与既有 test_rubric_scoring_pass/fail 一致 | 通过 |
| 6 | 行10/11：ai_fallback 明确 pass/fail→对应；无结论/unknown/skip/异常→error | AIJudger:518-565；test_truth_table_ai_*、test_exec04_ai_* | AI 返回 skip 落 error 不落 skip；unknown 不再产出 | 通过 |
| 7 | 行11：无配置/空规则/未知操作符/非法正则/结构非法/无法提取→error 绝不 pass | _unavailable:59-68；test_exec04 系列、test_fail_pattern_only_without_hit_is_error | 各失败关闭分支均 error 且 reason 标"判定配置不可用" | 通过 |
| 8 | 行1 timeout / 行2 内部异常→error | execution_engine.py HostExec 内部异常直接落 error（629-637）；test_exec05_timeout_is_timeout、test_exec05_subprocess_start_error_is_error、test_exec05_adb_shell_exception_maps_to_error_record | timeout 保持；执行器异常不再伪装 rc=-1 进判定 | 通过 |
| 9 | 原生 SKIP 正则只接受独立整行、大小写敏感、8 组反例 | find_native_skip 逐行 strip 后全等/前缀；test_skip02_not_native_skip（8 组参数化） | `foo RESULT: SKIP`、`RESULT: SKIPPED(:reason)`、`RESULT: skip`、`result: skip: reason`、中英文自然语言均不误判 | 通过 |
| 10 | SKIP 原因贯通 record | test_skip01_reason_persists_to_record | record.fail_reason=="设备无电池" | 通过（DB 层；报告/WS 见 L1） |
| 11 | 移除 rc=0 默认 pass 与 unknown | parse_result:159-178 委托 parse_patterns；test_exec02_parse_result_no_longer_returns_unknown | parse_result 不再产出 unknown、不再默认 pass | 通过 |
| 12 | 2 条旧单测语义更新是否为契约变更而非放宽 | git diff test_judgement_engine.py | ①default_returncode(pass→error，重命名 no_config_is_error)+reason 断言；②ai_fallback(unknown→error)保留 fail_reason 断言。均为**更严**（pass/unknown→error），符合已确认状态机"禁止 unknown 落库、无配置绝不 pass"；非放宽 | 通过 |
| 13 | 45 项新增用例真实执行、无 skip | grep 无 mark.skip/xfail/pytest.skip；独立重跑 80 passed（45 新 + 35 既有） | 全部真实断言执行 | 通过 |
| 14 | skip 不触发 stop-on-failure | test_skip_does_not_trigger_stop_on_failure | 第1项 skip、第2项继续执行 | 通过 |
| 15 | 只改声明 scope | git diff/status | task_executor.py 仅注释+防御映射（越界状态→error）；无其它文件 | 通过 |
| 16 | 独立重跑 T-06 定向 | pytest test_execution_failure_closed + judgement/execution/task_executor | **80 passed**，exit 0 | 通过 |

## 2. 问题与风险等级

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-T06-1 | **状态机未定义处的保守实现**：「fail_pattern 全局（行5）在 rubric/ai_fallback 等任意 judgement_type 下命中即 fail；pass_pattern 仅参与 assertion 正则层（行6/7）」。混合配置（如 rubric+pass_pattern）语义状态机未定义，实现取保守并以真值表测试固定 | result.md §5.5；judgement_engine.py:619-633（fail_pattern 先于类型分派）、:639-644（pass_pattern 只在 assertion 分支） | 混合配置行为有解释空间；保守=不会误 pass，但可能对 rubric+pass_pattern 配置多判 fail | 低-中 | **建议列待用户确认（U-T06-1）**；记录已充分（result.md §5 + 代码注释 + 真值表测试） |
| P-T06-2 | 「仅 fail_pattern 且未命中 → error」为行11 的解释性归类（状态机未逐字列出该场景） | result.md §5.2（Lead 确认决策2）；test_fail_pattern_only_without_hit_is_error | 归 error 而非 fail；失败关闭方向正确，但属解释性决策 | 低 | 已 Lead 确认；一并报用户备案 |

## 3. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | SKIP 原因「贯通报告/WS」仅为**代码级 + record(DB) 层**核对：报告读 `record.fail_reason`（reports.py:248,52,1384 等）、WS 读 `record.fail_reason`（websocket.py:100），本次未改动即贯通，但**未新增 API/WS 端到端断言** | 相应文件不在 T-06 write_scopes；report/WS/前端三层属后续验收 | 验证规则 §4「服务层、API/WS、报告三层」中 API/WS/报告与前端渲染层**未验证**，留 T-08/T-22+ 与最终验收 |
| L2 | 全量回归口径：开发阶段 `281 passed` 为 `--ignore=test_secret_strength.py --ignore=test_tool_manifest.py` 的结果（当时两 infra 文件在途）；**全部任务完成后评审方独立严格全量 `pytest tests` = 310 passed / 0 failed（12:25）**，Lead 最终日志 `docs/verification/tasks/FULL-REGRESSION-final-20261112.log` 亦 310 passed（135.09s）。此前 transient collection errors 来自队友在途文件，非 T-06 缺陷 | pytest-full.log；独立全量日志 | 已闭环：最终严格全量 0 failed |
| L3 | README.md「AI fallback 降级返回 unknown」文档过时未更新 | 不在 T-06 scope | 文档不一致，待 T-37 收口 |

## 4. 待用户确认项

| # | 事项 | 建议 |
|---|---|---|
| U-T06-1 | fail_pattern 全局 / pass_pattern 仅 assertion 层（混合配置语义） | 请用户备案或修订：确认保守实现（fail_pattern 任意类型命中即 fail、pass_pattern 只约束 assertion），或在状态机补写混合配置规则 |
| U-T06-2 | 「仅 fail_pattern 未命中→error」归类 | 备案（已 Lead 确认）；如需归 fail 请修订状态机 |

## 5. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest tests/unit/test_execution_failure_closed.py tests/unit/test_judgement_engine.py tests/unit/test_execution_engine.py tests/unit/test_task_executor.py -q -W error::pytest.PytestUnraisableExceptionWarning` | **80 passed**（45 新 + 35 既有），无 skip | 0 | `evidence/test-rerun-20261112/backend-targeted-t06-reviewer.log` |
| 开发证据对照：pytest-full-excluding-*.log | 281 passed（--ignore 2 infra 在途） | 0 | `docs/verification/tasks/T-06/` |
| 开发证据对照：pytest-full.log | 2 collection errors（队友在途文件，失败日志保留） | 2 | `docs/verification/tasks/T-06/pytest-full.log` |
| 严格全量 `pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA`（评审方独立，全部任务完成后） | **310 passed / 0 failed** | 0 | `evidence/test-rerun-20261112/backend-final-full-regression-reviewer.log` |
| Lead 最终全量日志 | 310 passed（135.09s） | 0 | `docs/verification/tasks/FULL-REGRESSION-final-20261112.log` |

## 6. 最终结论

**通过（T-06 范围内 DoD 达成）。** 状态机 §2 行3～行11 判定优先级逐条落地：rc!=0 优先于 SKIP/pass_pattern、原生 SKIP 优先于 fail_pattern/双命中、pass_pattern 未命中→fail、assertion false→fail、rubric 阈值、ai_fallback 仅明确 pass/fail、无配置/空规则/未知操作符/无法提取/AI 无结论→error；不再产出 unknown、不再 rc=0 默认 pass。原生 SKIP 仅认独立整行 `RESULT: SKIP[:原因]`（8 组反例全过）、原因贯通 record。2 条旧单测为**更严的契约变更**（pass/unknown→error），非放宽；45 项新增用例真实执行无 skip；独立定向重跑 80 passed、退出码 0。限制：报告/WS「贯通」为代码级+record 层核对，API/WS/报告三层与前端渲染未做端到端（L1）；全量口径待 Lead 统一严格全量后补记（L2）。P-T06-1/2 的状态机未定义处保守实现已充分记录，列 U-T06-1/2 待用户备案/修订，不阻塞本任务结论。

## 7. 签名

reviewer，2026-11-12；本记录基于源码、diff、测试真值表与独立重跑日志作出，未替开发修改任何代码。
