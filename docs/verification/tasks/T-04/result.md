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
