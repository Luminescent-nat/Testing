# T-05 报告读取/导出与 WS 订阅统一授权（V1-07 WS 部分）验证记录

- 任务：task-9，本文件对应 T-05（报告读取/导出/缓存 + WS 首消息订阅授权）
- 状态：实现完成，WS disabled → 1008 已验证，全量回归 378 passed / exit 0
- 日期：2026-11-12；基线 HEAD fa70d3b；未 commit（Lead 统一提交）
- 环境：Windows + D:\MCTEST\test-platform\.venv\Scripts\python.exe（Python 3.12.10，pytest 7.4.4，fastapi 0.109.0，starlette 0.35.1）

## 1. 变更文件
| 文件 | 变更 |
|---|---|
| test-platform/backend/app/services/authorization.py | **新增**：`can_read_task/ensure_can_read_task`（active + 管理员任意 / 普通用户仅本人任务；disabled 403）、`is_active`。报告与 WS 复用 |
| test-platform/backend/app/api/reports.py | `_check_report_permission`、`_build_report`、`get_item_log` 改用 `ensure_can_read_task`（active + 创建者/管理员）；`_build_multi_task_report`（summary/batch export）遇 403 **不再静默 `continue`**，请求集中含越权任务时整体 403；缓存路径（已落盘 report.json/html）同样先走 `_check_report_permission` |
| test-platform/backend/app/websocket.py | 首消息认证后：`authorization.is_active(user)` 为假（disabled）→ **1008 POLICY_VIOLATION**（reason 用户已被禁用）；任务归属改用 `authorization.can_read_task`（与 REST 同口径，管理员/创建者） |
| test-platform/backend/tests/integration/test_v1_authorization.py | **新增**：报告越权/本人/批量越权、WS disabled 1008、active 对照、disabled REST 403 用例 |

## 2. 覆盖用例
| 用例 | 场景 | 期望 |
|---|---|---|
| test_report_read_forbidden_for_other_user | 普通用户读取他人报告 | 403 FORBIDDEN |
| test_report_read_allowed_for_owner | 普通用户读取本人报告 | 200 |
| test_batch_export_rejects_unauthorized_task | 批量导出含他人任务 | 403（不静默跳过） |
| test_ws_disabled_user_closed_1008 | V1-07：disabled 用户 WS 首消息 | 关闭码 1008 POLICY_VIOLATION |
| test_ws_active_user_still_allowed | 对照：active 用户本人任务 | 认证通过并收到 test_progress |
| test_disabled_user_rest_403 | disabled 用户 REST | 403 |

说明：WS 用例使用 `TestClient(app)`（不进入 `with` 上下文，因而**不触发 lifespan**）完成 websocket 握手；WS 鉴权不依赖启动期初始化，故与并行任务的启动校验/迁移解耦。既有 `tests/integration/test_websocket.py`（含 lifespan、心跳 mock）同轮 3 passed，两者共同覆盖。

## 3. 命令与退出码（原始日志）
| # | 命令 | 结果 | 日志 |
|---|---|---|---|
| 1 | `python -m pytest tests/integration/test_v1_authorization.py -q --tb=short -rA` | **17 passed，exit 0** | [pytest-v1-authorization.log](../T-04/pytest-v1-authorization.log) |
| 2 | 受影响集成集合（含 websocket/reports/reports_stats）`-q --tb=short -rA` | **73 passed，exit 0** | [pytest-affected-integration.log](../T-04/pytest-affected-integration.log) |
| 3 | `python -m pytest tests/integration/test_websocket.py -q --tb=line` | 3 passed，exit 0 | [pytest-websocket-external-failure.log](../T-03/pytest-websocket-external-failure.log) |
| 4 | 全量 `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA` | **378 passed，0 failed，exit 0**（155.5s） | [pytest-full-run-03-final.log](../T-03/pytest-full-run-03-final.log) |

## 4. DoD 结论（task-9）
- **报告读取/导出/缓存复用 active + 创建者/管理员校验** → 达成：三处读取入口统一 `ensure_can_read_task`；缓存分支亦先校验。
- **批量导出不能绕过授权或静默跳过越权任务** → 达成：越权任务整体 403（修改了原 `except HTTPException: continue` 的静默跳过）。
- **WS 首消息订阅校验 disabled → 1008** → 达成（V1-07），active 用户对照正常。
- **禁止改其它队友模块** → 达成（仅改 reports.py / websocket.py / authorization.py 与新测试）。

## 5. 遗留
1. 报告 403 message 沿用既有“无权限查看报告/无权限查看”；未强制契约示例的 details.field。
2. WS 其它既有行为（认证超时、无效 token、ping/pong）由 `test_websocket.py` 覆盖，本轮未改动其语义。
3. 全量运行期间出现过并行任务（app/database.py、models）导致的瞬时 `SchemaMismatchError`，最终轮已消失（378 passed）；失败日志保留于 T-03 目录。
