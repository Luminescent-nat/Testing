# RR-V1-FIX-T14：V1-09b 任务删除边界、item_ids 写前校验与设备不可用 409（task-17）

- 评审编号：RR-V1-FIX-T14
- 评审对象/任务编号：task-17（V1-09b；对应 T-14；rev5→rev6 含 D2 追加）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/task-execution-v1.0.md` v1.0 §2（R14：不存在 item=400）、§7（409）、§8（软删除）、`RR-V1-READINESS-20261112.md` V1-09（删除/创建边界）、`verification-rules-v1.0.md` §3.1（取消/软删除幂等）
- 环境与 commit/变更集：Windows 10；Python 3.12.10；git HEAD `fa70d3b` + 工作区。变更：`app/models/__init__.py`（TestTask.deleted_at，Lead 批准）、`alembic/versions/004_task_deleted_at.py`（additive+downgrade 数据保护）、`app/schemas.py`（item_ids 校验）、`app/api/tasks.py`（软删除/409/400 item_ids.<下标>）、新增 `tests/integration/test_v1_task_delete.py`(18)、3 个既有测试 409/400 更新（更严）、`tests/unit/test_v1_migration.py` HEAD_REVISION→004（Lead 授权跨任务同步）
- 证据路径：`docs/verification/tasks/T-14/`（result.md、pytest-focused.log、alembic-004-drill.log、migration-summary-v1followup.json、pytest-full-run-03-final-ignore-followup-audit.log）；评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-fix-t14-delete-focused-reviewer.log`（42 passed）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | DELETE：终态软删除 200 `{id,deleted:true,artifacts:"retained"}`、deleted_at 写入、记录/报告引用保留 | 独立重跑聚焦 42 passed | test 管理员删 completed 断言 deleted_at 非空、TestRecord 保留、报告可追溯 | 通过 |
| 2 | DELETE 幂等：重复删除 200 不 500、deleted_at 不变 | 同上 | test 重复删除用例 | 通过 |
| 3 | DELETE pending/running → 409、deleted_at 仍 None | 同上 | test 参数化用例 | 通过 |
| 4 | DELETE 越权 403 零写入；不存在 404；非管理员（get_current_admin） | 同上 | test 用例 | 通过 |
| 5 | 默认列表/详情排除已删除（引用保留可追溯） | 读 tasks.py list/get 过滤 | test 断言列表不含、详情 404 | 通过 |
| 6 | item_ids `[]`/`[0]`/`[-1]`/`[1,1]`/`["abc"]` → 400 details.field=item_ids(.0)，零写入 | schemas._validate_item_ids + API | test 六类非法用例（独立 42 passed 内） | 通过 |
| 7 | 不存在/禁用 item → 400 `item_ids.<下标>`（R14：404→400），写前零写入 | 读 create 分支 `_ItemValidationError` | test 合法+99999 → item_ids.1；禁用 → reason 含"禁用" | 通过 |
| 8 | D2：创建 offline/maintenance → **409 CONFLICT**（原 400），零写入 | 读 create 分支 | test 参数化 409；test_tasks_api TC-TASK-002 400→409；test_contract_errors test_business_409_offline_device | 通过 |
| 9 | D2：重跑 offline/maintenance → 409 | 读 rerun 分支 | test 重跑 offline 409 零新增 | 通过 |
| 10 | 004 迁移：additive deleted_at；有软删除数据 downgrade 拒绝、数据保留 | 读 004 + 演练日志 | 演练：downgrade 003 被拒（RuntimeError"存在 1 行已软删除任务"），数据 rows=2,1 保留；清空后降级成功；重新 upgrade 恢复 | 通过 |
| 11 | 既有断言更新更严不放宽 | git diff 测试 | 仅状态码收紧（400→409、404→400+field） | 通过 |
| 12 | 未越界 | git status | 未改 judgement/execution/task_executor/reports/websocket/frontend/database/device.py | 通过 |

## 2. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest test_v1_task_delete + test_tasks_api + test_contract_errors` | **42 passed**（18 删除/边界新用例内含） | 0 | `evidence/v1-fix-20261112/v1-fix-t14-delete-focused-reviewer.log` |
| 开发证据：迁移演练 | 拒绝/保留/恢复全 PASS | — | `docs/verification/tasks/T-14/alembic-004-drill.log` |
| 开发证据：全量（最终轮） | 443 passed / 0 failed | 0 | `docs/verification/tasks/T-14/pytest-full-run-03-final-ignore-followup-audit.log` |
| 最终严格全量 | 待 Lead `V1-FINAL-STRICT-2-20261112.log`，届时补记 | — | — |

## 3. 问题与风险等级 / 遗留

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V1T14-1 | AI 创建入口 offline/maintenance 原仍 400（task-17 scope 外） | result §7.1 | **已由 task-22 followup 收口为 409**（test_v1_followup_audit::test_audit_ai_maintenance_device_cannot_start，独立 5 passed）→ D2 完全闭环 | 已关闭 | task-22 |
| P-V1T14-2 | 软删除报告/历史引用的完整前端展示 | 后端已排除默认列表/详情；报告引用保留 | 前端展示属 T-22+ | 低 | 前端任务 |
| P-V1T14-3 | 严格全量期间出现他人在途审计文件 5 failed | result §5（未修改/未跳过/未删除，日志保留） | 以 Lead 最终严格全量为准 | 记录性 | — |

## 4. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 真实库 004 迁移 | 仅隔离副本演练；真实库漂移 V1-05 阻塞 | 未执行 |
| L2 | 全量 443/448 为自报 | 以 Lead 最终严格日志为准 | 独立重跑 42 passed；全量待补记 |

## 5. 待用户确认项

无新增（D2 409 为契约要求；软删除对齐契约 §8）。

## 6. 最终结论

**通过（V1-09b：删除边界/item_ids 写前校验/D2 设备不可用 409）。** DELETE 软删除幂等（重复 200 不 500、deleted_at 不变）、pending/running 409、越权 403 零写入、引用保留、默认列表/详情排除；item_ids 六类非法 → 400 details.field=item_ids(.下标) 零写入（R14：不存在/禁用 item 由 404 改 400，写前校验）；**D2 创建/重跑 offline/maintenance → 409**（RR-V1-FIX-T10 的 D2 偏差由此关闭；AI 路径由 task-22 收口 409）。004 迁移含软删除数据 downgrade 拒绝、数据保留。独立重跑聚焦 **42 passed**。全量以 Lead 最终严格日志为准。

## 7. 签名

reviewer，2026-11-12；本记录基于源码 diff、契约与独立测试重跑作出，未替开发修改任何代码。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
