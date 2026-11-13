# T-14 task-C1：cancel 状态机条件更新与竞态治理（契约 v1.1 章节）

- 关联：共享任务 task-25；RR-V1-REFINAL §3.4（`test_cancel_running_task_keeps_cancelled` 偶发 running）
- 执行人：execution-engine；时间：2026-11-13T09:15～11:00 +08:00
- 环境：Windows / Python 3.12.10 / pytest 7.4.4；后端 `D:\MCTEST\test-platform\backend`；解释器 `D:\MCTEST\test-platform\.venv\Scripts\python.exe`
- 变更集：未 git commit。改动文件：`app/api/tasks.py`（cancel 端点）、`app/services/task_executor.py`、`tests/unit/test_v1_cancel_stability.py`（新增）、`tests/unit/test_v1_judgement_stop.py`（task-10 已交付文件，本任务内同步 1 处日志打桩语义，见 §5.4）、`tests/conftest.py`（Lead 授权的测试夹具并发参数，见 §5.5）；`docs/verification/tasks/T-14/` 证据。**禁止范围未触碰**：契约文档、ai_tasks/nl_task_planner/task_creation、reports/websocket/dashboard、frontend。

## 1. 根因链（红→绿过程中逐层实证）

| # | 缺陷 | 实证 | 修复 |
|---|---|---|---|
| 1 | API 端点与执行器收尾均为无条件 ORM 状态写；ORM 陈旧属性 flush 是隐藏写回后门 | 红用例 1（当前代码 `completed` 覆盖 `cancelled`，[v1.1-red-evidence.log](v1.1-red-evidence.log)） | 全部状态推进改条件更新（core `update` + rowcount；`WHERE status IN ('pending','running')`），输掉竞态零写入；条件更新后同步 ORM 对象，消除陈旧写回 |
| 2 | 取消信号打断执行器会话上的 DB 操作后，`_release_device`（finally）抛非 Cancelled 异常**替换**在飞 CancelledError → `_handle_cancel` 不执行 → 最后落库值停留 running | 红用例 2（当前代码实际 `failed`，同上日志） | finally 加固：异常→日志+rollback+重取设备对象重试一次，不改持有者校验语义；取消收尾移出异常作用域（见 #3） |
| 3 | **真根因**：CancelledError 的 traceback 钉住被打断的 ORM 游标帧（`db.refresh(record)` 执行中被取消），未复位游标的 SQLite 读锁在整个 except 块收尾期间不释放 → 收尾写库全部 `database is locked`（每次 5.4s 超时，与 [v1.1-diag-stab-run2.log](v1.1-diag-stab-run2.log) 时间线逐条吻合）→ cancelled 永远落不了库 | diag 现场日志（10:08:42 取消→10:08:48/53→10:09:05/11/17 五连 BUSY） | 取消/异常收尾移出 except 作用域：`except asyncio.CancelledError:` 不绑定异常对象，块结束时异常与 traceback 自动回收、游标帧释放、锁解除，**之后**再执行 `_handle_cancel` + `_ensure_cancelled_persisted`，最后重新抛出 CancelledError |
| 4 | 并发取消重复投递 CancelledError，第二次信号打断取消收尾本身 | 并发 10 用例失败现场（record 停留 running） | `TaskExecutor.cancel_task` 单次投递（`_cancel_signalled` 标记，重复调用返回 True 不重复 cancel） |
| 5 | 测试基础设施：SQLite 回滚日志模式下读者被 PENDING 写锁直接拒（busy_timeout 不覆盖），并发取消用例的鉴权 SELECT 偶发 BUSY → 500 | STAB run2/run3（`get_current_user` → `database is locked`） | Lead 授权域（测试夹具）：`PRAGMA journal_mode=WAL`（读者/写者互不阻塞）+ busy_timeout 30s；WAL sidecar 文件清理 |

端点幂等语义（保持契约）：404/403/400 预检在前 → 信号 → 条件更新 → 提交先于响应（happens-before）；终态重复取消 → 400 VALIDATION_ERROR（外层形状不变，[既有契约用例](../../../test-platform/backend/tests/integration/test_contract_errors.py) 通过）；竞态窗口输掉 → 重读状态：已 cancelled → 200 幂等，其他终态 → 400。执行器端：running/completed/failed 收尾全部条件化，输掉竞态不写任何状态、不调度报告、不做记忆体沉淀；skip/设备释放持有者校验语义不变。

## 2. 命令、退出码、日志

| 命令（workdir=backend） | 退出码 | 日志 |
|---|---|---|
| 红：`pytest tests/unit/test_v1_cancel_stability.py::test_red_* -v`（当前代码） | 1（2 failed，复现两缺陷） | [v1.1-red-evidence.log](v1.1-red-evidence.log)（保留） |
| 诊断：`pytest tests/unit/test_v1_cancel_stability.py -q -o log_cli=true --log-cli-level=INFO` | 1（复现真根因 #3） | [v1.1-diag-stab-run2.log](v1.1-diag-stab-run2.log)（时间线证据，保留） |
| 稳定性（绿后）：同文件 ×N 轮 | 0（7 passed/轮） | [v1.1-green-stability-run1~4.log](v1.1-green-stability-run1.log)（最终 4 轮连绿；中间失败轮日志亦保留于同目录作治理过程证据） |
| 定向回归：task_executor / v1_judgement_stop / v1_cancel_stability / tasks_api / contract_errors | 0（75、94 passed） | [v1.1-targeted-regression.log](v1.1-targeted-regression.log) |
| 全量第 1 轮：`pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning` | 0（**467 passed**） | [v1.1-pytest-full-r1.log](v1.1-pytest-full-r1.log) |
| 全量第 2 轮（连续） | 0（**467 passed**） | [v1.1-pytest-full-r2.log](v1.1-pytest-full-r2.log) |
| 治理过程中的中间失败日志（保留）：加固前全量 1 failed、加固后 run2 2 failed、logger 打桩回归等 | 1 | [v1.1-pytest-full.log](v1.1-pytest-full.log)、[v1.1-pytest-full-run2.log](v1.1-pytest-full-run2.log)、[v1.1-green-stability.log](v1.1-green-stability.log)、[v1.1-pytest-unit.log](v1.1-pytest-unit.log)、[v1.1-targeted-regression.log](v1.1-targeted-regression.log) |

## 3. DoD 逐条证据

| DoD | 结论 | 证据 |
|---|---|---|
| ① 取消端点（legacy + cancellations 共用）条件更新 pending/running→cancelled 并提交，预检后触发 | ✅ | `tasks.py::cancel_task` 重构（标量查询+条件更新+退避重试）；`test_cancellations_alias_delegates_cancel`、`test_cancellations_alias_same_auth`、`test_cancel_task` 原断言全过 |
| ① 幂等：重复取消返回当前状态；非终态 400 VALIDATION_ERROR；外层形状不变 | ✅ | `test_cancel_terminal_task_returns_400_validation_error`（completed/cancelled × 双路径 → 400 + 不覆盖终态）；契约用例外层形状断言通过 |
| ② 执行器收尾条件更新，cancelled 不得被覆盖；输掉竞态零写入/不调度报告/不做记忆体 | ✅ | 红用例 1 转绿；`_execute_with_db` running/completed、`_fail_remaining_items`、`_handle_failure` 均走 `_transition_task_status`（rowcount 判定）；stop/离线收尾既有用例全过 |
| ② `_handle_cancel` 幂等收尾 | ✅ | `_handle_cancel` set 条件更新 + 记录批量收尾（幂等）；红用例 2 转绿断言 record error/任务被取消 |
| ② happens-before：端点条件更新提交先于断言可见 | ✅ | 20 连跑/并发 10 全部基于真实 API 响应与 gather 后断言 |
| ③ 模块级连续 20 次取消断言 cancelled（双路径） | ✅ | `test_cancel_twenty_consecutive_cycles_legacy_api` / `_cancellations_api`（20×2，事件钉 running 消除时序假失败，Lead 修正采纳） |
| ③ 并发 10 全部返回、终态 cancelled、无 500（legacy + 混发） | ✅ | `test_concurrent_ten_cancels_legacy_no_500` / `_mixed_paths_no_500`（混发 5+5 双路径） |
| 既有取消用例不放宽 | ✅ | `test_cancel_running_task_keeps_cancelled`、`test_queued_task_cancellable`、`test_handle_cancel_missing_task_no_error` 等原断言零改动通过 |
| 全量连续 2 轮 0 failed | ✅ | r1/r2 各 467 passed、exit 0（§2） |

## 4. 排查过程与保留的中间失败（诚实记录）

加固是分层的，每层都先在真实环境验证、失败日志全部保留：
1. 条件更新+finally 加固 → 全量 1 failed（偶发仍现）→ 诊断定位 #3 真根因；
2. 收尾移出异常作用域 → 稳定性 3 连绿 → 全量 run2 2 failed（并发端点 BUSY 500 + 日志打桩回归）→ 端点退避重试 + 打桩语义更新；
3. 端点重试 → STAB 仍偶发 → ORM expire 惰性加载（MissingGreenlet）→ 标量化查询 + `current_user` 标量提升；
4. → 仍偶发 → Lead 确认 20 连跑测试设计缺陷（任务自然到终态 400 属正确语义）→ 事件钉 running + 终态 400 护栏用例；
5. → 仍偶发 → 鉴权 SELECT 撞 PENDING 写锁（测试夹具基础设施）→ Lead 授权 WAL + busy_timeout 30s；
6. 最终：稳定性 4 连绿 + 全量连续 2 轮 0 failed。

## 5. 语义决策与范围说明（需评审项）

1. **取消幂等语义**：终态重复取消 → 400 VALIDATION_ERROR（契约既有）；竞态窗口输掉且已 cancelled → 200 幂等返回；其他终态 → 400 带当前状态。与契约用例完全兼容。
2. **单次投递**：`cancel_task` 对同一协程只投递一次取消信号（重复调用返回 True）——重复投递会打断取消收尾本身，实证于并发用例。
3. **测试夹具改动（Lead 授权域）**：`tests/conftest.py` test_db 引擎增加 `timeout=30`（busy_timeout）与 `PRAGMA journal_mode=WAL` + sidecar 清理。**该文件不在 task-25 write_scopes 内，属 Lead 口头授权扩展，请评审确认**；仅影响测试基础设施，不影响生产连接参数。
4. **`test_v1_judgement_stop.py` 打桩语义更新**（task-10 交付文件的 1 处）：`_run_task` 平台异常日志从 `logger.exception`（exc_info 会钉住被打断游标帧、复现锁问题）改为 `logger.error` + 格式化堆栈字符串——完整堆栈仍仅进服务端日志，但 LogRecord 不再持有帧引用。测试打桩相应改为 `patch.object(logger, "error")`，断言强度不变（call_count ≥1）。属语义化更新并说明，非放宽。
5. `tests/unit/test_judgement_engine.py` 在 write_scopes 内但本任务无需改动，未触碰。

## 6. 未验证项 / 限制

- 门禁结论为"连续 2 轮全量 0 failed"+稳定性 4 连绿；按 RR 建议"连续 3 轮全量"仍可在后续轮次继续累积（本轮两次全量 ≈9 分钟/轮，如需第 3 轮可补跑）。
- WAL/busy_timeout 仅作用于测试临时库；生产库（MySQL/PG，行锁）不存在同类问题，无需同步。
- 并发用例的"全部返回无 500"在 SQLite BUSY 退避重试兜底下达成；生产数据库下该重试层理论上不触发（行锁等待），保留为防御性实现。

## 7. 回退说明

无迁移/配置变更。回退：还原 `app/api/tasks.py`、`app/services/task_executor.py`，删除 `tests/unit/test_v1_cancel_stability.py`，还原 `tests/conftest.py`（busy_timeout/WAL/sidecar 清理）与 `tests/unit/test_v1_judgement_stop.py` 的打桩改动。回退后恢复旧 last-writer-wins / 收尾丢失 / 偶发 running 行为（不建议）。
