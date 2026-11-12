# T-03 共享设备授权策略（V1-01 设备部分）验证记录

- 任务：task-9（V1-01/V1-07 设备与 WS 统一授权），本文件对应 T-03（设备授权）
- 状态：实现完成，定向与全量回归全绿（详见第 4 节）
- 日期：2026-11-12；基线 HEAD fa70d3b；未 commit（Lead 统一提交）
- 环境：Windows + D:\MCTEST\test-platform\.venv\Scripts\python.exe（Python 3.12.10，pytest 7.4.4，fastapi 0.109.0，starlette 0.35.1）

## 1. 变更文件（本任务共享）
| 文件 | 变更 |
|---|---|
| test-platform/backend/app/services/authorization.py | **新增**：唯一授权策略。`can_access_device`（管理员任意；普通用户 owner=本人且 PC 一致；owner=null/他人 false；disabled false）、`ensure_device_access`（403）、`filter_visible_devices`、`ensure_can_create_task_on_device`、`can_read_task/ensure_can_read_task`、`is_active/ensure_active`。供手动/AI/重跑/设备/报告/WS 复用 |
| test-platform/backend/app/api/devices.py | 列表按 `filter_visible_devices` 服务端过滤（普通用户仅 owner=本人且 PC 一致，不只隐藏前端）；详情与设备知识接口改用 `ensure_device_access`（非管理员 owner/PC 不满足 → 403） |
| test-platform/backend/tests/integration/test_v1_authorization.py | **新增**：含设备列表过滤、详情 403/200、owner=null 授权真值表用例 |

## 2. 设备授权真值表覆盖（契约 device-authorization-v1.0 §1）
| 场景 | 期望 | 用例 |
|---|---|---|
| active 管理员任意设备 | 列表可见/详情 200/创建允许 | test_device_list_filters_by_owner_and_pc、test_device_detail_authorization、test_admin_can_create_task_on_any_device（T-04） |
| 普通用户 owner=本人且 PC 一致 | 可见/200 | test_device_list_filters_by_owner_and_pc、test_device_detail_authorization |
| 普通用户 owner=他人（PC 一致/不一致） | 不可见/403 | test_device_list_filters_by_owner_and_pc、test_device_detail_authorization、test_audit_normal_user_cannot_start_task_on_other_users_device |
| 普通用户 owner=null | 不可见/403 | test_device_detail_authorization；test_normal_user_cannot_create_task_on_null_owner_device（T-04） |
| disabled 用户 | 403/401 | test_disabled_user_rest_403（REST get_current_user 403）；WS 见 T-05 |
| 设备列表不返回不可见设备 | total/items 过滤 | test_device_list_filters_by_owner_and_pc |

## 3. 命令与退出码（原始日志）
| # | 命令 | 结果 | 日志 |
|---|---|---|---|
| 1 | `python -m pytest tests/integration/test_v1_authorization.py -q --tb=short -rA` | **17 passed，exit 0**（16:52:13-16:52:31） | [pytest-v1-authorization.log](../T-04/pytest-v1-authorization.log) |
| 2 | `python -m pytest tests/integration/test_v1_authorization.py ... 8 个集成文件 -q --tb=short -rA` | **73 passed，exit 0**（16:52:32-16:53:38） | [pytest-affected-integration.log](../T-04/pytest-affected-integration.log) |
| 3 | `python -m pytest tests -q -W error::pytest.PytestUnraisableExceptionWarning -rA`（全量） | **378 passed，0 failed，exit 0**（16:54-16:57，155.5s） | [pytest-full-run-03-final.log](pytest-full-run-03-final.log) |
| 4 | 参考：`python -m pytest tests/integration/test_websocket.py -q --tb=line` | 3 passed，exit 0（16:49） | [pytest-websocket-external-failure.log](pytest-websocket-external-failure.log) |

说明：全量第 1/2 次运行（[pytest-full-run-01.log](pytest-full-run-01.log)、[pytest-full-run-02.log](pytest-full-run-02.log)）期间，其他并行任务正在改动 `app/database.py`/`app/models`，出现 `SchemaMismatchError` 导致 TestClient lifespan 用例（test_websocket）瞬时失败；该问题在 infra 任务完成后消失（见第 3 节 #4），最终全量 378 passed。失败历史日志按要求保留。

## 4. DoD 结论（task-9）
- **设备列表/详情按契约过滤/403，不只隐藏前端** → 达成：服务端 `filter_visible_devices` / `ensure_device_access`，用例断言普通用户仅见本人+PC 一致设备、他人/null 详情 403。
- **复用唯一授权策略** → 达成：`app/services/authorization.py` 为唯一事实来源，设备/任务/AI/重跑/报告/WS 全部复用（见 T-04/T-05）。
- **不得只改前端** → 达成：全部为后端服务端校验。
- **禁止改 device.py/models/alembic/database/judgement/execution/task_executor/test-tools/frontend** → 已遵守（本次仅改上表文件）。

## 5. 遗留 / 未覆盖（如实记录）
1. **设备发现（POST /device-discoveries 目标路径）与改派（PATCH /devices/{serial}）** 未在本次实现：任务明确禁止修改 `app/services/device.py`，且目标路径/版本条件更新属 T-03 完整范围，需后续任务在允许改动 device.py/新增路由时补齐；当前 legacy `POST /devices/refresh`、`PUT /devices/{serial}/status` 行为未变（status 仍仅管理员）。
2. **403 message 文案**：设备详情沿用契约示例“无权限访问此设备”；未按契约示例附带 `details.field=serial`（当前错误外层 details 仅在有字段级信息时给出，属可选项）。
3. disabled 用户的 REST 403 由 `get_current_user` 提供（本次未改 auth.py，保持既有行为）。

## 6. 追加（task-22 V1 followup 契约收口，2026-11-12）
T-03 遗留第 1 条中的设备契约缺口已由 task-22 收口（后端部分）：

| 缺口 | 修复 | 证据 |
|---|---|---|
| AI 创建设备 offline/maintenance 仍 400 | app/api/ai_tasks.py 改 **409 CONFLICT**（与手动创建 D2 一致，写前零任务写入；testing 仍 409 排队冲突） | test_v1_followup_audit.py::test_audit_ai_maintenance_device_cannot_start |
| PATCH /devices/{serial} owner_id 可省略 | DeviceAssignmentRequest.owner_id 改**必填（可显式 null）**：缺字段 → 400 details.field=owner_id（422 归并） | ::test_audit_patch_owner_id_is_required_even_when_nullable |
| POST /device-discoveries 接受任意体 | 请求体固定空对象：非空对象/未知字段 → **400** details.field=body | ::test_audit_discovery_rejects_nonempty_body |
| maintenance 设备序列化 500 | schemas.DeviceStatus 补 `MAINTENANCE = "maintenance"`（Lead 授权的契约对齐；说明记录于 T-14 result.md §8） | ::test_audit_maintenance_device_serializes_and_is_filterable |
| GET /devices 无分页校验 | page>=1、1<=page_size<=100（Query 约束，非法 422→400）；响应补 page/page_size | ::test_audit_device_list_rejects_invalid_pagination |
| scripts/verify_migrations.py HEAD_REVISION=002 | 同步为 004_task_deleted_at，重跑演练 **PASS (74/74 checks)** | [T-14/verify-migrations-004-drill.log](../T-14/verify-migrations-004-drill.log) |

审计文件 `tests/integration/test_v1_followup_audit.py` 已去掉"仅审计使用"标注，转为永久回归（文件头注明 task-22 收口范围）。改动范围：ai_tasks.py、devices.py、scripts/verify_migrations.py、schemas.py（Lead 授权一行枚举）、该测试文件。
验证：聚焦 65 passed / exit 0（[pytest-focused-followup.log](pytest-focused-followup.log)）；全量严格 **448 passed / 0 failed / exit 0**（242.3s，[pytest-full-run-followup-final.log](pytest-full-run-followup-final.log)）。发现/改派（owner_unchanged、版本条件更新）的完整契约行为由既有的 devices PATCH 实现与演练覆盖；真机发现（R3）仍无法核验。
