# RR-V1-FIX-T19V1-01：V1-01 补全——设备发现/改派/Device.version+003（task-19）

- 评审编号：RR-V1-FIX-T19V1-01
- 评审对象/任务编号：task-19（V1-01 补全：POST /device-discoveries、PATCH /devices/{serial}、Device.version+003、legacy refresh 委托；对应 T-03 补全）
- 评审日期：2026-11-12
- 评审人：reviewer（独立评审方）
- 依据文档与版本：`docs/contracts/device-authorization-v1.0.md` v1.0 §1/§2/§4/§5/§6/§7、`RR-V1-READINESS-20261112.md` V1-01、`RR-V1-FIX-T03T04T05.md`（此前判定"发现/改派未闭环"）
- 环境与 commit/变更集：Windows 10；Python 3.12.10；SQLite 3.49.1；git HEAD `fa70d3b` + 工作区（task-19 未提交）。变更：`app/services/device.py`（ADBDiscoveryError/get_device_list/discover_devices 重写）、`app/api/devices.py`（discovery_router + PATCH + refresh 委托 + GET 403 details.field）、`app/main.py`（注册 discovery_router 一行）、`app/models/__init__.py`（Device.version）、`alembic/versions/003_device_version.py`、新增 `tests/integration/test_v1_device_admin.py`(14)；`tests/unit/test_v1_migration.py` HEAD_REVISION 机械更新 002→003（已报 Lead）
- 证据路径：`docs/verification/tasks/T-03/result-v1-01-device-admin-20261112.md`、`pytest-v1-01-device-admin-green-20261112.log`、`migration-003-20261112.log`、`migration-003-summary.json`、`init-db-fresh-20261112.log`、`regression-full-20261112.log`；评审方独立重跑 `reviews/evidence/v1-fix-20261112/v1-fix-t19-device-admin-reviewer.log`（14 passed）、`v1-fix-t19-migration003-reviewer.log`（16/16 PASS）

## 1. 检查项与结论

| # | 检查项 | 方法 | 证据 | 结论 |
|---|---|---|---|---|
| 1 | ① POST /device-discoveries 201 + owner_unchanged=true | 读 devices.py discovery_router（status_code=201，items/total/owner_unchanged） | test_discovery_success_201_owner_unchanged（独立 14 passed 内） | 通过 |
| 2 | ① 发现不改既有 owner/PC/version；新设备 owner=null（普通用户不认领） | 读 device.py discover_devices 重写（既有设备不改 owner/pc/version；新设备 owner=None,pc=""） | test_discovery_does_not_change_existing_owner_pc_version、test_normal_user_discovery_new_device_owner_null | 通过 |
| 3 | ① ADB 失败 → 503 SERVICE_UNAVAILABLE，不批量误离线、testing 不被覆盖；有效空扫描 201 不误离线 | 读 ADBDiscoveryError（失败不触 DB）+ _adb_failure_response | test_discovery_adb_failure_503_does_not_offline_or_touch_testing、空扫描用例 | 通过 |
| 4 | ② PATCH 管理员（get_current_admin）version 条件更新递增 | 读 PATCH（DeviceAssignmentRequest extra=forbid；WHERE version 递增） | test PATCH 成功 200 且 version 1→2 | 通过 |
| 5 | ② 完全重放（同 owner+pc）幂等（旧 version 也 200 且不变）；不同目标旧 version → 409 details.field=version | 读 PATCH 完全重放分支 + 条件更新冲突 | 独立用例过（PATCH 成功/409/完全重放/普通用户 403/disabled 403/404/400） | 通过 |
| 6 | ② 普通用户/disabled 403；404 设备/目标用户；pc 空白 400；未知字段 400（pydantic extra=forbid）；目标未激活 400 | DeviceAssignmentRequest + 分支 | 7 个 PATCH 用例（独立 14 passed 内） | 通过 |
| 7 | ③ GET /devices/{serial} 403 → details.field=serial | 读 GET 的 403 转 JSONResponse build_error_body | test_get_device_forbidden_details_field_serial | 通过 |
| 8 | ④ Device.version 003 迁移：空库 0817→002→003、version 默认 1；存量副本加列数据全保留；downgrade 删列行保留；再 upgrade 恢复 | **独立运行 verify_device_version_migration.py** | **16/16 PASS**：行数 {tasks:10,records:98,devices:26,users:5} 全程保留；source SHA 前后一致 `2f919b…`；fresh init_db 探针 OK | 通过 |
| 9 | ⑤ legacy /devices/refresh 委托同一 discover_devices（deprecated，503） | 读 refresh diff + test_legacy_refresh_delegates_same_service | 200 成功 / 503 失败同语义 | 通过 |
| 10 | 真实库只读 | verify 脚本 source SHA 前后一致 | 未改真实库 | 通过 |
| 11 | 独立重跑 14 用例 | `pytest tests/integration/test_v1_device_admin.py` | **14 passed**，exit 0 | 通过 |

## 2. 独立重跑记录

| 命令 | 结果 | 退出码 | 日志 |
|---|---|---:|---|
| `pytest tests/integration/test_v1_device_admin.py` | **14 passed** | 0 | `evidence/v1-fix-20261112/v1-fix-t19-device-admin-reviewer.log` |
| `python docs/verification/tasks/T-03/verify_device_version_migration.py` | **16/16 PASS**（空库+存量副本+数据保留+源库 SHA 一致） | 0 | `evidence/v1-fix-20261112/v1-fix-t19-migration003-reviewer.log` |
| 开发证据：全量 | 427 passed / 0 failed | 0 | `docs/verification/tasks/T-03/regression-full-20261112.log` |
| 最终严格全量 | 待 Lead 最终日志（与 task-20/21 收口后），届时补记 | — | — |

## 3. 问题与风险等级 / 遗留

| # | 问题 | 依据 | 影响 | 等级 | 责任 |
|---|---|---|---|---|---|
| P-V1T19-1 | 真实设备发现未执行（真值表用 Mock ADB；真机未触发 discovery 写路径） | result §6.1 | 真机发现行为（adb 输出解析→发现结果）**无法核验**，仅单元/集成 mock 层验证 | 中 | 实机执行阶段（只读发现可另行授权） |
| P-V1T19-2 | 真实库迁移未执行（漂移 V1-05 遗留：新 init_db 会拒绝 stamp） | result §6.3；RR-V1-FIX-T02 P-V1T02-1 | 003 对结构一致副本可升级；真实库上线仍待用户 A/B 对账 | 高（既有 V1-05 阻塞，非本任务引入） | 用户/运维 |
| P-V1T19-3 | `tests/unit/test_v1_migration.py` HEAD_REVISION 002→003 机械更新（跨任务改他人文件） | result §1 已报 Lead | 仅常量更新、断言未放宽；可接受但属跨 scope 触碰 | 低 | 记录性（Lead 知悉） |
| P-V1T19-4 | 发现接口对普通用户无 PC 标识不做限制（新设备 owner=null 可见性依 filter 规则） | devices.py create_device_discovery 注释 | 符合契约"普通用户不认领"；发现结果可见性由列表过滤保证 | 低 | 记录性 |

## 4. 限制/无法核验项

| # | 事项 | 原因 | 影响 |
|---|---|---|---|
| L1 | 真机 discovery 端到端 | 本轮禁写设备；未触发 discovery | 真机发现无法核验（P-V1T19-1） |
| L2 | 真实库 003 升级 | V1-05 漂移阻塞 | 未执行（演练仅在副本） |
| L3 | 全量 427 passed 为自报 | 以 Lead 最终严格全量为准 | 独立重跑 14+16/16；全量待补记 |

## 5. 待用户确认项

无新增（V1-01 补全严格对齐 device-authorization §5/§6/§7 真值表）。

## 6. 最终结论

**通过（V1-01 补全：发现/改派/Device.version+003）。** POST /device-discoveries 201+owner_unchanged、发现不改既有 owner/PC/version、新设备 owner=null（普通用户不认领）、ADB 失败 503 不批量误离线且不动 testing；PATCH 管理员 version 条件更新递增、完全重放幂等、不同目标旧 version 409、普通用户/disabled 403、404/400齐备；GET 403 details.field=serial；legacy /devices/refresh 委托同一服务（deprecated）。003 迁移独立演练 **16/16 PASS**（空库+存量副本，行数全程保留、源库 SHA 一致）；**14 用例独立重跑 14 passed**。结合 task-9（手动/AI/重跑/报告/WS 授权），**V1-01 主体闭环**。遗留：真机 discovery 端到端无法核验（P-V1T19-1）、真实库迁移仍受 V1-05 漂移阻塞（P-V1T19-2）、HEAD_REVISION 跨 scope 机械更新已报备（P-V1T19-3）。全量以 Lead 最终严格日志为准。

## 7. 签名

reviewer，2026-11-12；本记录基于源码 diff、契约真值表、独立测试与独立迁移演练作出，未替开发修改任何代码，未对设备/真实库执行写操作。

---

## 附：最终严格全量补记（2026-11-12，reviewer）

- Lead 最终严格全量（无 ignore）：`docs/verification/tasks/V1-FINAL-STRICT-2-20261112.log` → **447 passed / 1 failed**。唯一失败为 `tests/unit/test_task_executor.py::test_cancel_running_task_keeps_cancelled`（断言 -cancelled +running）；经评审方隔离复跑 **3/3 通过**（`evidence/v1-fix-20261112/v1-final-cancel-test-stability-check.log`），判定为全量负载下的偶发竞态而非本轮修复回归（此前多轮全量 443/448 该用例均通过）；建议 Lead 复跑确认 0 failed 后归档。
- 评审方独立 6 项审计反例终验：**5 passed / 1 FAILED（R6 工具清单）**，日志 `evidence/v1-fix-20261112/targeted-defect-repro-FINAL-6of6.log`；R6 判定与基线更新建议见 `RR-V1-FIX-T17.md` §3。本记录结论不变，全量口径以该日志为准。
