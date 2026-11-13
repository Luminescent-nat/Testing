# T-04 手动/AI/失败重跑复用设备授权（V1-01 写入口）验证记录

- 任务：task-9，本文件对应 T-04（手动与 AI 创建、失败重跑复用设备授权）
- 状态：实现完成；V1-01 定向复现 fail→pass 已闭环，全量回归 378 passed / exit 0
- 日期：2026-11-12；基线 HEAD fa70d3b；未 commit（Lead 统一提交）
- 环境：Windows + D:\MCTEST\test-platform\.venv\Scripts\python.exe（Python 3.12.10，pytest 7.4.4，fastapi 0.109.0，starlette 0.35.1）

## 1. 变更文件
| 文件 | 变更 |
|---|---|
| test-platform/backend/app/services/authorization.py | **新增**：统一授权策略（含 `ensure_can_create_task_on_device`：active + 管理员任意 / 普通用户 owner=本人且 PC 一致，否则 403） |
| test-platform/backend/app/api/tasks.py | `create_task` 在解析设备后、任何写库/启动执行前调用 `ensure_can_create_task_on_device`；`rerun_failed_items` 在源任务归属校验后、设备可用性判断前同样调用（防止设备归属变更后越权重跑）。**未改幂等/201**（task-12 负责） |
| test-platform/backend/app/api/ai_tasks.py | AI 自然语言创建在解析目标设备后、`testing/offline` 分支与任务写入前调用 `ensure_can_create_task_on_device` |
| test-platform/backend/tests/integration/test_v1_authorization.py | **新增**：V1-01 核心复现用例（保留原名 `test_audit_normal_user_cannot_start_task_on_other_users_device`）＋手动/AI/重跑授权真值表用例 |

## 2. V1-01 定向复现（fail → pass）
- 复现源：`docs/verification/reviews/evidence/v1-readiness-20261112/targeted-defect-repro.py` 第 13-33 行，已**逐字纳入** `tests/integration/test_v1_authorization.py::test_audit_normal_user_cannot_start_task_on_other_users_device`（永久回归）。
- 修复前（审计 RR-V1-READINESS 动态复现）：普通用户用他人异 PC 设备创建任务返回 200。
- 修复后：`POST /api/v1/tasks` 返回 **403 FORBIDDEN**，普通用户任务列表 `total=0`，且服务端 `TestTask` 计数 `==0`（零写入）。
- fail→pass 归因证据：临时移除授权守卫生成旧行为演示（该临时用例已删除，仅日志保留）→ 同一请求返回 200，证明 403 由新授权逻辑决定：[repro-before-fix-demo.log](../T-03/repro-before-fix-demo.log)。

## 3. 授权真值表用例（test_v1_authorization.py）
| 用例 | 场景 | 期望 |
|---|---|---|
| test_audit_normal_user_cannot_start_task_on_other_users_device | 普通用户 + 他人异 PC 设备 | 403，任务 total=0，DB 计数=0 |
| test_admin_can_create_task_on_any_device | 管理员 + 他人设备 | 200 |
| test_normal_user_can_create_task_on_own_device_matching_pc | 普通用户 + 本人/PC 一致 | 200 pending |
| test_normal_user_cannot_create_task_on_other_owner_same_pc | 他人设备但 PC 一致（PC 非授权凭证） | 403 且零任务 |
| test_normal_user_cannot_create_task_on_own_device_mismatched_pc | 本人设备但 PC 不一致 | 403 且零任务 |
| test_normal_user_cannot_create_task_on_null_owner_device | owner=null | 403 且零任务 |
| test_ai_create_rejects_other_users_device | AI 自然语言 + 他人设备 | 403 且零任务 |
| test_rerun_rejects_device_no_longer_authorized | 重跑：源任务属本人但设备已归属他人 | 403 且不新增任务 |
| test_rerun_allowed_on_own_authorized_device | 重跑：本人任务且设备授权通过 | 200 创建重跑任务 |

## 4. 命令与退出码（原始日志）
| # | 命令 | 结果 | 日志 |
|---|---|---|---|
| 1 | `python -m pytest tests/integration/test_v1_authorization.py -q --tb=short -rA` | **17 passed，exit 0**（16:52:13-16:52:31） | [pytest-v1-authorization.log](pytest-v1-authorization.log) |
| 2 | 受影响集成集合（v1/tasks/ai/devices/websocket/reports/reports_stats/contract_errors）`-q --tb=short -rA` | **73 passed，exit 0**（16:52:32-16:53:38） | [pytest-affected-integration.log](pytest-affected-integration.log) |
| 3 | 全量 `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA` | **378 passed，0 failed，exit 0**（155.5s） | [pytest-full-run-03-final.log](../T-03/pytest-full-run-03-final.log) |

## 5. DoD 结论（task-9）
- **手动创建、AI 自然语言创建、失败重跑均复用同一策略** → 达成（同一 `authorization.ensure_can_create_task_on_device`，无第二套逻辑）。
- **写前校验，非法时零任务/零归属写入** → 达成：授权调用位于设备解析之后、状态变更/`db.add`/`commit`/`TaskExecutor.start_task` 之前；用例断言 403 后 `TestTask` 计数为 0、重跑不新增任务。
- **定向复现 403 且任务 total=0** → 达成（第 2 节）。
- **不得只改前端；禁止改其它队友模块** → 达成（仅改上表后端文件，未动 models/alembic/database/judgement/execution/task_executor/test-tools/frontend/device.py）。
- **既有测试如需改保持更严** → 本轮无需修改任何既有测试（全量 378 passed），无放宽/删除断言。

## 6. 遗留
1. 幂等键（Idempotency-Key）与创建返回 201 仍由 task-12 在同一 tasks.py 后续实现（本任务严格未动）。
2. 设备发现/改派（禁止改 device.py）见 T-03 result.md 遗留第 1 条。

---

# 追加：v1.1 章节（task-24，task-B AI 入口授权顺序与统一创建服务 B1~B3，2026-11-13）

- 契约依据：`docs/contracts/task-execution-v1.0.md` §10 授权顺序（v1.1 新增）、`CHANGES-DRAFT-v1.1-20261113.md` 变更包 2 GWT B1~B3、`RR-V1-REFINAL-20261112.md` §3.2/§3.3。
- 方法：严格先红后绿。

## B-1. 变更文件
| 文件 | 变更 |
|---|---|
| app/services/task_creation.py | **新增统一创建服务**：`create_task_instance`（设备查找→授权 403→可用性 409→item 存在/禁用 400 R14→参数/调度校验→幂等 claim/replay/409→建任务（AI 附 plan 快照）→immediate 启动→统一 201 响应）、`find_idempotent_replay`（AI 重放预检：同键同文本直接返回首次响应，先于设备状态检查，避免 testing 后重放被 409 掩盖）、`OPERATION_TASK_CREATE_AI="task_create_ai"`（AI 独立幂等 operation）、`resolve_idempotency_key`、`validation_error_response`、`ItemValidationError` |
| app/services/nl_task_planner.py | `plan()` 拆分为 `resolve_device`（仅全量登记设备的候选匹配，**不触知识库/LLM**，他人设备可被解析从而得到 403 而非被 400 掩盖）与 `plan_for_device`（授权通过后：知识读取+LLM+模块/类型/测试项选择）；`_match_device` 改为全量设备匹配 |
| app/api/tasks.py | create_task 改为**薄委托** `create_task_instance`（删除自写校验/建任务/启动逻辑）；重跑键解析改用 `resolve_idempotency_key`；清理失效 import |
| app/api/ai_tasks.py | 重写为：文本→resolve_device→`ensure_can_create_task_on_device`(403)→testing/offline/maintenance(409)→`plan_for_device`(知识/LLM)→item_ids 校验→统一创建服务；**删除自写 TestTask/commit/设备状态推进**；LLM 客户端初始化移至授权之后；成功 **201**；幂等 operation=task_create_ai、请求摘要={"text","device_serial"}；重放预检先于状态检查 |
| tests/integration/test_v1_followup_audit.py | 新增 B1/B2 反例（monkeypatch `get_device_knowledge` 与 `LLMClient` 计数器）与 B3 差分断言（永久回归） |
| tests/integration/test_ai_tasks_api.py | TC-AI-001：200→**201**；`data["task_id"]`→`data["id"]`；plan 断言改为核对落库 `TestTask.plan`（更严） |

未改：契约文档、idempotency.py、judgement/execution/task_executor、reports/websocket/dashboard、frontend。

## B-2. GWT 逐条验收（先红后绿）
| 编号 | 红（实现前） | 绿（实现后） |
|---|---|---|
| B1 | [red-b1-b2-20261113.log]：实际 400「无法从输入中识别目标设备或测试意图」（期望 403）；llm 计数 1（期望 0） | **403 FORBIDDEN**，`knowledge=0、llm=0`，任务计数 0 |
| B2 | 同日志：409 已达成但 `{'knowledge': 1, 'llm': 1}`（期望全 0——授权前已读知识/调用 LLM） | **409 CONFLICT**，`knowledge=0、llm=0`，任务计数 0 |
| B3 | 同日志：`NLTaskPlanner has no attribute 'plan_for_device'` | 同设备同 item 集合手动 vs AI：`user_id/device_id/selected_items/custom_parameters/status/schedule_type/next_run_at` 逐字段相等；设备状态推进一致（testing）；**plan 仅 AI 行持有**（manual.plan is None）；幂等语义一致（AI 同键同文本重放同一任务 ID 且不被 testing-409 掩盖、同键不同文本 409 CONFLICT） |

计数器实现：monkeypatch `app.services.nl_task_planner.get_device_knowledge`（包装计数）与 `app.api.ai_tasks.LLMClient`（get_default_client 计数）。

## B-3. 命令与退出码（原始日志）
| # | 命令 | 结果 | 日志 |
|---|---|---|---|
| 1 | 红测：`pytest test_v1_followup_audit.py::test_b1... ::test_b2... ::test_b3... -q --tb=short` | **3 failed，exit 1**（B1 400≠403；B2 计数 1/1≠0；B3 plan_for_device 缺失） | [red-b1-b2-20261113.log](red-b1-b2-20261113.log) |
| 2 | 受影响集合（followup/ai/授权/契约错误/tasks/幂等/删除/知识规则/e2e）`-q --tb=short` | **98 passed，exit 0** | （过程轮，未单存日志） |
| 3 | 全量 `pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA` | **460 passed，0 failed，exit 0**（226.8s） | [pytest-full-v1.1-taskB-green.log](pytest-full-v1.1-taskB-green.log) |

## B-4. 关键决策
1. **授权先于知识/LLM 的实现位置**：拆 planner 而非加回调——`resolve_device` 只查设备表，`plan_for_device` 才触知识/LLM；LLM 客户端初始化也移至授权后（计数器验证）。
2. **resolve_device 匹配全量登记设备**（原实现按 pc 过滤，他人设备不可见→400 掩盖 403）：他人设备在授权阶段得到 403；无法识别仍是 400。计划快照的 `device_id` 来自真实解析。
3. **AI 重放预检**：AI 的状态 409 检查在统一服务之外（保持 testing→409 语义），为避免设备进入 testing 后同键重放被 409 掩盖，增加 `find_idempotent_replay` 预检（同键同文本先返回首次响应；请求摘要={"text","device_serial"}，因为 AI 的 name 来自规划结果不能直接用请求模型 dump）。
4. **AI 幂等 operation 独立**（task_create_ai）：与手动 task_create 键空间隔离，同键不跨入口冲突。

## B-5. 遗留
1. AI 幂等键缺失仍走兼容策略（不强幂等），与手动一致（偏差已在 T-10 记录待用户确认）。
2. `resolve_device` 全量匹配使“设备存在但他人所有”的 AI 文本得到 403；设备不存在仍 400 无法识别（契约 §2 未把该场景定为 404，保持现状）。
3. 期间曾出现 tasks.py 编辑中间态被 Lead 观察到 import 报警，已当场修复并回执（rerun 键解析改用 resolve_idempotency_key），最终全量绿。
