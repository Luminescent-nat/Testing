# T-06 落地失败关闭与原生 SKIP 判定 — result.md

- 任务：task-2（共享任务板，owner：execution-engine）
- 执行人：execution-engine（Agent Team）
- 开始：2026-11-12T11:40+08:00；结束：2026-11-12T12:10+08:00
- 环境：Windows（Python 3.12.10，pytest 7.4.4，pytest-asyncio 0.23.3），工作目录 `D:\MCTEST`，后端 `D:\MCTEST\test-platform\backend`
- 解释器：`D:\MCTEST\test-platform\.venv\Scripts\python.exe`
- 变更集：本任务未 git commit（按委派要求）；变更文件见下节，可用 `git diff -- test-platform/backend/app/services/judgement_engine.py test-platform/backend/app/services/execution_engine.py test-platform/backend/app/services/task_executor.py test-platform/backend/tests/unit/test_judgement_engine.py` 复核；新增文件 `tests/unit/test_execution_failure_closed.py`

## 1. 变更文件（均在 write_scopes 内）

| 文件 | 变更 |
|---|---|
| `app/services/judgement_engine.py` | 重写为唯一判定入口：`JudgementEngine.judge` 实现状态机 §2 行3～行11（rc!=0 fail → 原生 SKIP skip → fail_pattern/双命中 fail → assertion → rubric → ai_fallback → 无配置/空规则/非法规则=error）；新增 `find_native_skip`（独立整行 `RESULT: SKIP[:原因]`，大小写敏感）、`parse_patterns`、`extract_fail_reason`；`judge_assertion`/`judge_rubric` 的 None→默认pass 路径全部改为 error（无法提取/未知操作符/非法正则/结构非法）；`AIJudger` 把 LLM schema 返回的 unknown/skip/缺字段/异常一律映射 error；`JudgementResult.status` 不再产出 unknown |
| `app/services/execution_engine.py` | `parse_result` 委托 `parse_patterns`（不再返回 unknown、不再 rc=0 默认 pass）；`_judge_result` 重写：ADB 设备级失败特化（rc!=0 → fail 含退出码+ADB 归因；rc=0 时原生 SKIP（行4）先于内置失败模式（行5）），其余行3～行11 交由 `JudgementEngine.judge`；`HostExecEngine` 内部异常（含子进程无法启动）改为直接落 error（行2），不再伪装 returncode=-1 进入判定 |
| `app/services/task_executor.py` | 仅更新 `_execute_item` 中状态白名单映射的注释（引擎不再产出 unknown；保留防御性映射越界→error）。stop-on-failure 判定（fail/error/timeout）与重试逻辑未改，skip 天然不触发 stop |
| `tests/unit/test_judgement_engine.py` | 按新契约更新 2 条旧语义用例（见 §4），其余断言未放宽 |
| `tests/unit/test_execution_failure_closed.py` | 新增 45 项：EXEC-01～05、SKIP-01（含原因落 record 断言）、SKIP-02 真值表（8 组反例参数化 + 优先级交叉）、状态机 §2 关键行真值表补充、skip 不触发 stop-on-failure |
| `docs/verification/tasks/T-06/*.log`、本文件 | 证据 |

未触碰：`docs/plan`、`main.py`、`test-tools`、frontend、`conftest.py`、`llm_client.py` 及其他队友文件。

## 2. 命令、退出码与原始日志

| # | 命令（在 `test-platform/backend`） | 时间 | 退出码 | 日志 |
|---|---|---|---|---|
| 1 | `python -m pytest tests/unit/test_judgement_engine.py tests/unit/test_execution_engine.py tests/unit/test_task_executor.py -q -W error::pytest.PytestUnraisableExceptionWarning`（改造后聚焦回归） | 12:0x | 0（35 passed） | 终端留痕（未存档，结果与 #3 一致） |
| 2 | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning`（严格全量） | 12:06:03 起 | 2（收集阶段 2 errors） | [pytest-full.log](pytest-full.log)（失败证据，保留） |
| 3 | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning --ignore=tests/unit/test_secret_strength.py --ignore=tests/unit/test_tool_manifest.py` | 12:06~12:08 | 0（**281 passed，0 failed**） | [pytest-full-excluding-other-teammates-inflight.log](pytest-full-excluding-other-teammates-inflight.log) |
| 4 | `python -m pytest tests/unit -q -W error::pytest.PytestUnraisableExceptionWarning --ignore=tests/unit/test_secret_strength.py --ignore=tests/unit/test_tool_manifest.py`（聚焦） | 12:09 | 0（**163 passed**） | [pytest-unit.log](pytest-unit.log) |

**失败日志说明**：#2 的 2 个收集错误全部来自其他队友的在途未完成文件（untracked）：`tests/unit/test_secret_strength.py`（`app.config.SECRET_KEY_MIN_LENGTH` 尚未实现）、`tests/unit/test_tool_manifest.py`（`app.services.tool_manifest` 模块尚未创建）。二者均不在本任务 scope，不能修改/删除；已按“失败日志保留并追加修复日志”原则保留 #2 原始日志，并以 `--ignore` 排除该 2 个无关模块后追加 #3/#4 新日志。待相应任务完成后可用严格命令复跑。

## 3. DoD 逐条证据

| DoD | 结论 | 证据 |
|---|---|---|
| 按状态机 §2 优先级实现唯一判定（timeout > 内部异常 error > rc!=0 fail > 原生 SKIP > fail_pattern/双命中 > assertion > rubric > ai_fallback > 无配置=error） | ✅ | `judgement_engine.py::JudgementEngine.judge`（行3～行11）+ `execution_engine.py::_judge_result`（行1/2/ADB 特化）；真值表测试 `test_truth_table_*`、`test_exec01_*`（rc 优先）、`test_skip02_native_skip_beats_fail_pattern`（行4>行5）、`test_skip01_skip_beats_pass_pattern`（行4>行6） |
| timeout 最高、内部异常→error | ✅ | `test_exec05_timeout_is_timeout`（timeout）、`test_exec05_subprocess_start_error_is_error`（HostExec 内部异常→error）、`test_exec05_adb_shell_exception_maps_to_error_record`（TaskExecutor 层 error）；既有 `test_host_exec_engine_timeout` 未改动仍通过 |
| rc!=0 → fail，即使输出含 SKIP/pass_pattern，reason 含退出码 | ✅ | `test_exec01_nonzero_rc_with_pass_and_skip_is_fail_engine` / `test_exec01_nonzero_rc_with_pass_pattern_is_fail_judge` / `test_exec01_nonzero_rc_with_skip_line_is_fail_judge`（断言退出码数字出现在 reason） |
| rc=0 独立整行原生 SKIP → skip，原因贯通 record/报告/WS | ✅ | `find_native_skip`（`test_skip01_find_native_skip_reason`）；engine 层 `test_skip01_engine_skip_with_reason`；record 层 `test_skip01_reason_persists_to_record`（`record.fail_reason == "设备无电池"`）。报告/WS 读取 `record.fail_reason` 的链路为既有代码（`app/api/reports.py` L248/`_build_verdict_basis` skip 分支、`app/websocket.py` L100），本次未改动即贯通；代码级核对确认不丢失 |
| SKIP-02：`foo RESULT: SKIP`、`RESULT: SKIPPED`、自然语言、大小写不误判 | ✅ | `test_skip02_not_native_skip`（8 组参数化反例）、`test_skip02_skipped_word_is_not_skip_but_fail`、`test_skip02_embedded_phrase_is_not_skip_but_error` |
| fail_pattern 命中或双命中 → fail | ✅ | `test_exec03_both_patterns_hit_is_fail_judge/_engine` |
| 移除 rc=0 默认 pass、unknown 语义 | ✅ | `parse_result` 不再产出 unknown（`test_exec02_parse_result_no_longer_returns_unknown`）；无配置 → error（`test_exec04_no_config_is_error`、`test_judgement_engine_no_config_is_error`）；AI unknown/异常 → error（`test_exec04_ai_no_conclusion_is_error`、`test_exec04_ai_exception_is_error`、`test_ai_fallback_without_llm` 更新后通过） |
| assertion：true→pass；false→fail；无法提取/未知操作符/非法正则/结构非法→error（不回退默认 pass） | ✅ | `test_truth_table_assertion_true_pass`、`test_truth_table_assertion_false_fail`（reason 含“未满足断言”）、`test_exec04_assertion_extract_failure_is_error_not_default_pass`、`test_exec04_unknown_operator_is_error`、`test_exec04_illegal_regex_is_error`、`test_exec04_illegal_structure_is_error`；既有 `test_rule_assertion_gt_fail`、`test_rule_assertion_approx_ratio`（false→fail 断言）未改动仍通过 |
| rubric：达阈值 pass / 低于 fail / 无有效评分 error | ✅ | `test_truth_table_rubric_above_threshold_pass` / `_below_threshold_fail` / `_no_valid_score_error`；既有 `test_rubric_scoring_pass/_fail` 未改动仍通过 |
| ai_fallback：明确 pass/fail → 对应结果；无有效结论/异常 → error | ✅ | `test_truth_table_ai_explicit_pass` / `_explicit_fail` / `_ai_skip_status_is_error_not_skip` |
| pass_pattern 未命中 → fail | ✅ | EXEC-02 三条 |
| （Lead 确认决策）仅 fail_pattern 且未命中（无正向通过判据）→ error，reason 标明判定配置不可用 | ✅ | `test_fail_pattern_only_without_hit_is_error`（显式用例，见 §5 决策 2） |
| skip 不触发 stop-on-failure | ✅ | `test_skip_does_not_trigger_stop_on_failure`（第 1 项 skip + on_failure=stop，第 2 项仍执行且 pass，execute_shell 调用 2 次）；未实现 T-07 的剩余项补 skip 收尾（不在范围，现行为未破坏） |
| 新增 `tests/unit/test_execution_failure_closed.py` 覆盖 EXEC-01～05、SKIP-01～02 | ✅ | 45 项全部通过（日志 #3/#4） |
| 更新旧“默认 pass/unknown”既有单测为新契约（不放宽） | ✅ | 见 §4，共 2 条，逐条说明 |
| 全量回归 0 failed、总数 ≥ 189+新增 | ✅ | 281 collected / 281 passed / 0 failed / 0 error（≥ 234）；严格命令当前被 2 个队友在途文件阻塞，已排除并留证（见 §2） |
| 未改 scope 外文件、未 commit、未跳过/删除测试 | ✅ | `git status` 复核：本任务仅触碰 §1 列表文件；未执行 git commit；无 skip/删除 |

## 4. 既有单测更新说明（逐条）

1. `test_judgement_engine_default_returncode` → 重命名 `test_judgement_engine_no_config_is_error`：旧断言“空规则 + rc=0 → pass”（旧默认 pass 语义）。新契约无判定配置落 error，断言改为 `status == "error"` 且 reason 含“判定配置不可用”——更严（pass→非 pass），未放宽。
2. `test_ai_fallback_without_llm`：旧断言 LLM 未配置时 `status == "unknown"`。新契约 unknown 不再产出，断言改为 `status == "error"`，保留“LLM API Key 未配置” 出现在 fail_reason 的断言——更严，未放宽。

其余既有用例（含 `test_judgement_engine_default_returncode_fail`、`test_rule_assertion_returncode_nonzero`、`test_rule_assertion_gt_fail`、`test_rule_assertion_approx_ratio`、`test_rubric_*`、`test_execution_engine.py`、`test_task_executor.py` 全部）断言未做任何改动，在新契约下直接通过。

## 5. 关键语义决策（均经 Lead 确认）

1. **assertion 条件完整执行且为 false → fail**（reason 指出未满足断言），与 pass_pattern 未命中对称；委派文字中“false→error”系笔误，以状态机文档 §2 行7 为准。error 仅用于“无法提取/未知操作符/非法正则/结构非法/AI 无有效结论/无判定配置”。
2. **rc=0、仅配置 fail_pattern 且未命中 → error**（reason 标明“判定配置不可用”，归 §2 行11）：移除 rc=0 默认 pass 后该配置无正向通过判据，失败关闭不许默认 pass；已配置 pass_pattern 但未命中 → fail（EXEC-02）。
3. **AI 判定**：schema 允许 unknown/skip，但仅“明确 pass/fail”有效；unknown/skip/缺字段/异常一律 error。`llm_client.py` 的 `JUDGEMENT_SCHEMA` 枚举未改（不在 write_scopes），映射在 `AIJudger` 就地完成。
4. **ADB 设备级失败特化保留**：rc!=0 命中 ADB 模式 → fail（reason 含 ADB 归因与退出码，兼容既有 `test_adb_shell_engine_adb_device_not_found`）；rc=0 命中 → 原生 SKIP（行4）优先，否则按内置失败模式 fail（行5）。
5. **fail_pattern 全局（行5）**：在 rubric/ai_fallback 等任意 judgement_type 下命中均 fail；pass_pattern 仅参与 assertion 正则模式层（行6/7），避免与 rubric/AI 判据互相覆盖（混合配置场景状态机未定义，取保守实现并在真值表测试中固定）。

## 6. 未验证项 / 限制

- 严格 `python -m pytest tests -q` 当前因其他队友 2 个在途文件收集失败而无法原样跑通（见 §2），已用 `--ignore` 排除后达成 0 failed；待该任务完成后建议复跑严格命令。
- SKIP 原因贯通已在 record（DB）层断言；报告/WS 层依赖既有读取 `record.fail_reason` 的代码（未改动），未新增 API/WS 端到端断言（相应文件不在本任务 write_scopes）。
- `docs/verification/rules` 中 EXEC/SKIP 场景的“服务层、API/WS 和报告三层”覆盖，本任务完成服务层/引擎层/record 层；API/WS/报告三层与前端渲染属后续验收任务。
- 验证规则 §3（幂等/并发/输入校验）、§5～§8 等不在本任务范围。
- README.md 中“AI fallback 降级返回 unknown”的描述已过时（该文件不在 scope，未修改）。

## 7. 回退说明

本任务无数据库迁移、无配置变更。回退只需还原 3 个服务文件与 2 个测试文件（`git checkout -- <file>`）并删除新增的 `tests/unit/test_execution_failure_closed.py` 与本证据目录即可；回退后恢复“rc=0 默认 pass / unknown”旧语义（不建议，除非整体放弃 T-06 契约）。
