# RR-V1-FIX-T22：V1 followup 契约收口（AI 409 / PATCH owner_id / discovery 空体 / 分页 / DeviceStatus / HEAD_REVISION→004）（task-22）

- 评审编号：RR-V1-FIX-T22
- 评审对象/任务编号：task-22（V1 followup 收口；作为 `RR-V1-FIX-T03T04T05.md` 的附录，亦可独立引用）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/device-authorization-v1.0.md` v1.0 §2/§5/§6、`docs/contracts/task-execution-v1.0.md` v1.0 §2/§8/§10（AI 必须转为同一创建对象）、`RR-V1-READINESS-20261112.md`（审计文件 test_v1_followup_audit.py）
- 环境与 commit/变更集：Windows 10；Python 3.12.10；git HEAD `fa70d3b` + 工作区。变更：`app/api/ai_tasks.py`（offline/maintenance 400→409）、`app/api/devices.py`（PATCH owner_id 必填可 null；discovery 固定空体）、`app/schemas.py`（DeviceStatus 补 MAINTENANCE，Lead 授权一行）、`scripts/verify_migrations.py`（HEAD_REVISION→004_task_deleted_at）、`tests/integration/test_v1_followup_audit.py`（审计文件转永久回归）
- 证据路径：`docs/verification/tasks/T-03/result.md` §6（收口表）、`pytest-focused-followup.log`（65 passed）、`pytest-full-run-followup-final.log`（448 passed）；评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-fix-t22-followup-audit-reviewer.log`（5 passed）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | AI 创建设备 offline/maintenance → **409 CONFLICT**（与手动 D2 一致，写前零任务写入；testing 仍 409） | 读 ai_tasks.py 分支；独立跑 followup 审计 | test_audit_ai_maintenance_device_cannot_start（独立 5 passed 内） | 通过（RR-V1-FIX-T10 D2 偏差由此关闭） |
| 2 | PATCH `owner_id` 必填（可显式 null）：缺字段 → 400 details.field=owner_id | 读 DeviceAssignmentRequest（owner_id 必填字段，可 null 值） | test_audit_patch_owner_id_is_required_even_when_nullable | 通过 |
| 3 | POST /device-discoveries 固定空体：非空对象/未知字段 → 400 details.field=body | 读 discovery 请求体模型 | test_audit_discovery_rejects_nonempty_body | 通过 |
| 4 | GET /devices 分页校验 page>=1、1<=page_size<=100（非法 422→400），响应补 page/page_size | 读 devices.py list Query 约束 | test_audit_device_list_rejects_invalid_pagination | 通过 |
| 5 | DeviceStatus 枚举补 MAINTENANCE（修复 maintenance 设备 GET 序列化 500） | 读 schemas.py 枚举；result 记录于 T-14 §8 | test_audit_maintenance_device_serializes_and_is_filterable | 通过 |
| 6 | verify_migrations.py HEAD_REVISION→004_task_deleted_at 并重跑演练 | 独立核对 migration-summary-v1followup.json | **74/74 checks PASS**（T-14/verify-migrations-004-drill.log） | 通过 |
| 7 | 审计文件转永久回归（去"仅审计使用"标注，注明收口范围） | 读文件头 | test_v1_followup_audit.py 成为回归资产 | 通过 |
| 8 | 独立重跑审计 5 用例 | `pytest tests/integration/test_v1_followup_audit.py` | **5 passed** | 通过 |

## 2. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest tests/integration/test_v1_followup_audit.py` | **5 passed** | 0 | `evidence/v1-fix-20261112/v1-fix-t22-followup-audit-reviewer.log` |
| 开发证据：聚焦 | 65 passed | 0 | `docs/verification/tasks/T-03/pytest-focused-followup.log` |
| 开发证据：全量严格 | 448 passed / 0 failed | 0 | `docs/verification/tasks/T-03/pytest-full-run-followup-final.log` |
| 最终严格全量 | 待 Lead `V1-FINAL-STRICT-2-20261112.log`，届时补记 | — | — |

## 3. 问题与风险等级 / 遗留

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V1T22-1 | 409/400 的 message 未见契约示例逐字核对（错误码/结构正确） | 抽查 | 低 | 低 | 记录性 |
| P-V1T22-2 | discovery 空体策略与契约 §5"请求体固定 {}"一致；未覆盖鉴权外场景 | 抽查 | 低 | 低 | 记录性 |

## 4. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 真实后端联调/浏览器 | 环境限制 | 待 T-38 联调 |
| L2 | 全量 448 为自报 | 以 Lead 最终严格日志为准 | 待补记 |

## 5. 待用户确认项

无新增。

## 6. 最终结论

**通过（followup 收口范围）。** AI 创建 offline/maintenance 409（D2 全闭环，含手动/重跑/AI）、PATCH owner_id 必填可 null（缺字段 400）、discovery 固定空体（非空 400）、设备分页校验 400、DeviceStatus 补 MAINTENANCE（修 500）、verify_migrations HEAD_REVISION→004 重跑 74/74 PASS；审计文件转永久回归。独立重跑审计 5 passed；全量以 Lead 最终严格日志为准。

## 7. 签名

reviewer，2026-11-12；本记录基于源码 diff、契约与独立测试重跑作出，未替开发修改任何代码。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
